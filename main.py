Conversation Log

ผมได้เข้าไปดูข้อมูลใน Google Sheets ของคุณแล้ว พบว่า ระบบบอทรับสลิปเข้ามาแล้วถึง 22 ใบอย่างสมบูรณ์แบบครับ! 👏

และผมได้ สร้างแท็บใหม่ชื่อ สรุปยอดสลิป (Dashboard) ใน Google Sheets ของคุณ
 ให้เรียบร้อยแล้ว โดยมีระบบคำนวณอัตโนมัติแบบ Real-time ดังนี้ครับ:

1. สิ่งที่สร้างไว้ให้ในแท็บ สรุปยอดสลิป:
การ์ดสรุปภาพรวมด้านบน (Real-time KPI):
จำนวนสลิปทั้งหมด: 22 ใบ
ยอดเงินรวมทั้งหมด: 2,430.00 บาท
ยอดเฉลี่ยต่อสลิป: 110.45 บาท
ตารางสรุปยอดแยกตามรายวัน:
มีระบบรวมยอดอัตโนมัติแยกตามวันที่ เมื่อสาขาส่งสลิปเข้ามา ยอดจะเพิ่มขึ้นทันทีโดยที่คุณไม่ต้องกดบวกเลขเอง
2. คำแนะนำเพิ่มเติมสำหรับการส่งสลิปหลายสาขาในสิ้นวัน:
แนวทาง A: สรุปแยกตาม "สาขา" (ถ้าแต่ละสาขาส่งเข้ามา)

หากต้องการให้สรุปแยกเป็นรายสาขาได้ (เช่น สาขา 1 ยอดเท่าไหร่, สาขา 2 ยอดเท่าไหร่) เราสามารถทำได้ 2 วิธี:

ให้ AI ดึงชื่อบัญชีผู้รับ/ผู้โอน หรือเลขสาขาที่ปรากฏบนสลิป
หรือให้พนักงานสาขาพิมพ์ชื่อสาขามาพร้อมรูป แล้วบันทึกแยกลงคอลัมน์ "สาขา" ในชีทเพื่อทำ Pivot Table สรุปแยกสาขาได้ทันที
แนวทาง B: ส่งข้อความสรุปยอดเข้ากลุ่ม LINE อัตโนมัติทุกสิ้นวัน (แนะนำมาก ⭐)

เราสามารถตั้งเวลาใน Google Apps Script ให้คำนวณยอดของวันนั้น แล้วส่งข้อความสรุปภาพรวมเข้ากลุ่ม LINE ทุกๆ สิ้นวัน (เช่น เวลา 20:00 น. หรือ 21:00 น.) เช่น:

text
📊 สรุปยอดสลิปประจำวัน: 09/11/2026
---------------------------------
• จำนวนสลิปที่ตรวจรับ: 22 ใบ
• ยอดเงินรวมทั้งหมด: 2,430.00 บาท
---------------------------------
ตรวจสอบรายการเต็มได้ที่: Google Sheets

(วิธีนี้สะดวกมาก หัวหน้างานหรือฝ่ายบัญชีไม่ต้องเปิดคอมดูชีทเลย รออ่านยอดสรุปสิ้นวันจากไลน์กลุ่มได้ทันที)

คุณสามารถเปิดดูแท็บ สรุปยอดสลิป ใน Google Sheets ได้ทันทีเลยครับ หากสนใจให้ทำระบบสรุปแจ้งเตือนสิ้นวันเข้า LINE แบบใน แนวทาง B เพิ่มเติม แจ้งเวลาที่ต้องการให้ส่งสรุปได้เลยครับ!

แก้ไขใหม่ ถ้าก่อนส่งจะพิมว่า #รวม 
แล้วส่งรูปให้ไปเรีอยๆ แต่ถ้าจบด้วย #ok ค่อยเอายอดเงินของรูประหว่างนี้มารวมกัน  
หรือถ้าลืมแล้วมีพิม #รวม เข้ามาสองรอบไม่ต้องสนใจอันเก่าให้เริ่มนับรูปจากอันนี้ จนถึง#ok
ถ้าใส่ #รวม อุดร  ก็ให้ระบุสาขาด้วยว่าเป็นยอดของอุดร ระบุวันที่ด้วย
โดยมากจะเป็นสลิปที่มีการโอนภายในวันเดียวกัน 
ถ้าใส่ #รวม ให้ตอบว่าพร้อมรับรูป 
ถ้าใส่ #รวม อุดร ให้ตอบว่าพร้อรับรูปสาขา อุดร

