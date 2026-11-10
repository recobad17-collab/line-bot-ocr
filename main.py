from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import os
import re
import sqlite3
import sys
import threading
import time

# บังคับใช้ UTF-8 encoding บน Windows เพื่อไม่ให้ติดปัญหา cp1252 กับภาษาไทย
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from google import genai
from google.genai import types
import httpx
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import (
    ImageMessageContent,
    MessageEvent,
    TextMessageContent,
)

# โหลดค่า Environment Variables จาก .env
dotenv.load_dotenv()

CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_SHEET_WEBAPP_URL = os.getenv("GOOGLE_SHEET_WEBAPP_URL")

# ตั้งค่า LINE SDK Configuration และ Gemini Client
configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN or "")
handler = WebhookHandler(CHANNEL_SECRET or "")
gemini_client = genai.Client(api_key=GEMINI_API_KEY or "")

app = FastAPI(title="LINE Bot OCR to Google Sheets with Fast Batching")

# ==========================================
# ระบบจัดการคิวประมวลผลรูปภาพแบบคู่ขนาน (Parallel Worker Pool)
# ==========================================
# รองรับการประมวลผลรูปภาพพร้อมกัน 8 ภาพ เพื่อความเร็วสูงสุด
image_executor = ThreadPoolExecutor(max_workers=8)

pending_tasks = {}
pending_lock = threading.Lock()


def add_pending(source_id: str):
    with pending_lock:
        pending_tasks[source_id] = pending_tasks.get(source_id, 0) + 1


def remove_pending(source_id: str):
    with pending_lock:
        if source_id in pending_tasks:
            pending_tasks[source_id] -= 1
            if pending_tasks[source_id] <= 0:
                del pending_tasks[source_id]


def wait_for_pending(source_id: str, timeout: float = 12.0) -> bool:
    """รอให้รูปภาพทั้งหมดที่กำลังประมวลผลอยู่เสร็จสิ้น ก่อนจะเริ่มรวมยอด"""
    start = time.time()
    while time.time() - start < timeout:
        with pending_lock:
            count = pending_tasks.get(source_id, 0)
        if count == 0:
            return True
        time.sleep(0.2)
    return False


# บันทึกประวัติ Event ล่าสุด 50 รายการ สำหรับตรวจสอบผ่าน /debug
recent_logs = []


def log_event(action: str, detail: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] [{action}] {detail}"
    recent_logs.append(entry)
    if len(recent_logs) > 50:
        recent_logs.pop(0)
    try:
        print(entry)
    except Exception:
        pass


# ==========================================
# ระบบจัดการ Session สะสมยอดสลิป (SQLite WAL Mode)
# ==========================================
DB_PATH = "sessions.db"


def init_db():
    with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS slip_sessions (
                source_id TEXT PRIMARY KEY,
                branch TEXT,
                created_date TEXT,
                slips_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


init_db()


def get_source_id(event) -> str:
    """ดึง ID ของห้องแชท (กลุ่ม / แชทเดี่ยว / ห้อง) เพื่อแยก session"""
    source = event.source
    if hasattr(source, "group_id") and source.group_id:
        return f"group_{source.group_id}"
    if hasattr(source, "room_id") and source.room_id:
        return f"room_{source.room_id}"
    if hasattr(source, "user_id") and source.user_id:
        return f"user_{source.user_id}"
    return "default_source"


def start_session(source_id: str, branch: str = ""):
    """เริ่ม Session ใหม่ (หากมีของเดิมอยู่แล้ว ให้รีเซ็ตเริ่มนับใหม่ทันที)"""
    today_str = datetime.now().strftime("%d/%m/%Y")
    with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
        conn.execute(
            """
            INSERT INTO slip_sessions (source_id, branch, created_date, slips_json, updated_at)
            VALUES (?, ?, ?, '[]', CURRENT_TIMESTAMP)
            ON CONFLICT(source_id) DO UPDATE SET
                branch = excluded.branch,
                created_date = excluded.created_date,
                slips_json = '[]',
                updated_at = CURRENT_TIMESTAMP
            """,
            (source_id, branch, today_str),
        )
        conn.commit()


def get_session(source_id: str):
    """ดึงข้อมูล Session ที่กำลังเปิดใช้งานอยู่"""
    with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT branch, created_date, slips_json FROM slip_sessions WHERE source_id = ?",
            (source_id,),
        )
        row = cursor.fetchone()
        if row:
            branch, created_date, slips_json = row
            try:
                slips = json.loads(slips_json)
            except Exception:
                slips = []
            return {
                "branch": branch or "",
                "date": created_date or "",
                "slips": slips,
            }
    return None


