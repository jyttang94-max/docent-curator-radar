
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
KST = ZoneInfo("Asia/Seoul")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ArtFieldRadar/3.0)"
}

DATE_PATTERN = re.compile(
    r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})"
)

RANGE_PATTERN = re.compile(
    r"(20\d{2}\s*[.\-/년]\s*\d{1,2}\s*[.\-/월]\s*\d{1,2})"
    r"\s*(?:일)?\s*(?:~|∼|～|부터|—|–)\s*"
    r"(20\d{2}\s*[.\-/년]\s*\d{1,2}\s*[.\-/월]\s*\d{1,2})"
)

RECRUITMENT_LABELS = (
    "접수기간", "접수 기간", "신청기간", "신청 기간",
    "모집기간", "모집 기간", "지원기간", "지원 기간",
)

CLOSED_TERMS = (
    "접수마감", "모집마감", "신청마감",
    "접수 종료", "모집 종료", "신청 종료",
)

DAY_TERMS = (
    "월요일", "화요일", "수요일", "목요일",
    "금요일", "토요일", "일요일",
    "주말", "평일", "온라인",
)

def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return default


def parse_date(value):
    match = DATE_PATTERN.search(value)
    if not match:
        return None
    try:
        return date(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
        )
    except ValueError:
        return None


def fetch_page(session, url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Unsupported URL scheme")

    response = session.get(url, timeout=15)
    response.raise_for_status()

    content_type = response.headers.get(
        "Content-Type", ""
    ).lower()

    if "html" not in content_type:
        raise ValueError("Not an HTML page")

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    title = (
        soup.title.get_text(" ", strip=True)
        if soup.title else ""
    )
    text = soup.get_text(" ", strip=True)

    return title, re.sub(r"\s+", " ", text)


def extract_recruitment_period(text):
    """
    모집/신청/접수 라벨 인근에서 명시적 연도 포함
    시작일과 종료일을 찾는다.
    """
    for label in RECRUITMENT_LABELS:
        for match in re.finditer(
            re.escape(label), text, re.IGNORECASE
        ):
            snippet = text[match.end():match.end() + 180]
            found = RANGE_PATTERN.search(snippet)

            if not found:
                continue

            start = parse_date(found.group(1))
            end = parse_date(found.group(2))

            if start and end and start <= end:
                return start, end, snippet[:160]

    return None, None, ""


def extract_schedule(text):
    """
    요일 정보는 모집 공고 본문에 등장한 단어만
    참고 정보로 저장한다.
    """
    days = [term for term in DAY_TERMS if term in text]

    times = re.findall(
        r"(?:오전|오후)?\s*\d{1,2}:\d{2}"
        r"\s*(?:~|∼|～|-)\s*"
        r"(?:오전|오후)?\s*\d{1,2}:\d{2}",
        text,
    )

    return {
        "days": days[:7],
        "time_candidates": times[:5],
    }


def extract_cost(text):
    patterns = [
        r"(?:교육비|수강료|참가비|수강 비용)"
        r"\s*[:：]?\s*(무료|무상)",
        r"(?:교육비|수강료|참가비|수강 비용)"
        r"\s*[:：]?\s*([\d,]+\s*원)",
    ]

    for pattern in patterns:
        found = re.search(pattern, text)
        if found:
            return found.group(1)

    return None


def verify(item, session, today):
    result = {
        "id": item.get("id"),
        "institution": item.get("institution"),
        "title": item.get("title"),
        "url": item.get("url"),
        "source_url": item.get("source_url"),
        "status": "check_required",
        "start_date": None,
        "deadline": None,
        "schedule": {},
        "cost": None,
        "evidence": "",
        "error": None,
        "verified_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    try:
        page_title, text = fetch_page(
            session, item.get("url", "")
        )

        start, end, evidence = extract_recruitment_period(
            text
        )

        result["page_title"] = page_title
        result["schedule"] = extract_schedule(text)
        result["cost"] = extract_cost(text)

        if start and end:
            result["start_date"] = start.isoformat()
            result["deadline"] = end.isoformat()
            result["evidence"] = evidence

            if today < start:
                result["status"] = "upcoming"
            elif today > end:
                result["status"] = "closed"
            else:
                result["status"] = "open_candidate"

        # 전체 페이지에 '마감'이라는 단어가 있다는
        # 이유만으로 접수 종료를 확정하지 않는다.
        # 조기 마감 여부는 공식 신청 화면 확인이 필요하다.

    except (requests.RequestException, ValueError) as exc:
        result["error"] = (
            f"{type(exc).__name__}: {exc}"
        )[:300]

    return result


def main():
    records = load_json(
        DATA / "opportunities.json", {}
    )

    if not isinstance(records, dict):
        raise ValueError("Invalid opportunities.json")

    today = datetime.now(KST).date()
    session = requests.Session()
    session.headers.update(HEADERS)

    # 최신 확인 순으로 처리한다.
    candidates = sorted(
        records.values(),
        key=lambda x: x.get("last_seen", ""),
        reverse=True,
    )

    results = []
    seen_urls = set()

    for item in candidates[:150]:
        url = item.get("url")
        if not url or url in seen_urls:
            continue

        seen_urls.add(url)
        results.append(verify(item, session, today))

    counts = {}
    for result in results:
        status = result["status"]
        counts[status] = counts.get(status, 0) + 1

    output = {
        "checked_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "today_kst": today.isoformat(),
        "counts": counts,
        "items": results,
    }

    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / "verified_v3.json"
    path.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("V3 verification completed")
    print(f"Checked: {len(results)}")
    print(json.dumps(counts, ensure_ascii=False))
    print(f"Saved: {path}")


if __name__ == "__main__":
    main()
