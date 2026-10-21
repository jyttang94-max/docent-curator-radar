import html
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'verified_v4.json'
OUT = ROOT / 'reports' / 'art_field_v4_preview.html'

def render(data):
    groups = [('01 NOW OPEN', 'open_candidate'), ('02 CHECK FIRST', 'check_required'), ('04 RADAR WATCH', 'upcoming')]
    sections = []
    for title, status in groups:
        items = [x for x in data['items'] if x['status'] == status][:8]
        cards = []
        for x in items:
            e = lambda s: html.escape(str(s or '미확인'), quote=True)
            cards.append(f'<tr><td style="padding:15px;border:1px solid #dce4eb"><b>{e(x.get("institution"))}</b><h3>{e(x.get("title"))}</h3><p>접수 시작: {e(x.get("start_date"))} / 마감: {e(x.get("deadline"))}</p><p>교육비: {e(x.get("cost"))}</p><a href="{e(x.get("url"))}">공식 공고 확인 →</a></td></tr>')
        sections.append(f'<tr><td><h2 style="color:#152b40">{title}</h2></td></tr>' + (''.join(cards) or '<tr><td>확인된 공고 없음</td></tr>'))
    day = datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y.%m.%d')
    return f'''<!doctype html><html lang="ko"><meta charset="utf-8"><body style="margin:0;background:#edf1f5;font-family:Arial,sans-serif"><table role="presentation" width="100%"><tr><td align="center"><table role="presentation" width="680" style="width:100%;max-width:680px;background:white"><tr><td style="background:#152b40;color:white;padding:28px"><h1>ART FIELD NOTES</h1><p>도슨트, 큐레이터 교육 및 활동 모집 정보 | {day}</p></td></tr><tr><td style="padding:25px"><p>접수 기간 후보 {data['counts']['open_candidate']}건 / 접수 예정 {data['counts']['upcoming']}건 / 확인 필요 {data['counts']['check_required']}건</p><p>※ 자동 추출 정보입니다. 실제 신청 가능 여부는 공식 페이지에서 확인하세요.</p><table role="presentation" width="100%">{''.join(sections)}</table></td></tr></table></td></tr></table></body></html>'''

def main():
    data = json.loads(DATA.read_text(encoding='utf-8'))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(data), encoding='utf-8')
    print('HTML generated:', OUT)

if __name__ == '__main__':
    main()
