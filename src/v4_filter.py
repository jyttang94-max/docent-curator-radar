import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data' / 'verified_v3.json'
TARGET = ROOT / 'data' / 'verified_v4.json'
BAD = re.compile(r'소개|오시는\s*길|개인정보|이용약관|조직도|연혁|공지사항$|공식 교육 페이지|프로그램 안내|^도슨트소개$', re.I)
TOPIC = re.compile(r'도슨트|큐레이터|학예|전시\s*해설|미술관|박물관|예술교육|전시기획', re.I)
ACTION = re.compile(r'모집|신청|접수|선발|양성|교육생|수강생|채용|아카데미|과정', re.I)

def filter_records(data, today):
    kept, rejected, seen = [], [], set()
    for item in data.get('items', []):
        title = str(item.get('title') or '').strip()
        url = str(item.get('url') or '')
        reason = None
        if not url.startswith(('https://', 'http://')) or url in seen:
            reason = 'invalid_or_duplicate_url'
        elif BAD.search(title) or not (TOPIC.search(title) and ACTION.search(title)):
            reason = 'not_a_specific_recruitment'
        elif item.get('status') == 'closed':
            reason = 'closed'
        elif re.search(r'20(?:1\d|2[0-5])', title):
            reason = 'old_year_in_title'
        elif item.get('deadline') and item['deadline'] < today:
            reason = 'expired_deadline'
        if reason:
            rejected.append({'title': title, 'url': url, 'reason': reason})
            continue
        seen.add(url)
        row = dict(item)
        if row.get('status') not in ('open_candidate', 'upcoming'):
            row['status'] = 'check_required'
        kept.append(row)
    return kept, rejected

def main():
    data = json.loads(SOURCE.read_text(encoding='utf-8'))
    today = datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
    kept, rejected = filter_records(data, today)
    counts = {s: sum(x['status'] == s for x in kept) for s in ('open_candidate', 'upcoming', 'check_required')}
    output = {'checked_at': data.get('checked_at'), 'today_kst': today, 'counts': counts, 'items': kept, 'excluded': rejected}
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print('V4:', counts, 'excluded:', len(rejected))

if __name__ == '__main__':
    main()
