import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "reports" / "art_field_v4_preview.html"

def main():
    if not HTML.is_file():
        raise FileNotFoundError("V4 HTML preview missing")
    sender = os.environ["NAVER_EMAIL"].strip()
    recipient = os.environ["ALERT_EMAIL"].strip()
    password = os.environ["NAVER_PASSWORD"]
    if not sender or not recipient or not password:
        raise ValueError("Missing SMTP configuration")
    subject = "[ART FIELD NOTES] V4 이메일 발송 테스트 " + datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y.%m.%d")
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content("ART FIELD NOTES V4 발송 테스트입니다. 공고 상태는 공식 페이지에서 확인해 주세요.")
    msg.add_alternative(HTML.read_text(encoding="utf-8"), subtype="html")
    with smtplib.SMTP_SSL("smtp.naver.com", 465, context=ssl.create_default_context(), timeout=30) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)
    print("V4 test email submitted to NAVER SMTP")

if __name__ == "__main__":
    main()