ปรับปรุงระบบใหม่ให้ตรงตามความต้องการครบทุกข้อเรียบร้อยแล้วครับ! 🎉

สรุปการทำงานของระบบใหม่:
เริ่มต้นนับสลิป:
พิมพ์ #รวม ➡️ บอทตอบ: พร้อมรับรูป
พิมพ์ #รวม อุดร ➡️ บอทตอบ: พร้อมรับรูปสาขา อุดร
(หากลืมแล้วพิมพ์ #รวม ซ้ำสองรอบ ระบบจะล้างรายการเดิมและเริ่มนับใหม่จากรอบล่าสุดทันที)
ระหว่างส่งรูป:
สามารถส่งรูปสลิปเข้ามาได้เรื่อยๆ โดยที่บอทจะไม่ส่งข้อความตอบมารบกวน
ระบบจะอ่านยอดเงินและสะสมไว้ในรอบนั้นๆ พร้อมบันทึกลง Google Sheets และระบุชื่อสาขาให้ด้วย
จบการนับและรวมยอดเงิน:
text
📊 สรุปยอดเงินสลิป
-------------------------
สาขา: อุดร
วันที่: 09/11/2026
จำนวนสลิป: 5 ใบ
💰 ยอดรวมทั้งหมด: 475.00 บาท
รายการสลิปที่ตรวจพบ:
1. 80.00 บาท
2. 80.00 บาท
3. 105.00 บาท
4. 130.00 บาท
5. 80.00 บาท
-------------------------
บันทึกลง Google Sheets เรียบร้อยแล้วครับ
พิมพ์ #ok (หรือ #OK) ➡️ บอทจะตอบกลับสรุปภาพรวมทันที เช่น:
สิ่งที่ต้องทำเพื่ออัปเดตระบบ (2 ขั้นตอนสั้นๆ):
ขั้นตอนที่ 1: อัปเดตไฟล์ main.py ขึ้น GitHub

เพื่อให้บอทบน Render ใช้งานโค้ดระบบใหม่:

เข้าไปที่ Repository ของคุณใน GitHub.com
คลิกที่ไฟล์ main.py -> คลิกไอคอน ดินสอ (Edit this file) (หรือกด Add file -> Upload files)
คัดลอกโค้ดจากไฟล์ main.py ในเครื่องของคุณไปวางทับ
กดปุ่มสีเขียว Commit changes (Render จะทำการตรวจจับและ Deploy อัปเดตให้อัตโนมัติใน 1 นาที)
ขั้นตอนที่ 2: อัปเดต Google Apps Script ใน Google Sheets

เพื่อบันทึกชื่อสาขาลงในช่อง "สาขา" (คอลัมน์ J ที่ผมเพิ่มไว้ให้):

เปิด Google Sheets ของคุณ
 -> เมนู ส่วนขยาย (Extensions) -> Apps Script
นำโค้ดนี้ไปวางทับโค้ดเดิม:
javascript
function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var timestamp = Utilities.formatDate(new Date(), "Asia/Bangkok", "yyyy-MM-dd HH:mm:ss");
    
    if (data.category === "สลิปโอนเงิน") {
      var sheet = ss.getSheetByName("สลิปโอนเงิน");
      sheet.appendRow([
        timestamp,
        data.amount || "-",
        data.bank || "-",
        data.sender || "-",
        data.receiver || "-",
        data.trans_date || "-",
        data.trans_time || "-",
        data.ref_no || "-",
        data.raw_text || "-",
        data.branch || "-"    // คอลัมน์ J: บันทึกชื่อสาขา
      ]);
    } else if (data.category === "ลงเวลาทำงาน") {
      var sheet = ss.getSheetByName("ลงเวลาทำงาน");
      sheet.appendRow([
        timestamp,
        data.employee_name || "-",
        data.work_date || "-",
        data.work_time || "-",
        data.work_type || "-",
        data.location || "-",
        data.raw_text || "-"
      ]);
    } else if (data.category === "ส่งรายงาน") {
      var sheet = ss.getSheetByName("ส่งรายงาน");
      sheet.appendRow([
        timestamp,
        data.reporter_name || "-",
        data.report_title || "-",
        data.summary || "-",
        data.report_date || "-",
        data.raw_text || "-"
      ]);
    } else {
      var sheet = ss.getSheetByName("อื่นๆ");
      sheet.appendRow([
        timestamp,
        data.description || "รูปภาพอื่นๆ",
        data.raw_text || "ไม่มีข้อความ"
      ]);
    }
    
    return ContentService.createTextOutput(JSON.stringify({status: "success"}))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({status: "error", message: error.toString()}))
      .setMimeType(ContentService.MimeType.JSON);
  }
}
กด บันทึก (ไอคอนแผ่นดิสก์) -> กด การทำให้ใช้งานได้ (Deploy) -> จัดการการทำให้ใช้งานได้ (Manage deployments) -> กดไอคอน ดินสอ (Edit) -> เลือกเวอร์ชัน: เวอร์ชันใหม่ (New version) -> กด ทำให้ใช้งานได้ (Deploy)

