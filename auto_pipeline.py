import argparse
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
OUTREACH_BASE_URL = os.getenv("OUTREACH_BASE_URL", "https://leadclaw.uk").rstrip("/")
OUTREACH_RUN_TOKEN = os.getenv("OUTREACH_RUN_TOKEN", "").strip()
PYTHON_BIN = os.getenv("PYTHON_BIN", os.sys.executable)
PLACES_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
FREE_TIER_MODE = os.getenv("FREE_TIER_MODE", "1").strip() != "0"
SCRAPER_DAILY_NEW_CAP = int(os.getenv("SCRAPER_DAILY_NEW_CAP", "40"))

DEFAULT_CITY_POOL = [
    "London","Manchester","Birmingham","Leeds","Liverpool",
    "Bristol","Nottingham","Leicester","Newcastle","Sheffield"
]

DEFAULT_NICHES = ["beauty"]
ROTATING_CITY_BATCH_SIZE = 3


def get_rotating_cities(pool: list[str], batch_size: int) -> list[str]:
    if not pool:
        return ["London", "Manchester"]

    day_index = datetime.now(timezone.utc).toordinal()
    start = (day_index * batch_size) % len(pool)

    selected = []
    for i in range(min(batch_size, len(pool))):
        selected.append(pool[(start + i) % len(pool)])

    return selected


def run_places_batch(limit: int, cities: list[str], niches: list[str]):
    city_args = " ".join(cities)
    niche_args = " ".join(niches)
    cmd = f'"{PYTHON_BIN}" places_batch.py --limit {limit} --cities {city_args} --niches {niche_args}'
    print(f"[pipeline] running: {cmd}")
    code = os.system(cmd)
    if code != 0:
        raise RuntimeError(f"places_batch failed with code {code}")


def supabase_client():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def iso_hours_ago(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def current_new_leads_24h():
    sb = supabase_client()
    rows = (
        sb.table("leads")
        .select("id")
        .eq("status", "new")
        .gte("created_at", iso_hours_ago(24))
        .limit(5000)
        .execute()
        .data or []
    )
    return len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-scrape", action="store_true")
    parser.add_argument("--skip-outreach", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=4)
    args = parser.parse_args()

    new_24h = current_new_leads_24h() if FREE_TIER_MODE else 0
    remaining_new_capacity = max(0, SCRAPER_DAILY_NEW_CAP - new_24h)

    if args.dry_run:
        print({
            "mode": "dry_run",
            "new24h": new_24h,
            "remaining_capacity": remaining_new_capacity,
            "skip_scrape": args.skip_scrape,
            "skip_outreach": args.skip_outreach
        })
        raise SystemExit(0)

    if not args.skip_scrape:
        if not PLACES_KEY:
            print("[pipeline] scrape skipped: GOOGLE_PLACES_API_KEY missing")
        elif FREE_TIER_MODE and remaining_new_capacity <= 0:
            print("[pipeline] scrape skipped: daily cap reached")
        else:
            effective_limit = min(args.limit, remaining_new_capacity)
            if effective_limit > 0:
                run_places_batch(effective_limit, DEFAULT_CITY_POOL[:3], DEFAULT_NICHES)

    print("[pipeline] finished")


if __name__ == "__main__":
    main()
