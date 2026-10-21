import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REPORTS = ROOT / "reports"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DocentCuratorRadar/2.0)"
}


def read_yaml(path):
    with (ROOT / path).open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return default


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def normalized(url):
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl().rstrip("/")


def matched(text, terms):
    text = re.sub(r"\s+", " ", text).lower()
    return [word for word in terms if word.lower() in text]


def extract_links(html, base):
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    page_text = soup.get_text(" ", strip=True)
    links = []

    for a in soup.select("a[href]"):
        href = urljoin(base, a.get("href", ""))

        if urlparse(href).scheme not in ("http", "https"):
            continue

        label = a.get_text(" ", strip=True) or a.get("title", "")

        if label:
            links.append({
                "url": normalized(href),
                "title": label[:250],
            })

    return page_text, links


def main():
    settings = read_yaml("config/settings.yaml")
    institutions = read_yaml(
        "config/institutions.yaml"
    ).get("institutions", [])

    keyword_config = read_yaml("config/keywords.yaml")
    groups = keyword_config.get("keyword_groups", {})

    terms = list(dict.fromkeys(
        word
        for words in groups.values()
        for word in words
    ))

    recruitment = keyword_config.get("recruitment_terms", [])
    activity = keyword_config.get("activity_terms", [])
    preferences = keyword_config.get(
        "schedule_terms", {}
    ).get("preferred", [])

    collection = settings.get("collection", {})
    timeout = int(collection.get("request_timeout_seconds", 20))
    delay = float(collection.get("delay_between_requests_seconds", 2))

    now = datetime.now(timezone.utc).isoformat()

    DATA.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    records = load_json(DATA / "opportunities.json", {})
    if not isinstance(records, dict):
        records = {}

    statuses = []
    changes = []

    session = requests.Session()
    session.headers.update(HEADERS)

    for inst in institutions:
        name = inst.get("name", inst.get("id", "unknown"))
        urls = inst.get("urls", [])

        local_terms = list(dict.fromkeys(
            terms + inst.get("keywords", [])
        ))

        for source_url in urls:
            status = {
                "institution": name,
                "source_url": source_url,
                "checked_at": now,
                "status": "failed",
                "candidates": 0,
            }

            try:
                response = session.get(
                    source_url,
                    timeout=timeout,
                )
                response.raise_for_status()

                content_type = response.headers.get(
                    "Content-Type", ""
                ).lower()

                if "html" not in content_type:
                    raise ValueError("Non-HTML response")

                page_text, links = extract_links(
                    response.text,
                    response.url,
                )

                candidates = []

                for item in links:
                    hits = matched(
                        item["title"],
                        local_terms,
                    )
                    if hits:
                        candidates.append((item, hits))

                landing_hits = matched(
                    page_text[:5000],
                    local_terms,
                )

                landing_paths = [
                    "academy", "docent", "168", "184"
                ]

                is_landing = (
                    bool(matched(source_url, local_terms))
                    or bool(matched(
                        urlparse(source_url).path,
                        landing_paths,
                    ))
                )

                if landing_hits and is_landing:
                    candidates.append((
                        {
                            "url": normalized(response.url),
                            "title": name + " 공식 교육 페이지",
                        },
                        landing_hits,
                    ))

                seen = set()

                for item, hits in candidates:
                    url = item["url"]

                    if url in seen:
                        continue

                    seen.add(url)

                    key = hashlib.sha256(
                        url.encode("utf-8")
                    ).hexdigest()[:20]

                    row = {
                        "id": key,
                        "institution": name,
                        "title": item["title"],
                        "url": url,
                        "source_url": source_url,
                        "keywords": hits,
                        "last_seen": now,
                        "recruitment_terms": matched(
                            item["title"], recruitment
                        ),
                        "activity_terms": matched(
                            item["title"], activity
                        ),
                        "schedule_terms": matched(
                            item["title"], preferences
                        ),
                        "verification": "unverified_candidate",
                    }

                    if key not in records:
                        row["first_seen"] = now
                        records[key] = row
                        changes.append({
                            "change": "new_candidate",
                            **row,
                        })
                    else:
                        previous = records[key]
                        row["first_seen"] = previous.get(
                            "first_seen", now
                        )

                        if previous.get("title") != row["title"]:
                            changes.append({
                                "change": "title_changed",
                                **row,
                            })

                        records[key] = row

                status.update(
                    status="success",
                    candidates=len(seen),
                    http_status=response.status_code,
                )

            except (requests.RequestException, ValueError) as exc:
                status["error"] = (
                    f"{type(exc).__name__}: {exc}"
                )[:400]

            statuses.append(status)
            time.sleep(delay)

    write_json(DATA / "opportunities.json", records)

    write_json(
        DATA / "collection_status.json",
        {
            "checked_at": now,
            "sources": statuses,
        },
    )

    write_json(DATA / "latest_changes.json", changes)

    successes = sum(
        s["status"] == "success"
        for s in statuses
    )

    failures = [
        s for s in statuses
        if s["status"] != "success"
    ]

    lines = [
        "# Docent Curator Radar - 수집 결과",
        "",
        f"- 실행 시각(UTC): {now}",
        f"- 접속 성공: {successes}/{len(statuses)}",
        f"- 접속 실패: {len(failures)}",
        f"- 신규 또는 변경 후보: {len(changes)}",
        "",
        "> 모집 중 여부와 마감일은 아직 검증되지 않은 후보입니다.",
        "",
        "## 신규 및 변경 후보",
        "",
    ]

    if not changes:
        lines.append(
            "신규 후보 없음 (공고 없음으로 확정할 수 없음)"
        )

    for item in changes[:100]:
        lines.append(
            f"- [{item['institution']}] "
            f"[{item['title']}]({item['url']}) "
            f"- {item['change']}"
        )

    lines.extend(["", "## 접속 실패", ""])

    if not failures:
        lines.append("없음")

    for item in failures:
        lines.append(
            f"- {item['institution']}: "
            f"{item['source_url']} "
            f"- {item.get('error', 'unknown')}"
        )

    (REPORTS / "latest.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print(
        f"Completed: {successes}/{len(statuses)} "
        f"URLs accessible, {len(changes)} changed "
        f"candidates, {len(failures)} failures"
    )

    if not institutions or successes == 0:
        raise SystemExit(
            "Collection health check failed: "
            "no successful sources"
        )


if __name__ == "__main__":
    main()
