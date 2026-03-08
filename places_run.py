import argparse
import os
import re
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
PLACES_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
UA = os.getenv("OUTREACH_UA", "LeadClawResearchBot/1.0")

CHAT_PATTERNS = [
    "tawk.to",
    "intercom",
    "drift",
    "crisp.chat",
    "livechat",
    "zendesk",
    "freshchat",
    "tidio",
    "olark",
    "gorgias",
]

CONTACT_FORM_PATTERNS = [
    "<form",
    "contact us",
    "contact form",
    "get in touch",
    "enquiry",
    "enquiries",
    "consultation form",
]

BOOKING_PATTERNS = [
    "book now",
    "book online",
    "book appointment",
    "book consultation",
    "book a consultation",
    "book treatment",
    "book your appointment",
    "bookings",
    "reserve now",
    "schedule appointment",
    "fresha",
    "treatwell",
    "phorest",
    "booksy",
    "timely",
    "cliniko",
]

WHATSAPP_PATTERNS = [
    "whatsapp",
    "wa.me/",
    "api.whatsapp.com",
]

FAQ_PATTERNS = [
    "faq",
    "frequently asked",
    "questions",
]

PHONE_CTA_PATTERNS = [
    "call now",
    "call us",
    "phone us",
    "tel:",
]

WEAK_SITE_PATTERNS = [
    "coming soon",
    "under construction",
    "site is currently unavailable",
]

TIMEOUT = 12


def fetch_html(url: str) -> str | None:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": UA},
            timeout=TIMEOUT,
            allow_redirects=True,
        )
        content_type = response.headers.get("Content-Type", "").lower()
        if response.status_code == 200 and "text/html" in content_type:
            return response.text.lower()
    except Exception:
        return None
    return None


def extract_domain(url: str | None) -> str:
    if not url:
        return ""
    try:
        host = urlparse(url).netloc.lower().strip()
        return host.replace("www.", "")
    except Exception:
        return ""


def detect_primary_cta(html: str) -> str:
    if any(p in html for p in BOOKING_PATTERNS):
        return "booking"
    if any(p in html for p in WHATSAPP_PATTERNS):
        return "whatsapp"
    if any(p in html for p in CONTACT_FORM_PATTERNS):
        return "contact_form"
    if any(p in html for p in PHONE_CTA_PATTERNS):
        return "phone"
    return "unknown"


def scan_website(url: str | None) -> Dict:
    result = {
        "has_live_chat": False,
        "has_contact_form": False,
        "has_booking_cta": False,
        "has_whatsapp": False,
        "has_faq": False,
        "has_phone_cta": False,
        "primary_cta": "unknown",
        "website_quality_score": 0,
        "lead_fit_score": 0,
        "outreach_angle": "no_live_chat",
        "site_domain": extract_domain(url),
        "scan_ok": False,
    }

    if not url:
        return result

    html = fetch_html(url)
    if not html:
        return result

    result["scan_ok"] = True
    result["has_live_chat"] = any(p in html for p in CHAT_PATTERNS)
    result["has_contact_form"] = any(p in html for p in CONTACT_FORM_PATTERNS)
    result["has_booking_cta"] = any(p in html for p in BOOKING_PATTERNS)
    result["has_whatsapp"] = any(p in html for p in WHATSAPP_PATTERNS)
    result["has_faq"] = any(p in html for p in FAQ_PATTERNS)
    result["has_phone_cta"] = any(p in html for p in PHONE_CTA_PATTERNS)
    result["primary_cta"] = detect_primary_cta(html)

    quality = 50
    if result["has_booking_cta"]:
        quality += 10
    if result["has_faq"]:
        quality += 10
    if result["has_phone_cta"]:
        quality += 5
    if result["has_whatsapp"]:
        quality += 5
    if result["has_live_chat"]:
        quality += 10
    if any(p in html for p in WEAK_SITE_PATTERNS):
        quality -= 25
    if len(html) < 3000:
        quality -= 10

    result["website_quality_score"] = max(0, min(quality, 100))

    fit = 30
    if not result["has_live_chat"]:
        fit += 20
    if result["has_contact_form"] and not result["has_live_chat"]:
        fit += 15
    if not result["has_booking_cta"]:
        fit += 15
    if not result["has_whatsapp"]:
        fit += 5
    if not result["has_faq"]:
        fit += 5
    if result["has_live_chat"]:
        fit -= 25
    if any(p in html for p in WEAK_SITE_PATTERNS):
        fit += 10

    result["lead_fit_score"] = max(0, min(fit, 100))

    if result["has_contact_form"] and not result["has_live_chat"]:
        result["outreach_angle"] = "contact_form_only"
    elif not result["has_booking_cta"]:
        result["outreach_angle"] = "weak_booking_flow"
    else:
        result["outreach_angle"] = "no_live_chat"

    return result


