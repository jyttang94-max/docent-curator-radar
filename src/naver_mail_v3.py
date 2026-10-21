
import html
import json
import os
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
KST = ZoneInfo("Asia/Seoul")


def esc(value):
    return html.escape(str(value or ""), quote=True)


def read_json(filename):
    path = ROOT / "data" / filename
    return json.loads(path.read_text(encoding="utf-8"))


def card(item):
    url = str(item.get("url") or "")
    if urlparse(url).scheme not in ("http", "https"):
        return ""

    status = item.get("status", "check_required")
    labels = {
        "open_candidate": "접수 기간 내",
        "upcoming": "접수 예정",
        "check_required": "확인 필요",
    }

    schedule = item.get("schedule") or {}
    days = ", ".join(schedule.get("days") or [])
    times = ", ".join(
        schedule.get("time_candidates") or []
    )

    details = [
        ("접수 상태", labels.get(status, "확인 필요")),
        ("접수 시작", item.get("start_date") or "확인 필요"),
        ("접수 마감", item.get("deadline") or "확인 필요"),
        ("교육 요일", days or "확인 필요"),
        ("시간 정보", times or "확인 필요"),
        ("교육비", item.get("cost") or "확인 필요"),
    ]

    detail_html = "".join(
        f'<div style="margin:5px 0">'
        f'<b>{esc(label)}</b>: {esc(value)}</div>'
        for label, value in details
    )

    return f"""
    <tr><td style="padding-bottom:14px">
      <table role="presentation" width="100%"
        cellpadding="0" cellspacing="0"
        style="border:1px solid #dce4eb">
        <tr><td style="padding:18px">
          <div style="font-size:12px;color:#60738a">
            {esc(item.get("institution"))}
            | {esc(labels.get(status, "확인 필요"))}
          </div>
          <h3 style="font-size:17px;line-height:1.5;
            color:#152b40;margin:10px 0">
            {esc(item.get("title"))}
          </h3>
          <div style="font-size:13px;line-height:1.7;
            color:#52657c;margin-bottom:16px">
            {detail_html}
          </div>
          <table role="presentation" width="100%"
            cellpadding="0" cellspacing="0">
            <tr><td bgcolor="#152b40" align="center">
              <a href="{esc(url)}"
                style="display:block;padding:15px;
                color:#ffffff;text-decoration:none;
                font-size:15px;font-weight:bold">
                공식 공고 확인 →
              </a>
            </td></tr>
          </table>
        </td></tr>
      </table>
    </td></tr>
    """


def section(title, items, empty_text):
    contents = (
        "".join(card(item) for item in items)
        if items
        else f"""<tr><td style="padding:15px;
          background:#f2f5f8;color:#52657c;
          font-size:14px">{esc(empty_text)}</td></tr>"""
    )
    return f"""
    <tr><td style="padding:24px 0 12px">
      <h2 style="margin:0;font-size:19px;color:#152b40">
        {esc(title)}
      </h2>
    </td></tr>
    {contents}
    """


def build_email():
    data = read_json("verified_v3.json")
    checked = datetime.fromisoformat(
        data["checked_at"].replace("Z", "+00:00")
    )

    if datetime.now(timezone.utc) - checked > timedelta(hours=26):
        raise ValueError("Verification data is stale")

    items = data.get("items", [])
    if not isinstance(items, list):
        raise ValueError("Invalid verification data")

    # 중복 URL 제거
    unique = {}
    for item in items:
        if isinstance(item, dict) and item.get("url"):
            unique[item["url"]] = item

    records = list(unique.values())

    # 마감 공고는 메일에서 제외
    open_items = [
        x for x in records
        if x.get("status") == "open_candidate"
    ]
    upcoming = [
        x for x in records
        if x.get("status") == "upcoming"
    ]
    unknown = [
        x for x in records
        if x.get("status") == "check_required"
    ]

    open_items.sort(key=lambda x: x.get("deadline") or "9999")
    upcoming.sort(key=lambda x: x.get("start_date") or "9999")

    # 요일 정보가 있다는 이유만으로 실제 교육 시간 확정은 아님
    weekend = [
        x for x in open_items
        if any(
            day in (x.get("schedule") or {}).get("days", [])
            for day in ("토요일", "일요일", "주말")
        )
    ]

    today = datetime.now(KST).strftime("%Y.%m.%d")
    subject = (
        f"[ART FIELD NOTES] {today} | "
        f"접수 기간 내 {len(open_items)}건, "
        f"접수 예정 {len(upcoming)}건"
    )

    content = "".join([
        section(
            "01. NOW OPEN",
            open_items[:8],
            "모집 기간이 확인된 접수 중 후보가 없습니다.",
        ),
        section(
            "02. CHECK FIRST",
            unknown[:6],
            "추가 확인이 필요한 후보가 없습니다.",
        ),
        section(
            "03. WEEKEND & EVENING",
            weekend[:5],
            "주말 교육 관련 정보가 확인되지 않았습니다.",
        ),
        section(
            "04. RADAR WATCH",
            upcoming[:6],
            "접수 예정 공고가 확인되지 않았습니다.",
        ),
    ])

    body = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport"
 content="width=device-width,initial-scale=1">
