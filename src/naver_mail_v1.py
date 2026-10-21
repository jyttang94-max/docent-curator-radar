
import html
import json
import os
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
KST = ZoneInfo("Asia/Seoul")


def read_json(filename, default):
    path = DATA / filename
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def safe_url(url):
    value = str(url or "")
    if urlparse(value).scheme not in ("http", "https"):
        return "#"
    return html.escape(value, quote=True)


def build_email():
    changes = read_json("latest_changes.json", [])
    status = read_json("collection_status.json", {})

    if not isinstance(changes, list):
        raise ValueError("Invalid latest_changes.json")
    if not isinstance(status, dict) or not status.get("sources"):
        raise ValueError("Collection status is missing")

    sources = status["sources"]
    successes = sum(
        s.get("status") == "success" for s in sources
    )
    failures = [
        s for s in sources
        if s.get("status") != "success"
    ]

    # 동일 URL의 중복 변경을 한 건으로 정리
    unique = {}
    for item in changes:
        url = item.get("url")
        if url:
            unique[url] = item

    # 모집 가능 여부를 확인한 공고가 아니라
    # 단순 수집 후보임을 명확히 표시
    rows = []
    for item in list(unique.values())[:60]:
        name = html.escape(item.get("institution", ""))
        title = html.escape(item.get("title", ""))
        url = safe_url(item.get("url"))
        change = html.escape(item.get("change", ""))

        rows.append(
            '<tr><td style="padding:12px;'
            'border-bottom:1px solid #eee">'
            f'<strong>{name}</strong><br>'
            f'<a href="{url}">{title}</a><br>'
            f'<small>{change} | 접수 여부 미검증</small>'
            '</td></tr>'
        )

    if not rows:
        rows.append(
            '<tr><td style="padding:16px">'
            '이번 수집에서 신규 또는 변경 후보가 없습니다.'
            '</td></tr>'
        )

    failed_names = ", ".join(
        html.escape(s.get("institution", ""))
        for s in failures
    ) or "없음"

    today = datetime.now(KST).strftime("%Y.%m.%d")
    subject = (
        f"[도슨트 레이더] {today} "
        f"신규 및 변경 후보 {len(unique)}건"
    )

    body = f"""
    <html>
    <body style="margin:0;background:#f4f6f8;
                 font-family:Arial,sans-serif;color:#253047">
      <div style="max-width:680px;margin:24px auto;
                  background:white;padding:28px">
        <h1 style="color:#152d50">
          DOCENT & CURATOR RADAR
        </h1>
        <p>{today} 자동 수집 보고</p>
        <p>
          접속 성공: {successes}/{len(sources)}<br>
          신규 및 변경 후보: {len(unique)}건
        </p>
        <p style="background:#fff4dc;padding:12px">
          주의: 아래 목록은 자동 수집한 후보입니다.
          모집 중 여부, 접수 마감일, 교육 일정은
          아직 검증되지 않았습니다.
        </p>
        <h2>신규 및 변경 후보</h2>
        <table style="width:100%;border-collapse:collapse">
          {''.join(rows)}
        </table>
        <h2>접속 실패 기관</h2>
        <p>{failed_names}</p>
        <p style="font-size:12px;color:#777">
          GitHub 자동 수집 결과를 바탕으로 생성된 메일입니다.
        </p>
      </div>
    </body>
    </html>
    """

    return subject, body


def main():
    sender = os.environ["NAVER_EMAIL"].strip()
    password = os.environ["NAVER_PASSWORD"]
    recipient = os.environ["ALERT_EMAIL"].strip()

    if not sender or not password or not recipient:
        raise ValueError("Email credentials are missing")

    subject, body = build_email()

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(
        "도슨트 레이더 수집 결과입니다. "
        "HTML 메일을 확인해주세요."
    )
    message.add_alternative(body, subtype="html")

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(
        "smtp.naver.com", 465,
        context=context, timeout=30
    ) as smtp:
        smtp.login(sender, password)
        smtp.send_message(message)

    print("Mail sent successfully")


if __name__ == "__main__":
    main()
