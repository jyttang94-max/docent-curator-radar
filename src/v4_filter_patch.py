import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/verified_v3.json'
TARGET = ROOT / 'data/verified_v4.json'
ACTION = re.compile(r'모집|신청|접수|지원자\s*모집|채용\s*공고', re.I)
TOPIC = re.compile(r'도슨트|큐레이터|학예|전시\s*해설|전문인력\s*양성|교육생|미술관|박물관', re.I)
RESULT = re.compile(r'합격자|선정\s*결과|서류전형|면접시험|최종\s*결과|결과\s*안내|홍보원\)|홍보원\s', re.I)
GENERIC = re.compile(r'소개$|안내$|^도슨트$|^도슨트소개$|^큐레이터 신청|^전문인력 양성$|^전문인력 양성과정$|공식 교육 페이지', re.I)
OLD = re.compile(r'20(?:1\d|2[0-5])')

def canonical(url):
    p = urlsplit(url)
    host = p.netloc.lower().removeprefix('www.')
    return urlunsplit((p.scheme.lower(), host, p.path.rstrip('/'), p.query, ''))

def filter_records(data, today):
    kept, excluded, seen = [], [], set()
    for item in data.get('items', []):
        title = str(item.get('title') or '').strip()
        url = str(item.get('url') or '')
        key = canonical(url)
        reason = None
        if not url.startswith(('https://', 'http://')) or key in seen:
            reason = 'invalid_or_duplicate_url'
        elif RESULT.search(title):
            reason = 'selection_or_result_notice'
        elif OLD.search(title):
            reason = 'old_year_in_title'
        elif item.get('status') == 'closed' or (item.get('deadline') and item['deadline'] < today):
            reason = 'closed_or_expired'
        elif title.startswith(('큐레이터 신청', '도슨트 신청')):
            reason = 'application_link_without_notice'
        elif GENERIC.search(title) and not ACTION.search(title):
            reason = 'generic_page'
        elif not ACTION.search(title):
            reason = 'no_recruitment_action'
        elif not TOPIC.search(title):
            reason = 'unrelated_recruitment'
        if reason:
            excluded.append({'title': title, 'url': url, 'reason': reason})
            continue
        seen.add(key)
        row = dict(item)
        # Only a parsed future/current application period can establish open/upcoming.
        if not row.get('start_date') or not row.get('deadline'):
            row['status'] = 'check_required'
        kept.append(row)
    return kept, excluded

def main():
    data = json.loads(SOURCE.read_text(encoding='utf-8'))
    today = datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
    kept, excluded = filter_records(data, today)
    statuses = ('open_candidate', 'upcoming', 'check_required')
    counts = {s: sum(i.get('status') == s for i in kept) for s in statuses}
    result = {'checked_at': data.get('checked_at'), 'today_kst': today,
              'counts': counts, 'items': kept, 'excluded': excluded}
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('V4 patch:', counts, 'excluded:', len(excluded))

if __name__ == '__main__':
    main()
