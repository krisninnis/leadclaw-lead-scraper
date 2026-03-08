import argparse
import os
from pathlib import Path
from typing import List, Dict

import requests
from dotenv import load_dotenv
from supabase import create_client


def scan_website(url: str | None):
    if not url:
        return False, False

    try:
        html = requests.get(url, timeout=10).text.lower()

        chat_patterns = [
            "tawk.to",
            "intercom",
            "drift",
            "crisp.chat",
            "livechat",
            "zendesk",
        ]

        has_live_chat = any(p in html for p in chat_patterns)

        form_patterns = [
            "<form",
            "contact",
            "book appointment",
            "book consultation",
        ]

        has_contact_form = any(p in html for p in form_patterns)

        return has_live_chat, has_contact_form

    except Exception:
        return False, False


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
PLACES_KEY = os.getenv("GOOGLE_PLACES_API_KEY")


def score_lead(
    website: str | None,
    email: str | None,
    phone: str | None,
    google_rating: float | None = None,
    review_count: int | None = None,
    has_live_chat: bool | None = None,
    has_contact_form: bool | None = None,
) -> int:
    score = 20

    if website:
        score += 20

    if email:
        score += 20

    if phone:
        score += 10

    if google_rating is not None and google_rating >= 4.2:
        score += 10

    if review_count is not None and review_count >= 20:
        score += 5

    if has_contact_form:
        score += 10

    if has_live_chat is False:
        score += 15

    if has_live_chat is True:
        score -= 15

    return max(0, min(score, 100))


def should_keep_lead(
    website: str | None,
    google_rating: float | None,
    review_count: int | None,
    has_live_chat: bool | None,
) -> bool:
    if not website:
        return False

    if has_live_chat is True:
        return False

    if google_rating is not None and google_rating < 3.5:
        return False

    if review_count is not None and review_count < 5:
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
        "fields": "name,website,formatted_phone_number,formatted_address,rating,user_ratings_total",
        "key": PLACES_KEY,
    }
    data = requests.get(url, params=params, timeout=20).json()
    return data.get("result", {})


def save(rows: List[Dict], niche: str, city: str):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Missing Supabase credentials")

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    saved = 0
    skipped = 0

    for r in rows:
        lead_score = score_lead(
            r.get("website"),
            r.get("contact_email"),
            r.get("contact_phone"),
            r.get("google_rating"),
            r.get("review_count"),
            r.get("has_live_chat"),
            r.get("has_contact_form"),
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
            "notes": r.get("address"),
            "google_rating": r.get("google_rating"),
            "review_count": r.get("review_count"),
            "has_live_chat": r.get("has_live_chat"),
            "has_contact_form": r.get("has_contact_form"),
            "lead_score": lead_score,
        }

        try:
            supabase.table("leads").insert(record).execute()
            saved += 1
        except Exception as e:
            message = str(e).lower()
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

    q = f"{args.query} {args.city} uk"
    results = text_search(q)[: args.limit]

    rows = []
    for item in results:
        pid = item.get("place_id")
        if not pid:
            continue

        d = place_details(pid)

        website = d.get("website")
        has_live_chat, has_contact_form = scan_website(website)

        if not should_keep_lead(
            website,
            d.get("rating"),
            d.get("user_ratings_total"),
            has_live_chat,
        ):
            continue

        rows.append(
            {
                "company_name": d.get("name") or item.get("name"),
                "website": website,
                "contact_phone": d.get("formatted_phone_number"),
                "contact_email": None,
                "address": d.get("formatted_address") or item.get("formatted_address"),
                "google_rating": d.get("rating"),
                "review_count": d.get("user_ratings_total"),
                "has_live_chat": has_live_chat,
                "has_contact_form": has_contact_form,
            }
        )

    save(rows, niche=args.niche, city=args.city)
    print(f"Processed {len(rows)} Google Places leads for {args.city} ({args.niche})")


if __name__ == "__main__":
    main()