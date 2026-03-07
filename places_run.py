import argparse
import os
from pathlib import Path
from typing import List, Dict

import requests
from dotenv import load_dotenv
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
PLACES_KEY = os.getenv("GOOGLE_PLACES_API_KEY")


def score_lead(website: str | None, email: str | None, phone: str | None) -> int:
    score = 40  # places records are already structured
    if website:
        score += 20
    if email:
        score += 25
    if phone:
        score += 15
    return min(score, 100)


def text_search(query: str) -> List[Dict]:
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"query": query, "key": PLACES_KEY}
    data = requests.get(url, params=params, timeout=20).json()
    return data.get("results", [])


def place_details(place_id: str) -> Dict:
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,website,formatted_phone_number,formatted_address",
        "key": PLACES_KEY,
    }
    data = requests.get(url, params=params, timeout=20).json()
    return data.get("result", {})


def save(rows: List[Dict], niche: str, city: str):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Missing Supabase credentials")

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    payload = []

    for r in rows:
        score = score_lead(r.get("website"), r.get("contact_email"), r.get("contact_phone"))
        payload.append(
            {
                "niche": niche,
                "company_name": r.get("company_name"),
                "website": r.get("website"),
                "contact_email": r.get("contact_email"),
                "contact_phone": r.get("contact_phone"),
                "city": city,
                "source": "google-places",
                "score": score,
                "status": "new",
                "notes": r.get("address"),
            }
        )

    if payload:
        supabase.table("leads").insert(payload).execute()


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
      rows.append(
          {
              "company_name": d.get("name") or item.get("name"),
              "website": d.get("website"),
              "contact_phone": d.get("formatted_phone_number"),
              "contact_email": None,
              "address": d.get("formatted_address") or item.get("formatted_address"),
          }
      )

    save(rows, niche=args.niche, city=args.city)
    print(f"Saved {len(rows)} Google Places leads for {args.city} ({args.niche})")


if __name__ == "__main__":
    main()