def score_lead(
    website: str | None,
    email: str | None,
    phone: str | None,
    google_rating: float | None = None,
    review_count: int | None = None,
    has_live_chat: bool | None = None,
    has_contact_form: bool | None = None,
    has_booking_cta: bool | None = None,
    has_whatsapp: bool | None = None,
    has_faq: bool | None = None,
    website_quality_score: int | None = None,
    lead_fit_score: int | None = None,
) -> int:
    score = 20

    if website:
        score += 15
    if email:
        score += 20
    if phone:
        score += 10

    if google_rating is not None and google_rating >= 4.2:
        score += 10
    elif google_rating is not None and google_rating < 3.8:
        score -= 10

    if review_count is not None and review_count >= 20:
        score += 8
    elif review_count is not None and review_count >= 5:
        score += 4

    if has_contact_form:
        score += 8
    if has_live_chat is False:
        score += 12
    if has_live_chat is True:
        score -= 20

    if has_booking_cta is False:
        score += 10
    if has_whatsapp is False:
        score += 4
    if has_faq is False:
        score += 4

    if website_quality_score is not None and website_quality_score < 45:
        score += 8

    if lead_fit_score is not None:
        score += int(lead_fit_score / 10)

    return max(0, min(score, 100))


def should_keep_lead(
    website: str | None,
    google_rating: float | None,
    review_count: int | None,
    analysis: Dict,
) -> bool:
    if not website:
        return False

    if analysis.get("has_live_chat") is True:
        return False

    if google_rating is not None and google_rating < 3.5:
        return False

    if review_count is not None and review_count < 5:
        return False

    if analysis.get("lead_fit_score", 0) < 40:
        return False

    return True


def text_search(query: str) -> List[Dict]:
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"query": query, "key": PLACES_KEY}
    data = requests.get(url, params=params, timeout=20).json()
    return data.get("results", [])


def place_details(place_id: str) -> Dict:
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": (
            "name,website,formatted_phone_number,formatted_address,"
            "rating,user_ratings_total"
        ),
        "key": PLACES_KEY,
    }
    data = requests.get(url, params=params, timeout=20).json()
    return data.get("result", {})


def build_notes(address: str | None, analysis: Dict) -> str:
    parts = []
    if address:
        parts.append(f"address={address}")
    parts.append(f"primary_cta={analysis.get('primary_cta')}")
    parts.append(f"outreach_angle={analysis.get('outreach_angle')}")
    parts.append(f"website_quality_score={analysis.get('website_quality_score')}")
    parts.append(f"lead_fit_score={analysis.get('lead_fit_score')}")
    parts.append(f"has_booking_cta={analysis.get('has_booking_cta')}")
    parts.append(f"has_whatsapp={analysis.get('has_whatsapp')}")
    parts.append(f"has_faq={analysis.get('has_faq')}")
    parts.append(f"has_phone_cta={analysis.get('has_phone_cta')}")
    return " | ".join(parts)


def save(rows: List[Dict], niche: str, city: str):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Missing Supabase credentials")

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    saved = 0
    skipped = 0

    for r in rows:
        analysis = r.get("analysis", {})

        lead_score = score_lead(
            r.get("website"),
            r.get("contact_email"),
            r.get("contact_phone"),
            r.get("google_rating"),
            r.get("review_count"),
            analysis.get("has_live_chat"),
            analysis.get("has_contact_form"),
            analysis.get("has_booking_cta"),
            analysis.get("has_whatsapp"),
            analysis.get("has_faq"),
            analysis.get("website_quality_score"),
            analysis.get("lead_fit_score"),
        )

        record = {
            "niche": niche,
            "company_name": r.get("company_name"),
            "website": r.get("website"),
            "contact_email": r.get("contact_email"),
            "contact_phone": r.get("contact_phone"),
            "city": city,
            "source": "google-places",
            "score": lead_score,
            "status": "new",
            "notes": build_notes(r.get("address"), analysis),
            "google_rating": r.get("google_rating"),
            "review_count": r.get("review_count"),
            "has_live_chat": analysis.get("has_live_chat"),
            "has_contact_form": analysis.get("has_contact_form"),
            "lead_score": lead_score,
        }

        try:
            supabase.table("leads").insert(record).execute()
            saved += 1
        except Exception as exc:
            message = str(exc).lower()
            if "duplicate key value violates unique constraint" in message:
                skipped += 1
                continue
            raise

    print(f"Saved {saved} leads, skipped {skipped} duplicates")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", required=True, help="e.g. London")
    parser.add_argument("--niche", default="beauty", help="e.g. beauty|hair|nails")
    parser.add_argument("--query", default="beauty salon", help="base query term")
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()

    if not PLACES_KEY:
        raise RuntimeError("Missing GOOGLE_PLACES_API_KEY in .env")

    query = f"{args.query} {args.city} uk"
    results = text_search(query)[: args.limit]

    rows = []
    for item in results:
        place_id = item.get("place_id")
        if not place_id:
            continue

        details = place_details(place_id)
        website = details.get("website")
        analysis = scan_website(website)

        if not should_keep_lead(
            website,
            details.get("rating"),
            details.get("user_ratings_total"),
            analysis,
        ):
            continue

        rows.append(
            {
                "company_name": details.get("name") or item.get("name"),
                "website": website,
                "contact_phone": details.get("formatted_phone_number"),
                "contact_email": None,
                "address": details.get("formatted_address")
                or item.get("formatted_address"),
                "google_rating": details.get("rating"),
                "review_count": details.get("user_ratings_total"),
                "analysis": analysis,
            }
        )

    save(rows, niche=args.niche, city=args.city)
    print(f"Processed {len(rows)} Google Places leads for {args.city} ({args.niche})")


if __name__ == "__main__":
    main()