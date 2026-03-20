import argparse
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

OUTREACH_BASE_URL = os.getenv("OUTREACH_BASE_URL", "https://www.leadclaw.uk").rstrip("/")
OUTREACH_RUN_TOKEN = os.getenv("OUTREACH_RUN_TOKEN", "").strip()

PYTHON_BIN = os.getenv("PYTHON_BIN", os.sys.executable)
PLACES_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()

FREE_TIER_MODE = os.getenv("FREE_TIER_MODE", "1").strip() != "0"
SCRAPER_DAILY_NEW_CAP = int((os.getenv("SCRAPER_DAILY_NEW_CAP") or "40").strip())

TARGET_MARKET = (os.getenv("TARGET_MARKET") or "uk").strip().lower()

CITY_POOLS = {
    "uk": [
        "London",
        "Manchester",
        "Birmingham",
        "Leeds",
        "Liverpool",
        "Bristol",
        "Nottingham",
        "Leicester",
        "Newcastle",
        "Sheffield",
        "Glasgow",
        "Edinburgh",
        "Cardiff",
        "Belfast",
        "Southampton",
        "Brighton",
        "Reading",
        "Coventry",
        "Bradford",
        "Derby",
    ],
    "english_speaking": [
        "London",
        "Manchester",
        "Birmingham",
        "Leeds",
        "Liverpool",
        "Bristol",
        "Glasgow",
        "Edinburgh",
        "Cardiff",
        "Belfast",
        "Dublin",
        "Cork",
        "Galway",
        "Sydney",
        "Melbourne",
        "Brisbane",
        "Perth",
        "Auckland",
        "Wellington",
        "Christchurch",
        "Toronto",
        "Vancouver",
        "Calgary",
        "Ottawa",
        "New York",
        "Los Angeles",
        "Chicago",
        "Miami",
        "Dallas",
    ],
}

DEFAULT_NICHES = ["beauty"]
ROTATING_CITY_BATCH_SIZE = 3


def log_event(event: str, **fields):
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    print(json.dumps(payload, default=str))


def get_city_pool() -> list[str]:
    return CITY_POOLS.get(TARGET_MARKET, CITY_POOLS["uk"])


def get_rotating_cities(pool: list[str], batch_size: int) -> list[str]:
    if not pool:
        return ["London", "Manchester"]

    day_index = datetime.now(timezone.utc).toordinal()
    start = (day_index * batch_size) % len(pool)

    selected = []
    for i in range(min(batch_size, len(pool))):
        selected.append(pool[(start + i) % len(pool)])

    return selected


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
        .data
        or []
    )
    return len(rows)


def run_python_script(script_name: str, *args: str):
    cmd = [PYTHON_BIN, script_name, *args]
    log_event("script_start", script=script_name, command=cmd)

    result = subprocess.run(
        cmd,
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
    )

    if result.stdout.strip():
        print(result.stdout.strip())

    if result.stderr.strip():
        print(result.stderr.strip())

    if result.returncode != 0:
        raise RuntimeError(f"{script_name} failed with code {result.returncode}")

    log_event("script_finish", script=script_name, returncode=result.returncode)


def run_places_batch(limit: int, cities: list[str], niches: list[str]):
    args = ["--limit", str(limit)]

    if cities:
        args.extend(["--cities", *cities])

    if niches:
        args.extend(["--niches", *niches])

    run_python_script("places_batch.py", *args)


def run_enrich():
    run_python_script("enrich_emails.py")


def run_generate_messages():
    run_python_script("generate_outreach_messages.py")


def trigger_outreach():
    if not OUTREACH_BASE_URL:
        log_event("outreach_trigger_skipped", reason="missing_outreach_base_url")
        return

    if not OUTREACH_RUN_TOKEN:
        log_event("outreach_trigger_skipped", reason="missing_outreach_run_token")
        return

    url = f"{OUTREACH_BASE_URL}/api/outreach/run"
    headers = {
        "Authorization": f"Bearer {OUTREACH_RUN_TOKEN}",
        "Content-Type": "application/json",
    }

    log_event("outreach_trigger_start", url=url)

    response = requests.post(url, headers=headers, timeout=60)
    response.raise_for_status()

    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text}

    log_event("outreach_trigger_finish", response=payload)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-scrape", action="store_true")
    parser.add_argument("--skip-enrich", action="store_true")
    parser.add_argument("--skip-generate", action="store_true")
    parser.add_argument("--skip-outreach", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=4)
    args = parser.parse_args()

    city_pool = get_city_pool()
    selected_cities = get_rotating_cities(city_pool, ROTATING_CITY_BATCH_SIZE)
    new_24h = current_new_leads_24h() if FREE_TIER_MODE else 0
    remaining_new_capacity = max(0, SCRAPER_DAILY_NEW_CAP - new_24h)

    log_event(
        "pipeline_start",
        target_market=TARGET_MARKET,
        selected_cities=selected_cities,
        niches=DEFAULT_NICHES,
        free_tier_mode=FREE_TIER_MODE,
        new24h=new_24h,
        daily_cap=SCRAPER_DAILY_NEW_CAP,
        remaining_capacity=remaining_new_capacity,
        skip_scrape=args.skip_scrape,
        skip_enrich=args.skip_enrich,
        skip_generate=args.skip_generate,
        skip_outreach=args.skip_outreach,
        dry_run=args.dry_run,
        requested_limit=args.limit,
        outreach_base_url=OUTREACH_BASE_URL,
        outreach_token_present=bool(OUTREACH_RUN_TOKEN),
        google_places_key_present=bool(PLACES_KEY),
    )

    if args.dry_run:
        log_event(
            "pipeline_dry_run_exit",
            target_market=TARGET_MARKET,
            selected_cities=selected_cities,
            new24h=new_24h,
            remaining_capacity=remaining_new_capacity,
            requested_limit=args.limit,
        )
        raise SystemExit(0)

    if not args.skip_scrape:
        if not PLACES_KEY:
            log_event("scrape_skipped", reason="google_places_api_key_missing")
        elif FREE_TIER_MODE and remaining_new_capacity <= 0:
            log_event("scrape_skipped", reason="daily_cap_reached")
        else:
            effective_limit = (
                min(args.limit, remaining_new_capacity)
                if FREE_TIER_MODE
                else args.limit
            )

            if effective_limit > 0:
                run_places_batch(
                    effective_limit,
                    selected_cities,
                    DEFAULT_NICHES,
                )
            else:
                log_event("scrape_skipped", reason="effective_limit_zero")
    else:
        log_event("scrape_skipped", reason="skip_scrape_flag")

    if args.skip_enrich:
        log_event("enrich_skipped", reason="skip_enrich_flag")
    else:
        run_enrich()

    if args.skip_generate:
        log_event("generate_skipped", reason="skip_generate_flag")
    else:
        run_generate_messages()

    if args.skip_outreach:
        log_event("outreach_trigger_skipped", reason="skip_outreach_flag")
    else:
        trigger_outreach()

    log_event(
        "pipeline_finish",
        target_market=TARGET_MARKET,
        selected_cities=selected_cities,
    )


if __name__ == "__main__":
    main()