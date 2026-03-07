import os
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('C:/Users/KRIS/.openclaw/workspace/lead-scraper-bot/.env')

SUPABASE_URL = os.getenv('SUPABASE_URL') or os.getenv('NEXT_PUBLIC_SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
UA = os.getenv('OUTREACH_UA', 'LeadClawResearchBot/1.0')
ENRICH_LIMIT = int(os.getenv('ENRICH_DAILY_LIMIT', '20'))

EMAIL_RE = re.compile(r'[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}', re.I)


def fetch(url: str):
    try:
        r = requests.get(url, headers={'User-Agent': UA}, timeout=10)
        if r.status_code == 200 and 'text/html' in r.headers.get('Content-Type', ''):
            return r.text
    except Exception:
        return None
    return None


def extract_email(html: str | None):
    if not html:
        return None
    m = EMAIL_RE.search(html)
    if not m:
        return None
    email = m.group(0).lower().strip()
    if any(x in email for x in ['example.com', 'wix.com', 'sentry.io']):
        return None
    return email


def get_contact_link(base_url: str, html: str):
    soup = BeautifulSoup(html, 'html.parser')
    for a in soup.select('a[href]'):
        href = (a.get('href') or '').strip()
        txt = (a.get_text() or '').lower()
        if 'contact' in href.lower() or 'contact' in txt:
            return urljoin(base_url, href)
    return None


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError('Missing Supabase credentials')

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    rows = (
        sb.table('leads')
        .select('id,website,company_name,contact_email,status')
        .eq('status', 'new')
        .is_('contact_email', 'null')
        .not_.is_('website', 'null')
        .limit(ENRICH_LIMIT)
        .execute()
        .data
        or []
    )

    scanned = 0
    updated = 0
    for row in rows:
        url = row.get('website')
        if not url:
            continue
        scanned += 1
        html = fetch(url)
        email = extract_email(html)
        if not email and html:
            c_link = get_contact_link(url, html)
            if c_link:
                email = extract_email(fetch(c_link))
        if email:
            sb.table('leads').update({'contact_email': email}).eq('id', row['id']).execute()
            updated += 1

    print({'ok': True, 'scanned': scanned, 'updated': updated})


if __name__ == '__main__':
    main()
