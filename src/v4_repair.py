import json
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import requests
import verify_v3 as base

ROOT = Path(__file__).resolve().parents[1]
DATE = r'20\d{2}[./-]\s*\d{1,2}[./-]\s*\d{1,2}'
SHORT = r'\d{1,2}[./-]\s*\d{1,2}'
LABEL = re.compile(r'모집\s*기간|접수\s*기간|신청\s*기간|지원\s*기간|신청\s*마감|접수\s*마감|모집\s*마감')
ACTION = re.compile(r'모집|신청|접수|채용|양성\s*과정|교육생')
RESULT = re.compile(r'합격자|선정\s*결과|서류전형|면접시험|최종\s*결과|결과\s*안내')
TOPIC = re.compile(r'도슨트|큐레이터|학예|전시\s*해설|전문인력|교육생|양성\s*과정')

def iso(raw, year=None):
    nums = list(map(int, re.findall(r'\d+', raw)))
    if len(nums) == 2 and year:
        nums.insert(0, year)
    try:
        return date(*nums).isoformat() if len(nums) == 3 else None
    except ValueError:
        return None

def period(text):
    for label in LABEL.finditer(text):
        near = text[label.end():label.end() + 110]
        full = re.search(rf'({DATE})\s*(?:~|∼|～|부터|—|–|-)\s*({DATE}|{SHORT})', near)
        if full:
            start = iso(full.group(1))
            end = iso(full.group(2), int(start[:4]) if start else None)
            if start and end and start <= end:
                return start, end, near[:100]
        if '마감' in label.group():
            one = re.search(DATE, near)
            if one:
                end = iso(one.group())
                if end:
                    return None, end, near[:100]
    return None, None, ''

def canonical(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme.lower(), p.netloc.lower().removeprefix('www.'), p.path.rstrip('/'), p.query, ''))

def curate(records, today, session):
    kept, excluded, seen = [], [], set()
    for item in records:
        title = str(item.get('title', '')).strip()
        url = str(item.get('url', ''))
        key = canonical(url)
        reason = None
        if not url.startswith(('https://', 'http://')) or key in seen:
            reason = 'duplicate_or_invalid'
        elif RESULT.search(title):
            reason = 'result_notice'
        elif re.search(r'20(?:1\d|2[0-5])', title):
            reason = 'historical_notice'
        elif not ACTION.search(title):
            reason = 'not_recruitment'
        elif not TOPIC.search(title) and not re.search(r'가을학기|봄학기|2학기', title):
            reason = 'not_relevant'
        if reason:
            excluded.append({'title': title, 'url': url, 'reason': reason})
            continue
        seen.add(key)
        row = base.verify(item, session, date.fromisoformat(today))
        row['status'] = 'check_required'
        try:
            _, text = base.fetch_page(session, url)
            start, end, evidence = period(text)
            if end:
                row.update(start_date=start, deadline=end, evidence=evidence)
                if end < today:
                    row['status'] = 'closed'
                elif start and start > today:
                    row['status'] = 'upcoming'
                elif start:
                    row['status'] = 'open_candidate'
        except (requests.RequestException, ValueError) as exc:
            row['error'] = str(exc)[:250]
        if row['status'] == 'closed':
            excluded.append({'title': title, 'url': url, 'reason': 'expired_deadline'})
        else:
            kept.append(row)
    return kept, excluded

def main():
    src = ROOT / 'data/opportunities.json'
    records = json.loads(src.read_text(encoding='utf-8'))
    today = datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
    with requests.Session() as session:
        session.headers.update(base.HEADERS)
        kept, excluded = curate(sorted(records.values(), key=lambda r:r.get('last_seen',''), reverse=True)[:150], today, session)
    counts = {s:sum(x['status']==s for x in kept) for s in ('open_candidate','upcoming','check_required')}
    out = {'today_kst':today,'checked_at':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),'counts':counts,'items':kept,'excluded':excluded}
    path = ROOT / 'data/verified_v4.json'
    path.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print('V4 repair:',counts,'excluded:',len(excluded))

if __name__ == '__main__':
    main()
