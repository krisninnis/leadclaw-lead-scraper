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


def run_places_batch(limit: int, cities: list[str], niches: list[str]):
    city_args = " ".join(cities)
    niche_args = " ".join(niches)
    cmd = (
        f'"{PYTHON_BIN}" places_batch.py --limit {limit} '
        f"--cities {city_args} --niches {niche_args}"
    )
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


def canonical(value: str | None):
    return (value or "").strip().lower()


def choose_key(row: dict):
    website = canonical(row.get("website"))
    email = canonical(row.get("contact_email"))
    company = canonical(row.get("company_name"))
    city = canonical(row.get("city"))

    if website:
        return f"w:{website}"
    if email:
        return f"e:{email}"
    return f"c:{company}|{city}"


def outreach_remaining_today(default_cap: int = 20):
    sb = supabase_client()
    cap = default_cap
    cfg_rows = []

    try:
        cfg_rows = (
            sb.table("ops_config")
            .select("key,value")
            .eq("key", "OUTREACH_DAILY_CAP")
            .limit(1)
            .execute()
            .data
            or []
        )
    except Exception:
        cfg_rows = []

    if cfg_rows:
        try:
            cap = int(str(cfg_rows[0].get("value") or default_cap))
        except Exception:
            cap = default_cap

    since = (
        datetime.now(timezone.utc)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .isoformat()
    )

    sent_rows = (
        sb.table("outreach_events")
        .select("id")
        .eq("channel", "email")
        .eq("event_type", "sent")
        .gte("created_at", since)
        .limit(2000)
        .execute()
        .data
        or []
    )

    sent_today = len(sent_rows)
    remaining = max(0, cap - sent_today)

    print(
        f"[pipeline] outreach quota: sent_today={sent_today} "
        f"cap={cap} remaining={remaining}"
    )

    return {"cap": cap, "sentToday": sent_today, "remaining": remaining}


def enforce_daily_new_cap(cap: int):
    sb = supabase_client()
    since = iso_hours_ago(24)

    rows = (
        sb.table("leads")
        .select("id,score,created_at")
        .eq("status", "new")
        .gte("created_at", since)
        .order("score", desc=True)
        .order("created_at", desc=True)
        .execute()
        .data
        or []
    )

    if len(rows) <= cap:
        print(f"[pipeline] daily cap ok: new_24h={len(rows)} cap={cap}")
        return {"new24h": len(rows), "paused": 0}

    overflow = rows[cap:]
    overflow_ids = [row["id"] for row in overflow if row.get("id")]

    if overflow_ids:
        (
            sb.table("leads")
            .update(
                {
                    "status": "paused_free_cap",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .in_("id", overflow_ids)
            .execute()
        )

    print(
        f"[pipeline] daily cap enforced: new_24h={len(rows)} "
        f"cap={cap} paused={len(overflow_ids)}"
    )

    return {"new24h": len(rows), "paused": len(overflow_ids)}


def dedupe_recent_new_leads(hours: int = 48):
    sb = supabase_client()
    since = iso_hours_ago(hours)

    data = (
        sb.table("leads")
        .select("id,company_name,website,contact_email,city,score,status,created_at")
        .eq("status", "new")
        .gte("created_at", since)
        .execute()
        .data
        or []
    )

    grouped = defaultdict(list)
    for row in data:
        grouped[choose_key(row)].append(row)

    duplicates = []
    for _, rows in grouped.items():
        if len(rows) < 2:
            continue

        rows.sort(
            key=lambda row: (int(row.get("score") or 0), row.get("created_at") or ""),
            reverse=True,
        )

        for duplicate in rows[1:]:
            duplicates.append(duplicate["id"])

    if duplicates:
        (
            sb.table("leads")
            .update(
                {
                    "status": "duplicate",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .in_("id", duplicates)
            .execute()
        )

    print(
        f"[pipeline] dedupe complete: checked={len(data)} "
        f"duplicates_marked={len(duplicates)}"
    )

    return {"checked": len(data), "duplicates": len(duplicates)}


def enrich_emails():
    cmd = f'"{PYTHON_BIN}" enrich_emails.py'
    print(f"[pipeline] running: {cmd}")
    code = os.system(cmd)
    if code != 0:
        print(f"[pipeline] enrich warnings: exit={code}")


def generate_outreach_messages():
    cmd = f'"{PYTHON_BIN}" generate_outreach_messages.py'
    print(f"[pipeline] running: {cmd}")
    code = os.system(cmd)
    if code != 0:
        print(f"[pipeline] outreach message generation warnings: exit={code}")


def trigger_outreach():
    if not OUTREACH_RUN_TOKEN:
        print("[pipeline] outreach skipped: OUTREACH_RUN_TOKEN missing")
        return {"ok": False, "reason": "missing_token"}

    url = f"{OUTREACH_BASE_URL}/api/outreach/run"

    try:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {OUTREACH_RUN_TOKEN}"},
            timeout=60,
        )
    except requests.RequestException as exc:
        print(f"[pipeline] outreach failed: request error: {exc}")
        return {"ok": False, "reason": str(exc), "status": None}

    if response.status_code >= 400:
        print(f"[pipeline] outreach failed: {response.status_code} {response.text}")
        return {"ok": False, "reason": response.text, "status": response.status_code}

    data = response.json()
    print(
        f"[pipeline] outreach ok: sent={data.get('sentCount', 0)} "
        f"skipped={data.get('skippedCount', 0)}"
    )
    return {"ok": True, **data}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-scrape", action="store_true")
    parser.add_argument("--skip-outreach", action="store_true")
    parser.add_argument("--limit", type=int, default=4, help="per places_batch job")
    parser.add_argument("--dedupe-hours", type=int, default=72)
    parser.add_argument("--cities", nargs="*", default=["London", "Manchester"])
    parser.add_argument("--niches", nargs="*", default=["beauty"])
    args = parser.parse_args()

    quota = {"cap": None, "sentToday": None, "remaining": None}
    if FREE_TIER_MODE:
        quota = outreach_remaining_today(20)

    if not args.skip_scrape:
        if FREE_TIER_MODE and quota.get("remaining", 0) <= 0:
            print("[pipeline] scrape skipped: outreach daily cap already reached")
        elif not PLACES_KEY:
            print("[pipeline] scrape skipped: GOOGLE_PLACES_API_KEY missing")
        else:
            run_places_batch(args.limit, args.cities, args.niches)

    dedupe = dedupe_recent_new_leads(args.dedupe_hours)

    cap = {"new24h": None, "paused": 0}
    if FREE_TIER_MODE:
        cap = enforce_daily_new_cap(SCRAPER_DAILY_NEW_CAP)

    outreach = {"ok": None, "reason": "skipped"}
    if not args.skip_outreach:
        enrich_emails()
        generate_outreach_messages()
        outreach = trigger_outreach()

    print(
        {
            "ok": True,
            "freeTier": FREE_TIER_MODE,
            "quota": quota,
            "cap": cap,
            "dedupe": dedupe,
            "outreach_messages_generated": not args.skip_outreach,
            "outreach": outreach,
        }
    )


if __name__ == "__main__":
    main()