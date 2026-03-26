import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
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

# ─── Companies House Classification ─────────────────────────────────────────
COMPANIES_HOUSE_API_KEY = os.getenv("COMPANIES_HOUSE_API_KEY", "").strip()
COMPLIANCE_ENABLED = os.getenv("COMPLIANCE_ENABLED", "1").strip() != "0"
# ─────────────────────────────────────────────────────────────────────────────

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

CORPORATE_TYPES = {
    "ltd",
    "private-limited-guarant-nsc",
    "private-limited-guarant-nsc-limited-exemption",
    "private-limited-shares-section-30-exemption",
    "private-unlimited",
    "private-unlimited-nsc",
    "plc",
    "llp",
    "limited-partnership",
    "registered-society-non-jurisdictional",
    "scottish-partnership",
}

NAME_MATCH_THRESHOLD = 0.80


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

    response = requests.post(url, headers=headers, timeout=180)
    response.raise_for_status()

    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text}

    log_event("outreach_trigger_finish", response=payload)


def clean_name(name: str) -> str:
    import re

    cleaned = name.lower().strip()
    for pattern in [
        r"\bltd\.?\b",
        r"\blimited\b",
        r"\bllp\b",
        r"\bplc\b",
        r"\binc\.?\b",
    ]:
        cleaned = re.sub(pattern, "", cleaned)
    cleaned = re.sub(r"^the\s+", "", cleaned)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def name_similarity(a: str, b: str) -> float:
    ca, cb = clean_name(a), clean_name(b)
    if not ca or not cb:
        return 0.0
    if ca == cb:
        return 1.0
    if ca in cb or cb in ca:
        return 0.85
    return SequenceMatcher(None, ca, cb).ratio()


def classify_lead_via_companies_house(business_name: str) -> dict:
    if not COMPANIES_HOUSE_API_KEY:
        return {
            "type": "unknown",
            "reason": "No Companies House API key configured",
            "company_number": None,
        }

    try:
        time.sleep(0.5)

        resp = requests.get(
            "https://api.company-information.service.gov.uk/search/companies",
            params={"q": business_name, "items_per_page": 5},
            auth=(COMPANIES_HOUSE_API_KEY, ""),
            timeout=10,
        )

        if resp.status_code == 429:
            log_event("companies_house_rate_limit", business=business_name)
            time.sleep(60)
            return classify_lead_via_companies_house(business_name)

        if resp.status_code != 200:
            log_event(
                "companies_house_error",
                status=resp.status_code,
                business=business_name,
            )
            return {
                "type": "unknown",
                "reason": f"API error {resp.status_code}",
                "company_number": None,
            }

        items = resp.json().get("items", [])
        if not items:
            return {
                "type": "individual",
                "reason": "No Companies House results — likely sole trader",
                "company_number": None,
            }

        best = None
        best_sim = 0.0
        for item in items:
            sim = name_similarity(business_name, item.get("title", ""))
            if sim > best_sim:
                best_sim = sim
                best = item

        if best and best_sim >= NAME_MATCH_THRESHOLD:
            status = best.get("company_status", "").lower()
            ctype = best.get("company_type", "").lower()
            number = best.get("company_number", "")

            if status == "active" and ctype in CORPORATE_TYPES:
                return {
                    "type": "corporate",
                    "reason": f"Active {ctype.upper()} — {best.get('title')} ({number}). Similarity: {best_sim:.0%}",
                    "company_number": number,
                }

            if status != "active":
                return {
                    "type": "unknown",
                    "reason": f"Company found but status is '{status}'. Manual review needed.",
                    "company_number": number,
                }

            return {
                "type": "unknown",
                "reason": f"Company type '{ctype}' not clearly corporate. Manual review needed.",
                "company_number": number,
            }

        closest = best.get("title", "N/A") if best else "N/A"
        return {
            "type": "unknown",
            "reason": f"Best match '{closest}' (similarity: {best_sim:.0%}) below threshold. Manual review.",
            "company_number": None,
        }

    except requests.RequestException as e:
        log_event("companies_house_exception", error=str(e), business=business_name)
        return {
            "type": "unknown",
            "reason": f"Request error: {e}",
            "company_number": None,
        }