เมื่ออัปเดตเรียบร้อยแล้ว ลองทดสอบส่งคำสั่ง #รวม อุดร ในแชท LINE ได้เลยครับ!

ถ้าเป็นสาขาที่ไม่เคยมีให้เพิ่มเองอัตโนมัติ

ระบบรองรับการเพิ่มสาขาใหม่อัตโนมัติ 100% โดยไม่ต้องตั้งค่าล่วงหน้าเลยครับ! 🚀

ระบบถูกออกแบบให้มีความยืดหยุ่นสูง ดังนี้ครับ:

1. ไม่ต้องกำหนดรายชื่อสาขาไว้ล่วงหน้า

ไม่ว่าจะมีสาขาใหม่เปิด หรือใครพิมพ์ชื่อสาขาใดเข้ามา เช่น:

#รวม เชียงใหม่ ➡️ บอทจะตอบ: พร้อมรับรูปสาขา เชียงใหม่
#รวม สาขาบางนา ➡️ บอทจะตอบ: พร้อมรับรูปสาขา สาขาบางนา
#รวม Shop 09 ➡️ บอทจะตอบ: พร้อมรับรูปสาขา Shop 09

ระบบจะบันทึกชื่อสาขาใหม่นั้นลงในฐานข้อมูลและ Google Sheets ทันที

2. ใน Google Sheets มีตารางสรุปแยกสาขาให้อัตโนมัติ

ผมได้เพิ่มตาราง 🏢 สรุปยอดแยกตามสาขา ไว้ในแท็บ สรุปยอดสลิป
 ให้แล้วครับ:

ใช้สูตรอัตโนมัติ =UNIQUE(...) เมื่อมีสลิปของสาขาใหม่ส่งเข้ามา ชื่อสาขานั้นจะเด้งขึ้นมาในตารางสรุปทันที
คำนวณจำนวนสลิป และยอดรวมเงินของแต่ละสาขาให้อัตโนมัติ โดยที่คุณไม่ต้องมานั่งพิมพ์เพิ่มชื่อสาขาเองเลยครับ
3. กรณีไม่ได้พิมพ์ชื่อสาขา แต่ในสลิปมีระบุไว้

ผมได้เพิ่มคำสั่งให้ AI ช่วยสแกนดูชื่อสาขาหรือสถานที่บนตัวสลิปให้ด้วย หากพนักงานลืมพิมพ์ชื่อสาขาแต่บนสลิปมีระบุไว้ AI จะดึงมาบันทึกเป็นชื่อสาขาให้อัตโนมัติครับ

NOTE

อย่าลืมนำโค้ดใน main.py ที่อัปเดตใหม่ไปวางทับบน GitHub เพื่อให้ Render อัปเดตความสามารถใหม่นี้นะครับ!

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
สร้าง Google Form แจ้งซ่อมเครื่อง
08ส่งซ่อม
Updated Nov 5, 10:11 AM
Choosing Language For CCTV App
06
Updated Nov 3, 1:05 PM
Checking Attendance And Salary Files
05เงินเดือน
Updated Nov 3, 11:03 AM
