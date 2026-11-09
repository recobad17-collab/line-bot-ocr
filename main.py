import json
import os
import re
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
)
from linebot.v3.webhooks import ImageMessageContent, MessageEvent

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

app = FastAPI(title="LINE Bot OCR to Google Sheets")


@app.get("/")
def read_root():
    return {
        "status": "LINE Bot OCR to Google Sheets is running!",
        "sheet_configured": bool(GOOGLE_SHEET_WEBAPP_URL),
    }


def send_to_google_sheet(data: dict):
    """ส่งข้อมูล JSON ไปบันทึกลง Google Sheets ผ่าน Apps Script Web App"""
    webhook_url = os.getenv("GOOGLE_SHEET_WEBAPP_URL")
    if not webhook_url:
        print("[Sheet] ยังไม่ได้กำหนด GOOGLE_SHEET_WEBAPP_URL ใน .env ข้อมูลไม่ได้ถูกส่งไป Google Sheets")
        print(f"[Sheet Data Preview]: {data}")
        return False

    try:
        # Google Apps Script Web App จะทำ redirect (302) จึงต้องตั้ง follow_redirects=True
        with httpx.Client(follow_redirects=True, timeout=15.0) as client:
            resp = client.post(webhook_url, json=data)
            print(f"[Sheet] บันทึกข้อมูลสำเร็จ ({data.get('category')}): {resp.status_code}")
            return True
    except Exception as e:
        print(f"[Sheet Error] ไม่สามารถส่งข้อมูลไป Google Sheet: {e}")
        return False


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


@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image_message(event):
    """ฟังก์ชันทำงานเมื่อผู้ใช้ส่งรูปภาพเข้ามา: อ่านรูป + แยกหมวดหมู่ + บันทึกลง Google Sheets (ไม่ตอบกลับ)"""
    message_id = event.message.id

    with ApiClient(configuration) as api_client:
        messaging_api_blob = MessagingApiBlob(api_client)

        try:
            # 1. ดึงข้อมูลไฟล์รูปภาพไบนารีจาก LINE Content API
            image_bytes = messaging_api_blob.get_message_content(message_id)

            # 2. ส่งรูปให้ Gemini วิเคราะห์และจำแนก 4 หมวดหมู่ พร้อมดึงข้อมูลเจาะจง
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
                    # กรณีโมเดลไม่ได้ตอบเป็น JSON มาตรฐาน ให้เก็บลงหมวดหมู่อื่นๆ
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

            # 3. ส่งข้อมูลไปบันทึกลง Google Sheets ตามหมวดหมู่ (ไม่ต้องตอบกลับใน LINE)
            send_to_google_sheet(parsed_data)
            try:
                print(f"[Processed] แยกหมวดหมู่ได้: {parsed_data.get('category')}")
            except Exception:
                pass

        except Exception as e:
            try:
                print(f"[Error] เกิดข้อผิดพลาดในการประมวลผลรูปภาพ: {e}")
            except Exception:
                pass

        # ไม่มีการเรียก reply_message เพื่อไม่ให้บอทส่งข้อความตอบกลับในแชท LINE


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