def run_compliance_classification():
    """
    Classify all unclassified leads in Supabase.
    Updates each lead with:
      - pecr_classification: "corporate" | "individual" | "unknown"
      - pecr_reason: human-readable explanation
      - company_number: Companies House number (if found)
      - pecr_classified_at: timestamp
    """
    sb = supabase_client()

    unclassified = (
        sb.table("leads")
        .select("id, company_name, contact_email")
        .is_("pecr_classification", "null")
        .not_.is_("contact_email", "null")
        .limit(100)
        .execute()
        .data
        or []
    )

    if not unclassified:
        log_event("compliance_skip", reason="no_unclassified_leads")
        return

    log_event("compliance_start", count=len(unclassified))

    stats = {"corporate": 0, "individual": 0, "unknown": 0, "errors": 0}

    for lead in unclassified:
        lead_id = lead["id"]
        business_name = (lead.get("company_name") or "").strip()

        if not business_name:
            try:
                sb.table("leads").update(
                    {
                        "pecr_classification": "unknown",
                        "pecr_reason": "Missing business name",
                        "pecr_classified_at": datetime.now(timezone.utc).isoformat(),
                    }
                ).eq("id", lead_id).execute()
                stats["unknown"] += 1
            except Exception as e:
                stats["errors"] += 1
                log_event("compliance_update_error", lead_id=lead_id, error=str(e))
            continue

        result = classify_lead_via_companies_house(business_name)

        try:
            sb.table("leads").update(
                {
                    "pecr_classification": result["type"],
                    "pecr_reason": result["reason"],
                    "company_number": result.get("company_number"),
                    "pecr_classified_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", lead_id).execute()

            stats[result["type"]] += 1

            log_event(
                "compliance_classified",
                lead_id=lead_id,
                business=business_name,
                classification=result["type"],
                reason=result["reason"],
            )

        except Exception as e:
            stats["errors"] += 1
            log_event("compliance_update_error", lead_id=lead_id, error=str(e))

    log_event("compliance_finish", **stats)


def run_suppression_check():
    """
    Check suppressed emails before outreach.
    Any lead whose email is in email_suppressions gets marked as 'suppressed'
    so the outreach step skips it.
    """
    sb = supabase_client()

    suppressed_rows = (
        sb.table("email_suppressions")
        .select("email")
        .execute()
        .data
        or []
    )

    suppressed_emails = {
        str(row.get("email", "")).strip().lower()
        for row in suppressed_rows
        if row.get("email")
    }

    if not suppressed_emails:
        log_event("suppression_check", result="no_suppressed_emails")
        return

    leads = (
        sb.table("leads")
        .select("id, contact_email, status")
        .eq("pecr_classification", "corporate")
        .neq("status", "suppressed")
        .not_.is_("contact_email", "null")
        .limit(5000)
        .execute()
        .data
        or []
    )

    suppressed_count = 0

    for lead in leads:
        lead_email = str(lead.get("contact_email", "")).strip().lower()

        if not lead_email or lead_email not in suppressed_emails:
            continue

        sb.table("leads").update(
            {
                "status": "suppressed",
                "pecr_reason": "Email on suppression list — do not contact",
            }
        ).eq("id", lead["id"]).execute()

        suppressed_count += 1

    log_event(
        "suppression_check",
        total_checked=len(leads),
        suppressed=suppressed_count,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-scrape", action="store_true")
    parser.add_argument("--skip-enrich", action="store_true")
    parser.add_argument("--skip-compliance", action="store_true")
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
        skip_compliance=args.skip_compliance,
        skip_generate=args.skip_generate,
        skip_outreach=args.skip_outreach,
        dry_run=args.dry_run,
        requested_limit=args.limit,
        outreach_base_url=OUTREACH_BASE_URL,
        outreach_token_present=bool(OUTREACH_RUN_TOKEN),
        google_places_key_present=bool(PLACES_KEY),
        companies_house_key_present=bool(COMPANIES_HOUSE_API_KEY),
        compliance_enabled=COMPLIANCE_ENABLED,
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

    if args.skip_compliance:
        log_event("compliance_skipped", reason="skip_compliance_flag")
    elif not COMPLIANCE_ENABLED:
        log_event("compliance_skipped", reason="compliance_disabled_in_env")
    else:
        if not COMPANIES_HOUSE_API_KEY:
            log_event(
                "compliance_warning",
                reason="COMPANIES_HOUSE_API_KEY not set — leads will be classified as 'unknown' and held for manual review",
            )

        run_suppression_check()
        run_compliance_classification()

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