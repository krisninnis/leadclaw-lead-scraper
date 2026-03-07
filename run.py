import argparse
import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os
from pathlib import Path
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

UA = os.getenv("OUTREACH_UA", "LeadClawResearchBot/1.0")
HEADERS = {"User-Agent": UA}

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(\+?44|0)\s?\d{2,4}\s?\d{3,4}\s?\d{3,4}")


def score_lead(website, email, phone, city):
    score = 0
    if website:
        score += 25
    if email:
        score += 30
    if phone:
        score += 20
    if city:
        score += 10
    return min(score, 100)


def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code == 200 and "text/html" in r.headers.get("Content-Type", ""):
            return r.text
    except Exception:
        return None
    return None


def extract_contact_fields(html):
    emails = set(EMAIL_RE.findall(html or ""))
    phones = set(PHONE_RE.findall(html or ""))
    return (next(iter(emails), None), next(iter(phones), None))


def parse_site(site_url):
    html = fetch(site_url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.text.strip() if soup.title and soup.title.text else urlparse(site_url).netloc)

    email, phone = extract_contact_fields(html)

    # try contact page
    if not email:
        contact_link = None
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            txt = (a.get_text() or "").lower()
            if "contact" in href.lower() or "contact" in txt:
                contact_link = urljoin(site_url, href)
                break
        if contact_link:
            c_html = fetch(contact_link)
            c_email, c_phone = extract_contact_fields(c_html or "")
            email = email or c_email
            phone = phone or c_phone

    return {
        "company_name": title[:120],
        "website": site_url,
        "contact_email": email,
        "contact_phone": phone,
    }


def save_leads(rows, niche, city):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Missing Supabase env vars")

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    payload = []

    for row in rows:
        score = score_lead(row.get("website"), row.get("contact_email"), row.get("contact_phone"), city)
        payload.append(
            {
                "niche": niche,
                "company_name": row.get("company_name"),
                "website": row.get("website"),
                "contact_email": row.get("contact_email"),
                "contact_phone": row.get("contact_phone"),
                "city": city,
                "source": "web-public",
                "score": score,
                "status": "new",
            }
        )

    if payload:
        supabase.table("leads").insert(payload).execute()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True, help="e.g. 'beauty salon london'")
    parser.add_argument("--max-sites", type=int, default=20)
    args = parser.parse_args()

    # manual/public seed list approach (safe MVP)
    # replace with approved directories/APIs as you scale
    seeds = [
        "https://www.treatwell.co.uk",
        "https://www.yell.com",
        "https://www.fresha.com",
    ]

    city = args.query.split()[-1].title()
    niche = "beauty"

    leads = []
    for s in seeds[: args.max_sites]:
        row = parse_site(s)
        if row:
            leads.append(row)
        time.sleep(1.0)

    if not leads:
        print("No leads found from current seeds.")
        return

    save_leads(leads, niche=niche, city=city)
    print(f"Saved {len(leads)} leads for query='{args.query}'")


if __name__ == "__main__":
    main()
