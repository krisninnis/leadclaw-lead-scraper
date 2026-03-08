import os
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
UA = os.getenv("OUTREACH_UA", "LeadClawResearchBot/1.0")
ENRICH_LIMIT = int(os.getenv("ENRICH_DAILY_LIMIT", "20"))

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)

BLOCKED_SUBSTRINGS = [
    "example.com",
    "wix.com",
    "wixpress.com",
    "sentry.io",
    "cloudflare.com",
    "godaddy.com",
    "googletagmanager.com",
    "google-analytics.com",
    "doubleclick.net",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "youtube.com",
    "vimeo.com",
    "fontawesome.com",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "jsdelivr.net",
    "cdnjs.com",
    "unpkg.com",
    "stripe.com",
    "shopify.com",
    "squarespace.com",
    "wordpress.com",
    "mailchimp.com",
    "sendgrid.net",
    "amazonses.com",
    "zendesk.com",
    "intercom.io",
    "drift.com",
    "crisp.chat",
    "tawk.to",
    "latofonts.com",
]

BLOCKED_PREFIXES = [
    "noreply@",
    "no-reply@",
    "donotreply@",
    "do-not-reply@",
    "mailer-daemon@",
    "postmaster@",
]

BLOCKED_LOCAL_PARTS = {
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "mailer-daemon",
    "postmaster",
}

ASSET_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".css",
    ".js",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".pdf",
    ".mp4",
    ".webm",
    ".avif",
)

CONTACT_KEYWORDS = [
    "contact",
    "about",
    "get in touch",
    "book",
    "booking",
    "consultation",
    "enquiry",
    "enquiries",
]

PREFERRED_LOCAL_PARTS = {
    "info",
    "hello",
    "contact",
    "bookings",
    "booking",
    "reception",
    "admin",
    "team",
    "enquiries",
    "enquiry",
}


def fetch(url: str) -> str | None:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": UA},
            timeout=10,
            allow_redirects=True,
        )
        content_type = response.headers.get("Content-Type", "").lower()
        if response.status_code == 200 and "text/html" in content_type:
            return response.text
    except Exception:
        return None
    return None


def normalize_email(raw: str) -> str:
    email = raw.lower().strip()
    email = email.replace("mailto:", "")
    email = email.replace("\\u003c", "")
    email = email.replace("\\u003e", "")
    email = email.replace("&lt;", "")
    email = email.replace("&gt;", "")
    email = email.strip("<>\"'()[]{}")
    email = email.rstrip(".,;:)>]}'\"")
    return email


def website_domain(url: str | None) -> str:
    if not url:
        return ""
    try:
        host = urlparse(url).netloc.lower().strip()
        return host.replace("www.", "")
    except Exception:
        return ""


def email_domain(email: str) -> str:
    return email.split("@", 1)[1].lower().strip() if "@" in email else ""


def looks_like_asset_string(value: str) -> bool:
    value = value.lower()

    if any(ext in value for ext in ASSET_EXTENSIONS):
        return True

    if "@2x" in value or "@3x" in value:
        return True

    if "logo" in value or "icon" in value or "banner" in value:
        return True

    if "u003c" in value or "u003e" in value:
        return True

    return False


def is_bad_email(email: str, site_domain: str = "") -> bool:
    email = normalize_email(email)

    if not email or "@" not in email or email.count("@") != 1:
        return True

    if " " in email:
        return True

    if any(email.startswith(prefix) for prefix in BLOCKED_PREFIXES):
        return True

    if any(bad in email for bad in BLOCKED_SUBSTRINGS):
        return True

    local_part, domain_part = email.split("@", 1)

    if not local_part or not domain_part:
        return True

    if local_part in BLOCKED_LOCAL_PARTS:
        return True

    if len(local_part) > 80:
        return True

    if looks_like_asset_string(local_part) or looks_like_asset_string(email):
        return True

    if local_part.endswith(ASSET_EXTENSIONS):
        return True

    if any(ext in local_part for ext in ASSET_EXTENSIONS):
        return True

    if domain_part.startswith("www."):
        return True

    if domain_part.count(".") == 0:
        return True

    if site_domain:
        clean_site = site_domain.replace("www.", "")
        clean_email_domain = domain_part.replace("www.", "")

        unrelated_vendor_domains = [
            "wix.com",
            "wixpress.com",
            "sentry.io",
            "cloudflare.com",
            "shopify.com",
            "squarespace.com",
            "wordpress.com",
            "latofonts.com",
        ]

        if (
            clean_email_domain != clean_site
            and not clean_email_domain.endswith(clean_site)
            and any(vendor in clean_email_domain for vendor in unrelated_vendor_domains)
        ):
            return True

    return False


def score_email(email: str, site_domain: str = "") -> int:
    email = normalize_email(email)
    local_part = email.split("@", 1)[0]
    domain_part = email_domain(email)

    score = 0

    if local_part in PREFERRED_LOCAL_PARTS:
        score += 5

    if local_part.startswith(("info", "hello", "contact", "book", "reception", "admin")):
        score += 3

    if site_domain:
        clean_site = site_domain.replace("www.", "")
        clean_domain = domain_part.replace("www.", "")

        if clean_domain == clean_site:
            score += 6
        elif clean_domain.endswith(clean_site):
            score += 4

    if domain_part.endswith(("gmail.com", "hotmail.com", "outlook.com", "icloud.com", "yahoo.com")):
        score += 1

    if "-" in local_part or "_" in local_part:
        score -= 1

    return score


def extract_email(html: str | None, site_domain: str = "") -> str | None:
    if not html:
        return None

    matches = EMAIL_RE.findall(html)
    if not matches:
        return None

    candidates = []
    seen = set()

    for raw in matches:
        email = normalize_email(raw)
        if email in seen:
            continue
        seen.add(email)

        if is_bad_email(email, site_domain=site_domain):
            continue

        candidates.append(email)

    if not candidates:
        return None

    ranked = sorted(
        ((score_email(email, site_domain=site_domain), email) for email in candidates),
        reverse=True,
    )

    return ranked[0][1]


def get_contact_links(base_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []

    for anchor in soup.select("a[href]"):
        href = (anchor.get("href") or "").strip()
        text = (anchor.get_text() or "").strip().lower()

        if not href:
            continue

        href_lower = href.lower()

        if href_lower.startswith("mailto:"):
            continue

        if any(keyword in href_lower or keyword in text for keyword in CONTACT_KEYWORDS):
            links.append(urljoin(base_url, href))

    deduped = []
    seen = set()
    for link in links:
        if link not in seen:
            seen.add(link)
            deduped.append(link)

    return deduped[:3]


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Missing Supabase credentials")

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    rows = (
        supabase.table("leads")
        .select("id,website,company_name,contact_email,status")
        .eq("status", "new")
        .is_("contact_email", "null")
        .not_.is_("website", "null")
        .limit(ENRICH_LIMIT)
        .execute()
        .data
        or []
    )

    scanned = 0
    updated = 0

    for row in rows:
        url = row.get("website")
        if not url:
            continue

        scanned += 1
        site_domain = website_domain(url)

        html = fetch(url)
        email = extract_email(html, site_domain=site_domain)

        if not email and html:
            for contact_link in get_contact_links(url, html):
                contact_html = fetch(contact_link)
                email = extract_email(contact_html, site_domain=site_domain)
                if email:
                    break

        if email:
            (
                supabase.table("leads")
                .update({"contact_email": email})
                .eq("id", row["id"])
                .execute()
            )
            updated += 1

    print({"ok": True, "scanned": scanned, "updated": updated})


if __name__ == "__main__":
    main()