def add_slip_to_session(source_id: str, amount: float, ref_no: str = ""):
    """เพิ่มข้อมูลสลิปเข้าไปใน Session สะสม (Thread-safe)"""
    with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT slips_json FROM slip_sessions WHERE source_id = ?",
            (source_id,),
        )
        row = cursor.fetchone()
        if not row:
            return False

        try:
            slips = json.loads(row[0])
        except Exception:
            slips = []

        slips.append({"amount": amount, "ref_no": ref_no})

        conn.execute(
            "UPDATE slip_sessions SET slips_json = ?, updated_at = CURRENT_TIMESTAMP WHERE source_id = ?",
            (json.dumps(slips, ensure_ascii=False), source_id),
        )
        conn.commit()
    return True


def clear_session(source_id: str):
    """ลบ Session ออกเมื่อสรุปยอดเสร็จสิ้น (#ok)"""
    with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
        conn.execute("DELETE FROM slip_sessions WHERE source_id = ?", (source_id,))
        conn.commit()


def clean_amount(val) -> float:
    """แปลงค่ายอดเงินที่ได้จาก OCR ให้เป็นตัวเลข float ที่คำนวณได้"""
    if val is None:
        return 0.0
    val_str = str(val).replace(",", "").strip()
    match = re.search(r"\d+(?:\.\d+)?", val_str)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            return 0.0
    return 0.0


def reply_line_message(reply_token: str, message_text: str):
    """ส่งข้อความตอบกลับใน LINE"""
    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=message_text)],
                )
            )
        log_event("REPLY_OK", f"ตอบกลับสำเร็จ: {message_text[:40]}...")
    except Exception as e:
        log_event("REPLY_ERROR", f"ตอบกลับไม่สำเร็จ: {e}")


def send_to_google_sheet(data: dict):
    """ส่งข้อมูล JSON ไปบันทึกลง Google Sheets ผ่าน Apps Script Web App"""
    webhook_url = os.getenv("GOOGLE_SHEET_WEBAPP_URL")
    if not webhook_url:
        return False

    try:
        with httpx.Client(follow_redirects=True, timeout=15.0) as client:
            resp = client.post(webhook_url, json=data)
            log_event("SHEET_OK", f"บันทึกชีทสำเร็จ ({data.get('category')}): {resp.status_code}")
            return True
    except Exception as e:
        log_event("SHEET_ERR", f"บันทึกชีทไม่สำเร็จ: {e}")
        return False


@app.get("/")
def read_root():
    return {
        "status": "LINE Bot OCR to Google Sheets with Fast Batching is running!",
        "sheet_configured": bool(GOOGLE_SHEET_WEBAPP_URL),
    }


@app.get("/debug")
def read_debug():
    """ดู Log เหตุการณ์ล่าสุดที่ยิงเข้ามายัง Webhook"""
    with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT source_id, branch, slips_json FROM slip_sessions")
        sessions = [
            {"source_id": r[0], "branch": r[1], "slips_count": len(json.loads(r[2]))}
            for r in cursor.fetchall()
        ]
    return {
        "active_sessions": sessions,
        "recent_logs": recent_logs,
    }


