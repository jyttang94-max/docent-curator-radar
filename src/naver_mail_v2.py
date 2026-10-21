
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


def read_json(filename, default):
    path = ROOT / "data" / filename
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def escape(value):
    return html.escape(str(value or ""), quote=True)


def card(item):
    url = str(item.get("url", ""))
    if urlparse(url).scheme not in ("http", "https"):
        url = "#"

    return f"""
    <tr><td style="padding-bottom:14px">
      <table role="presentation" width="100%"
             cellpadding="0" cellspacing="0"
             style="border:1px solid #dce4eb">
        <tr><td style="padding:18px">
          <div style="font-size:12px;color:#60738a">
            {escape(item.get("institution"))}
            | 접수 확인 필요
          </div>

          <h3 style="font-size:17px;line-height:1.5;
                     color:#152b40;margin:10px 0">
            {escape(item.get("title"))}
          </h3>

          <div style="font-size:14px;line-height:1.7;
                      color:#52657c;margin-bottom:15px">
            접수 상태: 미검증<br>
            마감일: 미확인<br>
            교육 일정 및 비용: 미확인
          </div>

          <table role="presentation" width="100%"
                 cellpadding="0" cellspacing="0">
            <tr>
              <td bgcolor="#152b40" align="center">
                <a href="{escape(url)}"
                   style="display:block;padding:15px;
                          color:#ffffff;text-decoration:none;
                          font-size:15px;font-weight:bold">
                  공식 공고 확인 →
                </a>
              </td>
            </tr>
          </table>
        </td></tr>
      </table>
    </td></tr>
    """


def section(title, content):
    return f"""
    <tr>
      <td style="padding:22px 0 12px">
        <h2 style="margin:0;font-size:19px;color:#152b40">
          {escape(title)}
        </h2>
      </td>
    </tr>
    {content}
    """


def empty(message):
    return f"""
    <tr>
      <td style="background:#f2f5f8;padding:15px;
                 font-size:14px;line-height:1.6;
                 color:#52657c">
        {escape(message)}
      </td>
    </tr>
    """


def build_email():
    changes = read_json("latest_changes.json", [])
    status = read_json("collection_status.json", {})

    if (
        not isinstance(changes, list)
        or not isinstance(status, dict)
        or not status.get("sources")
    ):
        raise ValueError("Missing or invalid collector data")

    checked = datetime.fromisoformat(
        status["checked_at"].replace("Z", "+00:00")
    )

    if datetime.now(timezone.utc) - checked > timedelta(hours=26):
        raise ValueError("Collection data is older than 26 hours")

    sources = status["sources"]
    success = sum(
        source.get("status") == "success"
        for source in sources
    )

    if success == 0:
        raise ValueError("No successful collection sources")

    # 동일 URL 중복 제거
    unique = {
        item["url"]: item
        for item in changes
        if isinstance(item, dict) and item.get("url")
    }

    items = list(unique.values())

    # 모집 및 교육 관련 제목 우선
    terms = ("모집", "교육생", "양성", "교육과정", "아카데미")

    items.sort(
        key=lambda item: (
            not any(
                word in str(item.get("title", ""))
                for word in terms
            ),
            str(item.get("title", "")),
        )
    )

    selected = items[:10]

    today = datetime.now(KST).strftime("%Y.%m.%d")
    checked_kst = checked.astimezone(KST).strftime(
        "%m.%d %H:%M"
    )

    subject = (
        f"[ART FIELD NOTES] {today} "
        f"| 확인 필요 {len(items)}건"
    )

    cards = (
        "".join(card(item) for item in selected)
        if selected
        else empty("새로운 변경 후보가 없습니다.")
    )

    body = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport"
        content="width=device-width, initial-scale=1">

  <style>
    @media only screen and (max-width:600px) {{
      .outer {{
        width:100%!important;
      }}
      .pad {{
        padding:18px 16px!important;
      }}
      .hero {{
        font-size:24px!important;
      }}
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
       style="width:100%;max-width:680px;
              background:#ffffff">

  <tr>
    <td class="pad" bgcolor="#152b40"
        style="padding:30px 28px">

      <div style="font-size:11px;color:#b8cbdc">
        DOCENT &amp; CURATOR OPPORTUNITIES
      </div>

      <h1 class="hero"
          style="font-size:29px;line-height:1.2;
                 margin:10px 0;color:#ffffff">
        ART FIELD NOTES
      </h1>

      <div style="font-size:14px;color:#d7e2ea">
        도슨트, 큐레이터 교육 및 활동 모집 정보
        <br>{today}
      </div>
    </td>
  </tr>

  <tr>
    <td class="pad" style="padding:26px 28px">

      <h2 style="font-size:20px;color:#152b40">
        오늘의 모집 현황
      </h2>

      <table role="presentation" width="100%"
             cellpadding="0" cellspacing="0">
        <tr>
          <td width="33%" align="center"
              bgcolor="#f1f4f7"
              style="padding:13px 2px">
            <b style="font-size:24px">0</b><br>
            <span style="font-size:11px">
              접수 확인
            </span>
          </td>

          <td width="34%" align="center"
              bgcolor="#e9eff4"
              style="padding:13px 2px">
            <b style="font-size:24px">
              {len(items)}
            </b><br>
            <span style="font-size:11px">
              변경 후보
            </span>
          </td>

          <td width="33%" align="center"
              bgcolor="#f1f4f7"
              style="padding:13px 2px">
            <b style="font-size:24px">
              {len(sources) - success}
            </b><br>
            <span style="font-size:11px">
              접속 실패
            </span>
          </td>
        </tr>
      </table>

      <p style="background:#fff4e3;padding:13px;
                font-size:13px;line-height:1.6;
                color:#795723">
        현재 수집 데이터는 접수 기간, 비용,
        교육 요일을 검증하지 않습니다.
        미검증 후보를 접수 중으로 표시하지 않습니다.
      </p>

      <table role="presentation" width="100%"
             cellpadding="0" cellspacing="0">

        {section(
            "01. NOW OPEN",
            empty("현재 접수 중으로 검증된 공고 없음")
        )}

        {section("02. CHECK FIRST", cards)}

        {section(
            "03. WEEKEND & EVENING",
            empty("교육 요일 및 시간 검증 후 게재 예정")
        )}

        {section(
            "04. RADAR WATCH",
            empty("다음 모집 일정은 별도 검증 후 게재 예정")
        )}

      </table>

      <p style="font-size:12px;line-height:1.6;
                color:#68788c">
        수집 시각: {checked_kst} KST<br>
        접속 성공: {success}/{len(sources)}<br>
        상위 {len(selected)}건 표시
        <br><br>
        신규 후보는 실제 신청 가능한 공고와
        다를 수 있습니다.
      </p>

    </td>
  </tr>

  <tr>
    <td bgcolor="#e8edf2"
        style="padding:20px;text-align:center;
               font-size:12px;color:#60738a">
      ART FIELD NOTES
      — DOCENT &amp; CURATOR RADAR
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>
"""

    return subject, body


def main():
    subject, body = build_email()

    preview = ROOT / "reports" / "mail_preview_v2.html"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(body, encoding="utf-8")

    print("Preview generated:", preview)

    # 기본값은 미리보기만 생성
    if os.getenv("SEND_EMAIL") != "true":
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
        "ART FIELD NOTES HTML 뉴스레터를 확인해 주세요."
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
