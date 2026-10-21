def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def normalized(url):
    parsed = urlparse(url)
    return parsed._replace(fragment='').geturl().rstrip('/')


def matched(text, terms):
    t = re.sub(r'\s+', ' ', text).lower()
    return [word for word in terms if word.lower() in t]


def extract_links(html, base):
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()
    page_text = soup.get_text(' ', strip=True)
    links = []
    for a in soup.select('a[href]'):
        href = urljoin(base, a.get('href', ''))
        if urlparse(href).scheme not in ('http', 'https'):
            continue
        label = a.get_text(' ', strip=True) or a.get('title', '')
        if label:
            links.append({'url': normalized(href), 'title': label[:250]})
    return page_text, links


def main():
    settings = read_yaml('config/settings.yaml')
    institutions = read_yaml('config/institutions.yaml').get('institutions', [])
    keyword_config = read_yaml('config/keywords.yaml')
    groups = keyword_config.get('keyword_groups', {})
    terms = list(dict.fromkeys(w for words in groups.values() for w in words))
    recruitment = keyword_config.get('recruitment_terms', [])
    activity = keyword_config.get('activity_terms', [])
    preferences = keyword_config.get('schedule_terms', {}).get('preferred', [])
    timeout = int(settings.get('collection', {}).get('request_timeout_seconds', 20))
    delay = float(settings.get('collection', {}).get('delay_between_requests_seconds', 2))
    now = datetime.now(timezone.utc).isoformat()
    DATA.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    records = load_json(DATA / 'opportunities.json', {})
    if not isinstance(records, dict):
        records = {}
    statuses = []
    changes = []
    session = requests.Session()
    session.headers.update(HEADERS)

    for inst in institutions:
        name = inst.get('name', inst.get('id', 'unknown'))
        urls = inst.get('urls', [])
        local_terms = list(dict.fromkeys(terms + inst.get('keywords', [])))
        for source_url in urls:
            status = {'institution': name, 'source_url': source_url, 'checked_at': now, 'status': 'failed', 'candidates': 0}
            try:
                response = session.get(source_url, timeout=timeout)
                response.raise_for_status()
                if 'html' not in response.headers.get('Content-Type', '').lower():
                    raise ValueError('Non-HTML response')
                page_text, links = extract_links(response.text, response.url)
                # Candidate discovery is intentionally conservative: link labels must contain a topic keyword.
                # This is NOT exhaustive crawling or confirmed recruitment availability.
                candidates = []
                for item in links:
                    hits = matched(item['title'], local_terms)
                    if hits:
                        candidates.append((item, hits))
                # Capture matching direct landing pages, including course pages without relevant links.
                landing_hits = matched(page_text[:5000], local_terms)
                if landing_hits and (matched(source_url, local_terms) or matched(urlparse(source_url).path, ['academy', 'docent', '168', '184'])):
                    candidates.append(({'url': normalized(response.url), 'title': name + ' 공식 교육 페이지'}, landing_hits))
                seen = set()
                for item, hits in candidates:
                    url = item['url']
                    if url in seen:
                        continue
                    seen.add(url)
                    key = hashlib.sha256(url.encode('utf-8')).hexdigest()[:20]
                    row = {'id': key, 'institution': name, 'title': item['title'], 'url': url,
                           'source_url': source_url, 'keywords': hits, 'last_seen': now,
                           'recruitment_terms': matched(item['title'], recruitment),
                           'activity_terms': matched(item['title'], activity),
                           'schedule_terms': matched(item['title'], preferences),
                           'verification': 'unverified_candidate'}
                    if key not in records:
                        row['first_seen'] = now
                        records[key] = row
                        changes.append({'change': 'new_candidate', **row})
                    else:
                        previous = records[key]
                        row['first_seen'] = previous.get('first_seen', now)
                        if previous.get('title') != row['title']:
                            changes.append({'change': 'title_changed', **row})
                        records[key] = row
                status.update(status='success', candidates=len(seen), http_status=response.status_code)
            except (requests.RequestException, ValueError) as exc:
                status['error'] = f'{type(exc).__name__}: {exc}'[:400]
            statuses.append(status)
            time.sleep(delay)

    write_json(DATA / 'opportunities.json', records)
    write_json(DATA / 'collection_status.json', {'checked_at': now, 'sources': statuses})
    write_json(DATA / 'latest_changes.json', changes)
    successes = sum(s['status'] == 'success' for s in statuses)
    failures = [s for s in statuses if s['status'] != 'success']
    lines = ['# Docent Curator Radar — 수집 결과', '', f'- 실행 시각(UTC): {now}',
             f'- 접속 성공: {successes}/{len(statuses)}', f'- 접속 실패: {len(failures)}',
             f'- 신규 또는 제목 변경 후보: {len(changes)}', '',
             '> 주의: 후보 발견 결과입니다. 모집 중 여부, 마감일, 수강 가능 여부는 아직 검증되지 않았습니다.', '',
             '## 신규 및 변경 후보', '']
    if not changes:
        lines.append('신규 후보 없음 (모집 공고 없음으로 확정할 수 없음)')
    for c in changes[:100]:
        lines.append(f"- [{c['institution']}] [{c['title']}]({c['url']}) — {c['change']}")
    lines.extend(['', '## 접속 실패', ''])
    if not failures:
        lines.append('없음')
    for s in failures:
        lines.append(f"- {s['institution']}: {s['source_url']} — {s.get('error', 'unknown')}")
    (REPORTS / 'latest.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Completed: {successes}/{len(statuses)} URLs accessible, {len(changes)} changed candidates, {len(failures)} failures')
    if not institutions or successes == 0:
        raise SystemExit('Collection health check failed: no successful sources')