<style>
@media only screen and (max-width:600px) {{
  .outer {{width:100%!important}}
  .pad {{padding:18px 16px!important}}
  .hero {{font-size:24px!important}}
}}
</style>
</head>
<body style="margin:0;padding:0;background:#edf1f5;
 -webkit-text-size-adjust:100%">
<table role="presentation" width="100%"
 cellpadding="0" cellspacing="0"
 style="background:#edf1f5">
<tr><td align="center">
<table role="presentation" class="outer"
 width="680" cellpadding="0" cellspacing="0"
 style="width:100%;max-width:680px;background:#ffffff">
<tr><td class="pad" bgcolor="#152b40"
 style="padding:30px 28px">
 <div style="font-size:11px;color:#b8cbdc">
 DOCENT &amp; CURATOR OPPORTUNITIES
 </div>
 <h1 class="hero" style="font-size:29px;
 line-height:1.2;margin:10px 0;color:#ffffff">
 ART FIELD NOTES
 </h1>
 <div style="font-size:14px;color:#d7e2ea">
 도슨트, 큐레이터 교육 및 활동 모집 정보<br>
 {today}
 </div>
</td></tr>
<tr><td class="pad" style="padding:26px 28px">
 <h2 style="font-size:20px;color:#152b40">
 오늘의 모집 현황
 </h2>
 <table role="presentation" width="100%"
 cellpadding="0" cellspacing="0">
 <tr>
 <td width="33%" bgcolor="#f1f4f7"
 align="center" style="padding:14px 2px">
 <b style="font-size:24px">{len(open_items)}</b><br>
 <span style="font-size:11px">접수 기간 내</span>
 </td>
 <td width="34%" bgcolor="#e9eff4"
 align="center" style="padding:14px 2px">
 <b style="font-size:24px">{len(upcoming)}</b><br>
 <span style="font-size:11px">접수 예정</span>
 </td>
 <td width="33%" bgcolor="#f1f4f7"
 align="center" style="padding:14px 2px">
 <b style="font-size:24px">{len(unknown)}</b><br>
 <span style="font-size:11px">확인 필요</span>
 </td>
 </tr></table>
 <p style="padding:13px;background:#fff4e3;
 font-size:13px;line-height:1.6;color:#795723">
 모집 기간은 공고 본문에서 자동 추출했습니다.
 접수 기간 내 공고도 실제 신청 가능 여부와
 조기 마감 여부는 공식 페이지에서 확인해 주세요.
 교육 요일 및 비용은 자동 추출된 참고 정보입니다.
 </p>
 <table role="presentation" width="100%"
 cellpadding="0" cellspacing="0">
 {content}
 </table>
 <p style="font-size:12px;line-height:1.6;
 color:#68788c">
 검증 시각:
 {checked.astimezone(KST).strftime("%m.%d %H:%M")} KST<br>
 전체 확인: {len(records)}건<br>
 마감 공고는 메일에서 제외했습니다.
 </p>
</td></tr>
<tr><td bgcolor="#e8edf2"
 style="padding:20px;text-align:center;
 font-size:12px;color:#60738a">
 ART FIELD NOTES — DOCENT &amp; CURATOR RADAR
</td></tr>
</table>
</td></tr></table>
</body></html>"""

    return subject, body


def main():
    subject, body = build_email()

    preview = ROOT / "reports" / "mail_preview_v3.html"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(body, encoding="utf-8")
    print("Preview generated:", preview)

    if os.getenv("SEND_EMAIL", "").lower() != "true":
        print("PREVIEW ONLY: no email sent")
        return

    sender = os.environ["NAVER_EMAIL"].strip()
    recipient = os.environ["ALERT_EMAIL"].strip()
    password = os.environ["NAVER_PASSWORD"]

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(
        "ART FIELD NOTES 뉴스레터를 HTML로 확인해 주세요."
    )
    message.add_alternative(body, subtype="html")

    with smtplib.SMTP_SSL(
        "smtp.naver.com",
        465,
        context=ssl.create_default_context(),
        timeout=30,
    ) as smtp:
        smtp.login(sender, password)
        smtp.send_message(message)

    print("Email submitted to NAVER SMTP")


if __name__ == "__main__":
    main()
