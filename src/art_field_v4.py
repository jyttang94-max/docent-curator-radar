import hashlib
import html
import json
import os
import re
import smtplib
import ssl
import sys
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag
from zoneinfo import ZoneInfo

import requests
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
KST = ZoneInfo('Asia/Seoul')
NOW = datetime.now(KST)
TODAY = NOW.date()
OUT = ROOT / 'reports'
DATA = ROOT / 'data'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; ArtFieldNotes/Final; +https://github.com/)'}
RELEVANT = re.compile(r'도슨트|큐레이터|학예|전시해설|전시 해설|문화예술교육|예술교육|전시기획|전시 기획|미술관 교육|박물관 교육|전문인력 양성', re.I)
ACTION = re.compile(r'모집|신청|접수|채용|선발|수강생|교육생|참가자|지원자|공고|양성\s*과정', re.I)
NEGATIVE = re.compile(r'소개|연혁|오시는\s*길|개인정보|이용약관|뉴스레터|인사말|조직도|시설안내|관람안내|공지사항\s*$|교육\s*페이지$|프로그램\s*안내$', re.I)
DATE = r'(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*일?'
SHORT_DATE = r'(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*일?'
DATE_RE = re.compile(DATE)
LABEL = re.compile(r'접수\s*기간|신청\s*기간|모집\s*기간|지원\s*기간|접수\s*일정|신청\s*일정|접수\s*마감|신청\s*마감|모집\s*마감|신청\s*방법', re.I)
SEPARATOR = r'\s*(?:~|∼|～|〜|부터|–|—|－|\-|\bto\b)\s*'
FULL_RANGE = re.compile(rf'{DATE}{SEPARATOR}{DATE}', re.I)
SHORT_RANGE = re.compile(rf'{DATE}{SEPARATOR}{SHORT_DATE}', re.I)
DEADLINE = re.compile(rf'(?:마감|까지|접수\s*종료)\s*[:：]?\s*{DATE}|{DATE}\s*(?:까지|마감)', re.I)
WEEKDAYS = re.compile(r'(?<![가-힣])(?:월|화|수|목|금|토|일)요일|주말|평일|야간|저녁|오후\s*[6-9]시', re.I)
TIME = re.compile(r'(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d\s*(?:~|–|—|-)\s*(?:[01]?\d|2[0-3]):[0-5]\d')
COST = re.compile(r'(?:교육비|수강료|참가비|수강\s*비용)\s*[:：]?\s*(무료|무상|\d[\d,]*\s*원)')


def clean_url(url):
    url = urldefrag(url)[0]
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return ''
    if any(parsed.path.lower().endswith(ext) for ext in ('.jpg', '.png', '.gif', '.zip', '.hwp', '.hwpx', '.doc', '.docx', '.xls', '.xlsx')):
        return ''
    return url


def fetch(session, url):
    response = session.get(url, timeout=12)
    response.raise_for_status()
    content_type = response.headers.get('Content-Type', '').lower()
    if 'html' not in content_type:
        raise ValueError('non_html')
    soup = BeautifulSoup(response.text, 'html.parser')
    for tag in soup(['script', 'style', 'noscript', 'footer', 'nav']):
        tag.decompose()
    heading = soup.find('h1') or soup.find('h2')
    page_title = heading.get_text(' ', strip=True) if heading else (soup.title.get_text(' ', strip=True) if soup.title else '')
    main = soup.find('main') or soup.find('article') or soup
    text = re.sub(r'\s+', ' ', main.get_text(' ', strip=True))[:18000]
    links = []
    for a in soup.select('a[href]'):
        label = re.sub(r'\s+', ' ', a.get_text(' ', strip=True) or a.get('title', ''))[:160]
        link = clean_url(urljoin(response.url, a.get('href', '')))
        if label and link:
            links.append((label, link))
    return page_title, text, links


def as_date(year, month, day):
    try:
        return date(int(year), int(month), int(day))
    except (TypeError, ValueError):
        return None


def parse_period(text):
    # Extract only close to application-specific labels, not arbitrary event dates.
    for label in LABEL.finditer(text):
        snippet = text[max(0, label.start() - 12):label.end() + 130]
        match = FULL_RANGE.search(snippet)
        if match:
            start = as_date(*match.group(1, 2, 3))
            end = as_date(*match.group(4, 5, 6))
            if start and end and start <= end and (end - start).days <= 180:
                return start, end, snippet[:180]
        match = SHORT_RANGE.search(snippet)
        if match:
            start = as_date(*match.group(1, 2, 3))
            end = as_date(match.group(1), *match.group(4, 5))
            if start and end and start <= end and (end - start).days <= 180:
                return start, end, snippet[:180]
