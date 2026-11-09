import json
import os
import re
import sqlite3
import sys
from datetime import datetime

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

app = FastAPI(title="LINE Bot OCR to Google Sheets with Batching")

# ==========================================
# ระบบจัดการ Session สะสมยอดสลิป (SQLite)
# ==========================================
DB_PATH = "sessions.db"


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
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
    with sqlite3.connect(DB_PATH) as conn:
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
    with sqlite3.connect(DB_PATH) as conn:
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
    """เพิ่มข้อมูลสลิปเข้าไปใน Session สะสม"""
    session = get_session(source_id)
    if not session:
        return False

    slips = session["slips"]
    slips.append({"amount": amount, "ref_no": ref_no})

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE slip_sessions SET slips_json = ?, updated_at = CURRENT_TIMESTAMP WHERE source_id = ?",
            (json.dumps(slips, ensure_ascii=False), source_id),
        )
        conn.commit()
    return True


def clear_session(source_id: str):
    """ลบ Session ออกเมื่อสรุปยอดเสร็จสิ้น (#ok)"""
    with sqlite3.connect(DB_PATH) as conn:
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
    except Exception as e:
        print(f"[LINE Reply Error] {e}")


def send_to_google_sheet(data: dict):
    """ส่งข้อมูล JSON ไปบันทึกลง Google Sheets ผ่าน Apps Script Web App"""
    webhook_url = os.getenv("GOOGLE_SHEET_WEBAPP_URL")
    if not webhook_url:
        print("[Sheet] ยังไม่ได้กำหนด GOOGLE_SHEET_WEBAPP_URL ใน .env")
        return False

    try:
        with httpx.Client(follow_redirects=True, timeout=15.0) as client:
            resp = client.post(webhook_url, json=data)
            print(f"[Sheet] บันทึกข้อมูลสำเร็จ ({data.get('category')}): {resp.status_code}")
            return True
    except Exception as e:
        print(f"[Sheet Error] ไม่สามารถส่งข้อมูลไป Google Sheet: {e}")
        return False


@app.get("/")
def read_root():
    return {
        "status": "LINE Bot OCR to Google Sheets with Batching is running!",
        "sheet_configured": bool(GOOGLE_SHEET_WEBAPP_URL),
    }


@app.post("/callback")
async def callback(request: Request, x_line_signature: str = Header(None)):
    """รับ Webhook event จาก LINE Platform"""
    if x_line_signature is None:
        raise HTTPException(status_code=400, detail="Missing X-Line-Signature")

    body = await request.body()
    try:
        handler.handle(body.decode("utf-8"), x_line_signature)
    except InvalidSignatureError:
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

    # 1. ตรวจจับคำสั่ง #รวม หรือ #รวม <ชื่อสาขา>
    # รองรับทั้ง #รวมอุดร หรือ #รวม อุดร
    match_sum = re.match(r"^#รวม(?:\s*(.+))?$", text, re.IGNORECASE)
    if match_sum:
        branch = match_sum.group(1).strip() if match_sum.group(1) else ""
        # เริ่มนับใหม่ทันที (ถ้ามี session เก่าค้างอยู่จะถูกล้างทิ้ง)
        start_session(source_id, branch)

        if branch:
            reply_text = f"พร้อมรับรูปสาขา {branch}"
        else:
            reply_text = "พร้อมรับรูป"

        reply_line_message(reply_token, reply_text)
        return

    # 2. ตรวจจับคำสั่งจบการนับ #ok หรือ #OK หรือ #จบ
    if text.lower() in ["#ok", "#จบ"]:
        session = get_session(source_id)
        if not session:
            reply_line_message(
                reply_token,
                "ยังไม่มีรายการที่เปิดสะสมยอดครับ\nพิมพ์ #รวม หรือ #รวม <ชื่อสาขา> เพื่อเริ่มต้นส่งรูปครับ",
            )
            return

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

        # เคลียร์ session จบการทำงาน
        clear_session(source_id)

        reply_line_message(reply_token, summary_msg)
        return