@app.post("/callback")
async def callback(request: Request, x_line_signature: str = Header(None)):
    """รับ Webhook event จาก LINE Platform"""
    if x_line_signature is None:
        raise HTTPException(status_code=400, detail="Missing X-Line-Signature")

    body = await request.body()
    body_str = body.decode("utf-8")
    log_event("WEBHOOK_IN", f"ได้รับ Request ขนาด {len(body_str)} ตัวอักษร")
    try:
        handler.handle(body_str, x_line_signature)
    except InvalidSignatureError:
        log_event("SIGNATURE_ERR", "Invalid Signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    return "OK"


# ==========================================
# จัดการข้อความตัวหนังสือ (#รวม, #รวม สาขา, #ok)
# ==========================================
@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    text = event.message.text.strip()
    source_id = get_source_id(event)
    reply_token = event.reply_token
    log_event("TEXT_RECEIVED", f"ข้อความ: '{text}' จาก {source_id}")

    # 1. ตรวจจับคำสั่ง #รวม หรือ # รวม หรือ รวม <ชื่อสาขา>
    match_sum = re.match(r"^(?:#\s*)?รวม(?:\s+(.+))?$", text, re.IGNORECASE)
    if match_sum:
        branch = match_sum.group(1).strip() if match_sum.group(1) else ""
        start_session(source_id, branch)
        log_event("SESSION_START", f"เริ่มนับสลิปสาขา: '{branch or 'ทั่วไป'}'")

        if branch:
            reply_text = f"พร้อมรับรูปสาขา {branch}"
        else:
            reply_text = "พร้อมรับรูป"

        reply_line_message(reply_token, reply_text)
        return

    # 2. ตรวจจับคำสั่งจบการนับ: #ok, # ok, ok, #จบ, จบ
    cleaned_lower = re.sub(r"^[#\s]+", "", text.lower()).strip()
    if cleaned_lower in ["ok", "จบ"]:
        session = get_session(source_id)
        if not session:
            reply_line_message(
                reply_token,
                "ยังไม่มีรายการที่เปิดสะสมยอดครับ\nพิมพ์ #รวม หรือ #รวม <ชื่อสาขา> เพื่อเริ่มต้นส่งรูปครับ",
            )
            return

        # หากยังมีรูปภาพที่กำลังประมวลผลค้างอยู่ใน ThreadPool ให้รอให้เสร็จก่อน (สูงสุด 12 วิ)
        wait_for_pending(source_id, timeout=12.0)

        # ดึงข้อมูลรอบล่าสุดหลังรูปประมวลผลเสร็จทั้งหมด
        session = get_session(source_id) or session
        slips = session.get("slips", [])
        branch = session.get("branch", "")
        session_date = session.get("date", datetime.now().strftime("%d/%m/%Y"))

        total_amount = 0.0
        slip_lines = []
        for i, s in enumerate(slips, 1):
            amt = float(s.get("amount", 0.0))
            total_amount += amt
            slip_lines.append(f"{i}. {amt:,.2f} บาท")

        branch_header = f"สาขา: {branch}\n" if branch else ""
        if slip_lines:
            detail_text = "\n\nรายการสลิปที่ตรวจพบ:\n" + "\n".join(slip_lines)
        else:
            detail_text = "\n\n(ไม่พบสลิปโอนเงินที่ส่งเข้ามาระหว่างนี้)"

        summary_msg = (
            f"📊 สรุปยอดเงินสลิป\n"
            f"-------------------------\n"
            f"{branch_header}"
            f"วันที่: {session_date}\n"
            f"จำนวนสลิป: {len(slips)} ใบ\n"
            f"💰 ยอดรวมทั้งหมด: {total_amount:,.2f} บาท"
            f"{detail_text}\n"
            f"-------------------------\n"
            f"บันทึกลง Google Sheets เรียบร้อยแล้วครับ"
        )

        clear_session(source_id)
        log_event("SESSION_FINISH", f"สรุปยอดสาขา: '{branch}' {len(slips)} ใบ ยอด {total_amount:,.2f} บาท")

        reply_line_message(reply_token, summary_msg)
        return


# ==========================================
# ฟังก์ชันประมวลผลรูปภาพแบบคู่ขนาน (Worker Task)
# ==========================================
PROMPT_FAST_SLIP = """คุณคือ AI อ่านสลิปโอนเงิน โปรดดึงข้อมูลในรูปแบบ JSON เท่านั้น (ห้ามใส่คำบรรยายอื่น):
{
  "category": "สลิปโอนเงิน",
  "amount": "ยอดเงินเฉพาะตัวเลข เช่น 500.00",
  "bank": "ชื่อธนาคาร",
  "sender": "ชื่อผู้โอน",
  "receiver": "ชื่อผู้รับ",
  "trans_date": "วันที่ทำรายการ",
  "trans_time": "เวลาทำรายการ",
  "ref_no": "เลขที่อ้างอิง/รหัสรายการ",
  "branch": "ชื่อสาขาหรือสถานที่ (หากมีระบุในสลิป)",
  "raw_text": "ข้อความสำคัญย่อๆ"
}"""

PROMPT_GENERAL = """คุณคือ AI วิเคราะห์รูปภาพและแยกหมวดหมู่สำหรับบันทึกลง Google Sheet
วิเคราะห์ภาพนี้และจัดให้อยู่ใน 1 ใน 4 หมวดหมู่นี้:
1. "สลิปโอนเงิน", 2. "ลงเวลาทำงาน", 3. "ส่งรายงาน", 4. "อื่นๆ"
ตอบเป็น JSON เท่านั้น:
{
  "category": "หมวดหมู่",
  "amount": "ยอดเงิน (กรณีสลิป)",
  "bank": "ธนาคาร",
  "sender": "ผู้โอน",
  "receiver": "ผู้รับ",
  "trans_date": "วันที่",
  "trans_time": "เวลา",
  "ref_no": "เลขอ้างอิง",
  "employee_name": "ชื่อพนักงาน (กรณีลงเวลา)",
  "work_date": "วันที่",
  "work_time": "เวลา",
  "work_type": "ประเภท",
  "location": "สถานที่/สาขา",
  "reporter_name": "ชื่อผู้รายงาน",
  "report_title": "หัวข้อ",
  "summary": "สรุปงาน",
  "branch": "ชื่อสาขา",
  "description": "คำอธิบายภาพ",
  "raw_text": "ข้อความในภาพ"
}"""


def process_image_worker(image_bytes: bytes, source_id: str, branch_name: str, is_in_session: bool):
    """ฟังก์ชันที่ทำงานใน Background Thread เพื่อประมวลผลรูปภาพพร้อมๆ กันหลายใบ"""
    try:
        # หากอยู่ใน session รวมยอดสลิป ให้ใช้ prompt สลิปแบบเร็วพิเศษ
        prompt = PROMPT_FAST_SLIP if is_in_session else PROMPT_GENERAL

        candidate_models = [
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-3.8-flash",
        ]

        response_text = ""
        for model_name in candidate_models:
            try:
                response = gemini_client.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                        prompt,
                    ],
                )
                if response and response.text:
                    response_text = response.text.strip()
                    break
            except Exception as err:
                continue

        parsed_data = None
        if response_text:
            clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", response_text, flags=re.MULTILINE).strip()
            try:
                parsed_data = json.loads(clean_json)
            except Exception:
                parsed_data = {
                    "category": "สลิปโอนเงิน" if is_in_session else "อื่นๆ",
                    "description": "ข้อความจากการอ่านภาพ",
                    "raw_text": response_text,
                }

        if not parsed_data:
            parsed_data = {
                "category": "อื่นๆ",
                "description": "ไม่พบข้อมูลในรูปภาพ",
                "raw_text": "ไม่มีข้อความ",
            }

        # กำหนดชื่อสาขา
        detected_branch = parsed_data.get("branch", "") if isinstance(parsed_data, dict) else ""
        final_branch = branch_name if branch_name else detected_branch
        parsed_data["branch"] = final_branch or "-"

        # หากเป็นสลิป และอยู่ใน session ให้สะสมยอดเงิน
        if parsed_data.get("category") == "สลิปโอนเงิน" and is_in_session:
            amt = clean_amount(parsed_data.get("amount"))
            ref = parsed_data.get("ref_no", "")
            add_slip_to_session(source_id, amt, ref)
            log_event("SLIP_ADDED", f"บันทึกยอดสลิป: {amt:,.2f} บาท ({final_branch})")

        # ส่งข้อมูลบันทึกลง Google Sheets
        send_to_google_sheet(parsed_data)

    except Exception as e:
        log_event("IMAGE_ERR", f"เกิดข้อผิดพลาดในการประมวลผลรูป: {e}")
    finally:
        remove_pending(source_id)


# ==========================================
# จัดการรูปภาพที่ส่งเข้ามา (รับทันที แล้วโยนให้ Worker Pool)
# ==