# ==========================================
# จัดการรูปภาพที่ส่งเข้ามา
# ==========================================
@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image_message(event):
    """อ่านรูป + แยกหมวดหมู่ + ถ้ามี session สะสมยอด ให้เก็บยอดไว้ตอบตอน #ok"""
    message_id = event.message.id
    source_id = get_source_id(event)

    # ตรวจสอบว่าห้องแชทนี้กำลังเปิด session สะสมยอดสลิปอยู่หรือไม่
    current_session = get_session(source_id)
    branch_name = current_session.get("branch", "") if current_session else ""

    with ApiClient(configuration) as api_client:
        messaging_api_blob = MessagingApiBlob(api_client)

        try:
            # 1. ดึงไฟล์รูปภาพจาก LINE Content API
            image_bytes = messaging_api_blob.get_message_content(message_id)

            # 2. ส่งรูปให้ Gemini วิเคราะห์และจำแนก 4 หมวดหมู่
            prompt = """คุณคือ AI ผู้ช่วยวิเคราะห์รูปภาพและแยกหมวดหมู่สำหรับบันทึกลง Google Sheet
วิเคราะห์ภาพนี้และจัดให้อยู่ใน 1 ใน 4 หมวดหมู่นี้เท่านั้น:
1. "สลิปโอนเงิน" (สลิปธนาคาร, หลักฐานการโอนเงิน)
2. "ลงเวลาทำงาน" (หน้าจอแอพตอกบัตร, ลงเวลาเข้า-ออกงาน, สแกนนิ้ว, ป้ายเวลา)
3. "ส่งรายงาน" (รายงานการปฏิบัติงาน, เอกสารสรุปงาน, ภาพถ่ายงานพร้อมบันทึกข้อความ)
4. "อื่นๆ" (ภาพที่ไม่เข้าข่าย 3 หมวดหมู่ข้างต้น เช่น รูปถ่ายทั่วไป, รูปวิว, รูปที่ไม่เกี่ยวข้อง, หรือภาพที่ไม่มีข้อความ)

โปรดตอบเป็น JSON เท่านั้น (ไม่ต้องใส่ markdown code fence อื่นใด) โดยมีโครงสร้างดังนี้:

ถ้าเป็น "สลิปโอนเงิน":
{
  "category": "สลิปโอนเงิน",
  "amount": "ยอดเงิน (เฉพาะตัวเลข เช่น 500.00)",
  "bank": "ธนาคารหรือผู้ให้บริการ",
  "sender": "ชื่อผู้โอน/บัญชีผู้โอน",
  "receiver": "ชื่อผู้รับ/บัญชีผู้รับ",
  "trans_date": "วันที่ทำรายการ",
  "trans_time": "เวลาทำรายการ",
  "ref_no": "เลขที่อ้างอิง/รหัสรายการ",
  "raw_text": "ข้อความสำคัญทั้งหมดที่อ่านได้"
}

ถ้าเป็น "ลงเวลาทำงาน":
{
  "category": "ลงเวลาทำงาน",
  "employee_name": "ชื่อพนักงาน",
  "work_date": "วันที่",
  "work_time": "เวลา",
  "work_type": "ประเภท (เช่น เข้างาน, ออกงาน, OT)",
  "location": "สถานที่หรือสาขา (ถ้ามี)",
  "raw_text": "ข้อความสำคัญทั้งหมดที่อ่านได้"
}

ถ้าเป็น "ส่งรายงาน":
{
  "category": "ส่งรายงาน",
  "reporter_name": "ชื่อผู้ส่งรายงาน/พนักงาน",
  "report_title": "หัวข้อรายงาน",
  "summary": "สรุปเนื้อหาของรายงาน",
  "report_date": "วันที่",
  "raw_text": "ข้อความสำคัญทั้งหมดที่อ่านได้"
}

ถ้าเป็น "อื่นๆ":
{
  "category": "อื่นๆ",
  "description": "คำอธิบายภาพสั้นๆ ว่าเป็นภาพอะไร",
  "raw_text": "ข้อความที่พบในภาพ (หากไม่มีข้อความให้ใส่ 'ไม่มีข้อความ')"
}
"""

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
                    print(f"Model {model_name} failed: {err}")
                    continue

            # ถอดรหัส JSON จากคำตอบของ Gemini
            parsed_data = None
            if response_text:
                clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", response_text, flags=re.MULTILINE).strip()
                try:
                    parsed_data = json.loads(clean_json)
                except Exception:
                    parsed_data = {
                        "category": "อื่นๆ",
                        "description": "ข้อความจากการอ่านภาพ",
                        "raw_text": response_text,
                    }

            if not parsed_data:
                parsed_data = {
                    "category": "อื่นๆ",
                    "description": "ไม่พบข้อมูลในรูปภาพ",
                    "raw_text": "ไม่มีข้อความ",
                }

            # แนบชื่อสาขาลงในข้อมูล
            parsed_data["branch"] = branch_name

            # 3. ถ้าเป็นสลิปโอนเงิน และกำลังอยู่ใน session #รวม ให้นับยอดเงินสะสมไว้
            if parsed_data.get("category") == "สลิปโอนเงิน" and current_session:
                amt = clean_amount(parsed_data.get("amount"))
                ref = parsed_data.get("ref_no", "")
                add_slip_to_session(source_id, amt, ref)

            # 4. ส่งข้อมูลไปบันทึกลง Google Sheets
            send_to_google_sheet(parsed_data)

            try:
                print(f"[Processed] แยกหมวดหมู่ได้: {parsed_data.get('category')} (สาขา: {branch_name or '-'})")
            except Exception:
                pass

        except Exception as e:
            try:
                print(f"[Error] เกิดข้อผิดพลาดในการประมวลผลรูปภาพ: {e}")
            except Exception:
                pass

        # ระหว่างส่งรูป ไม่ตอบกลับข้อความใดๆ ให้ส่งรูปได้ต่อเนื่อง


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
