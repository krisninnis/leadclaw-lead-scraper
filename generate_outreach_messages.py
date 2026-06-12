import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

APP_URL = os.getenv("OUTREACH_BASE_URL", "https://www.leadclaw.uk").rstrip("/")

DEMO_URL = os.getenv(
    "OUTREACH_DEMO_URL",
    "https://leadclaw-uk.vercel.app/demo?source=outreach",
).strip()

OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE = OUTPUT_DIR / "OUTREACH_MESSAGES_TODAY.md"

EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.I)

BLOCKED_EMAIL_PREFIXES = [
    "noreply@",
    "no-reply@",
    "donotreply@",
    "do-not-reply@",
]


def log_event(event: str, **fields):
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    print(json.dumps(payload, default=str))


def parse_cli_list(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None

    parsed: list[str] = []
    seen: set[str] = set()

    for value in values:
        for item in str(value).split(","):
            normalized = item.strip()
            if not normalized:
                continue

            dedupe_key = normalized.lower()
            if dedupe_key in seen:
                continue

            parsed.append(normalized)
            seen.add(dedupe_key)

    return parsed


def apply_lead_scope(query, niches: list[str] | None, created_after: str | None):
    if niches:
        query = query.in_("niche", niches)

    if created_after:
        query = query.gte("created_at", created_after)

    return query

# -----------------------------
# NEW DEMO-LED TEMPLATES
# -----------------------------

NICHE_CONTEXT = {
    "plumber": (
        "For plumbing businesses, missed calls while you're on jobs, "
        "after-hours enquiries, and emergency callout requests can easily "
        "arrive when nobody is free to reply."
    ),
    "electrician": (
        "For electricians, it can help capture website visitors before they "
        "leave, collect quote requests, and make callback capture easier when "
        "you're on-site."
    ),
    "heating": (
        "For heating engineers, boiler breakdowns, emergency heating enquiries, "
        "and out-of-hours requests are often urgent, so a fast response path "
        "matters."
    ),
    "roofer": (
        "For roofing businesses, storm damage enquiries and quote requests can "
        "come in quickly, and contact-form-only journeys can mean good leads "
        "sit waiting."
    ),
    "estate_agent": (
        "For estate agents, valuation requests and viewing enquiries are "
        "time-sensitive, so lead response speed can make a real difference."
    ),
    "garage": (
        "For garages, MOT bookings, service enquiries, and missed calls during "
        "workshop hours can be hard to catch while the team is busy."
    ),
}

NICHE_ALIASES = {
    "plumbers": "plumber",
    "electricians": "electrician",
    "heating_engineer": "heating",
    "heating_engineers": "heating",
    "roofers": "roofer",
    "roofing": "roofer",
    "estate_agents": "estate_agent",
    "estate agent": "estate_agent",
    "estate agents": "estate_agent",
    "garages": "garage",
}

TEMPLATE_NO_CHAT = (
    "Hi, I came across {business}{city_hint} and wanted to reach out.\n\n"
    "I'm building LeadClaw, a simple website assistant that helps small businesses capture enquiries when you're busy or out of hours, so fewer website visitors leave without getting in touch.\n\n"
    "{niche_context}\n\n"
    "It's free to get started, with an optional paid plan later, and there's a no-obligation free trial as well.\n\n"
    "I put together a quick demo for your business here:\n"
    "{demo_url}\n\n"
    "Because we're still early, we're improving the product constantly and listening closely to feedback.\n\n"
    "As we're just starting out, early clients also get founding-client perks like priority support and early access to new features.\n\n"
    "Worth a quick look?\n\n"
    "Best,\n"
    "Kris\n"
    "LeadClaw"
    "\n\n---\n"
    "Lead Claw Ltd (Company No. 13546017)\n"
    "206 Whitechapel Road, London, E1 1AA\n"
    "We found your business on Google Maps.\n"
    "Privacy policy: https://www.leadclaw.uk/legal/privacy\n"
    "Data rights: privacy@leadclaw.uk\n"
    "Unsubscribe: {unsubscribe_url}"
)

TEMPLATE_CONTACT_FORM_ONLY = (
    "Hi, I came across {business}{city_hint} and noticed the site relies mainly on a contact form.\n\n"
    "I'm building LeadClaw, a simple website assistant that helps small businesses capture and follow up on enquiries before visitors drop off, so you collect more contact details from the people already visiting your site.\n\n"
    "{niche_context}\n\n"
    "It's free to get started, with an optional paid plan later, and there's a no-obligation free trial too.\n\n"
    "I put together a quick demo for your business here:\n"
    "{demo_url}\n\n"
    "Because the product is still early, we're shipping updates continuously and taking real feedback seriously.\n\n"
    "As we're just starting out, early clients also get founding-client perks like priority support and early access to new features.\n\n"
    "Worth a quick look?\n\n"
    "Best,\n"
    "Kris\n"
    "LeadClaw"
    "\n\n---\n"
    "Lead Claw Ltd (Company No. 13546017)\n"
    "206 Whitechapel Road, London, E1 1AA\n"
    "We found your business on Google Maps.\n"
    "Privacy policy: https://www.leadclaw.uk/legal/privacy\n"
    "Data rights: privacy@leadclaw.uk\n"
    "Unsubscribe: {unsubscribe_url}"
)

TEMPLATE_WEAK_BOOKING = (
    "Hi, I came across {business}{city_hint} and noticed there may be some friction for people trying to get in touch or book.\n\n"
    "I'm building LeadClaw, a simple website assistant that helps small businesses capture missed enquiries and follow up automatically, so fewer leads slip through when you can't get to the phone.\n\n"
    "{niche_context}\n\n"
    "It's free to get started, with an optional paid plan later, and there's a no-obligation free trial available.\n\n"
    "I put together a quick demo for your business here:\n"
    "{demo_url}\n\n"
    "We're still in the early stage, which means the product is improving all the time and early users get a real say in what we build.\n\n"
    "As we're just starting out, early clients also get founding-client perks like priority support and early access to new features.\n\n"
    "Worth a quick look?\n\n"
    "Best,\n"
    "Kris\n"
    "LeadClaw"
    "\n\n---\n"
    "Lead Claw Ltd (Company No. 13546017)\n"
    "206 Whitechapel Road, London, E1 1AA\n"
    "We found your business on Google Maps.\n"
    "Privacy policy: https://www.leadclaw.uk/legal/privacy\n"
    "Data rights: privacy@leadclaw.uk\n"
    "Unsubscribe: {unsubscribe_url}"
)


def normalize_email(raw: str | None) -> str:
    value = str(raw or "").strip().lower()
    value = value.replace("mailto:", "")
    value = value.strip("<>\"'()[]{}")
    value = value.rstrip(".,;:)>]}'\"")
    return value


def normalize_phone(raw: str | None) -> str:
    return str(raw or "").strip()


BLOCKED_EMAIL_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico"}

def is_bad_email(email: str) -> bool:
    email = normalize_email(email)

    if not email or "@" not in email:
        return True

    if not EMAIL_RE.match(email):
        return True

    if any(email.startswith(prefix) for prefix in BLOCKED_EMAIL_PREFIXES):
        return True

    # Block image filenames mistakenly scraped as emails
    local_part = email.split("@")[0].lower()
    if any(local_part.endswith(ext.replace(".", "")) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]):
        return True
    
    # Block if domain looks like a file extension
    domain = email.split("@")[1].lower() if "@" in email else ""
    if any(domain.startswith(ext.lstrip(".")) for ext in BLOCKED_EMAIL_EXTENSIONS):
        return True

    return False

def best_contact(row: dict) -> str:
    email = normalize_email(row.get("contact_email"))
    phone = normalize_phone(row.get("contact_phone"))

    if email and not is_bad_email(email):
        return email

    if phone:
        return phone

    return "NO_CONTACT"


def has_valid_contact(row: dict) -> bool:
    email = normalize_email(row.get("contact_email"))
    phone = normalize_phone(row.get("contact_phone"))

    if email and not is_bad_email(email):
        return True

    if phone:
        return True

    return False
def parse_notes(notes: str | None) -> dict:
    parsed = {}
    raw = str(notes or "").strip()

    if not raw:
        return parsed

    for part in raw.split("|"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        parsed[k.strip()] = v.strip()

    return parsed


def parse_bool(value):
    if value is None:
        return None
    value = str(value).lower().strip()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def parse_int(value):
    try:
        return int(value)
    except:
        return None


def normalize_niche(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    normalized = raw.replace("-", "_").replace(" ", "_")
    return NICHE_ALIASES.get(normalized, normalized)


def niche_context_for(row: dict) -> str:
    niche = normalize_niche(row.get("niche"))
    return NICHE_CONTEXT.get(
        niche,
        "For small service businesses, LeadClaw helps capture website enquiries and follow-up details when the team is busy.",
    )


def build_subject(angle, business):
    return f"Quick idea for {business}"


def choose_angle(row: dict):

    business = (row.get("company_name") or "your business").strip()
    city = (row.get("city") or "").strip()

    city_hint = f" in {city}" if city else ""

    notes = parse_notes(row.get("notes"))

    lead_id = row.get("id") or ""
    _demo_base = DEMO_URL if "?" in DEMO_URL else f"{DEMO_URL}?source=outreach"
    demo_url = f"{_demo_base}&lead={lead_id}" if lead_id else _demo_base

    has_contact_form = row.get("has_contact_form")

    notes_angle = notes.get("outreach_angle")

    has_booking_cta = parse_bool(notes.get("has_booking_cta"))

    primary_cta = notes.get("primary_cta")

    lead_fit_score = parse_int(notes.get("lead_fit_score")) or 0
    niche_context = niche_context_for(row)

    if notes_angle == "contact_form_only" or has_contact_form:

        angle = "contact_form_only"

        subject = build_subject(angle, business)

        message = TEMPLATE_CONTACT_FORM_ONLY.format(
            business=business,
            city_hint=city_hint,
            niche_context=niche_context,
            demo_url=demo_url,
            unsubscribe_url = f"{APP_URL}/api/unsubscribe?email={normalize_email(row.get('contact_email'))}"
        )

        return angle, subject, message

    if (
        notes_angle == "weak_booking_flow"
        or has_booking_cta is False
        or primary_cta == "unknown"
    ):

        angle = "weak_booking_flow"

        subject = build_subject(angle, business)

        message = TEMPLATE_WEAK_BOOKING.format(
            business=business,
            city_hint=city_hint,
            niche_context=niche_context,
            demo_url=demo_url,
            unsubscribe_url = f"{APP_URL}/api/unsubscribe?email={normalize_email(row.get('contact_email'))}"
        )

        return angle, subject, message

    angle = "no_live_chat"

    if lead_fit_score >= 70:
        angle = "no_live_chat"

    subject = build_subject(angle, business)

    message = TEMPLATE_NO_CHAT.format(
        business=business,
        city_hint=city_hint,
        niche_context=niche_context,
        demo_url=demo_url,
        unsubscribe_url = f"{APP_URL}/api/unsubscribe?email={normalize_email(row.get('contact_email'))}"
    )

    return angle, subject, message


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--niches", nargs="+")
    parser.add_argument("--created-after")
    args = parser.parse_args()
    selected_niches = parse_cli_list(args.niches)
    created_after = args.created_after.strip() if args.created_after else None

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Missing Supabase env")

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    log_event(
        "generate_scope",
        niches=selected_niches,
        created_after=created_after,
        isolated=bool(selected_niches or created_after),
    )

    query = (
        supabase.table("leads")
        .select(
            "id,company_name,contact_email,contact_phone,city,score,status,"
            "has_live_chat,has_contact_form,google_rating,review_count,website,notes,"
            "pecr_classification,niche,created_at"
        )
        .in_("status", ["new", "queued"])
        .eq("pecr_classification", "corporate")
    )
    query = apply_lead_scope(query, selected_niches, created_after)
    raw_rows = query.limit(100).execute().data or []

    rows = [r for r in raw_rows if has_valid_contact(r)][:30]

    out_lines = []

    out_lines.append(
        f"# Generated Outreach Messages ({datetime.now(timezone.utc).isoformat()})"
    )
    out_lines.append("")
    out_lines.append(f"Base URL: {APP_URL}")
    out_lines.append(f"Demo URL: {DEMO_URL}")
    out_lines.append(f"Selected leads: {len(rows)}")
    out_lines.append(f"Filtered out: {max(0, len(raw_rows)-len(rows))}")
    out_lines.append("")

    updated = 0

    for index, row in enumerate(rows, start=1):

        business = (row.get("company_name") or "your business").strip()

        contact = best_contact(row)

        angle, subject, message = choose_angle(row)

        out_lines.append(f"## {index}. {business}")
        out_lines.append(f"- lead_id: {row.get('id')}")
        out_lines.append(f"- niche: {row.get('niche') or '-'}")
        out_lines.append(f"- contact: {contact}")
        out_lines.append(f"- city: {row.get('city') or '-'}")
        out_lines.append(f"- website: {row.get('website') or '-'}")
        out_lines.append(f"- score: {row.get('score') or 0}")
        out_lines.append(f"- google_rating: {row.get('google_rating') or '-'}")
        out_lines.append(f"- review_count: {row.get('review_count') or 0}")
        out_lines.append(f"- outreach_angle: {angle}")
        out_lines.append(f"- outreach_subject: {subject}")
        out_lines.append(f"- message: {message}")
        out_lines.append("")

        lead_id = row.get("id")

        if lead_id:

            (
                supabase.table("leads")
                .update(
                    {
                        "outreach_angle": angle,
                        "outreach_subject": subject,
                        "outreach_message": message,
                    }
                )
                .eq("id", lead_id)
                .execute()
            )

            updated += 1

    OUTPUT_FILE.write_text("\n".join(out_lines), encoding="utf-8")


    print(f"Wrote {len(rows)} messages -> {OUTPUT_FILE}")
    print(f"Updated {updated} leads in Supabase")


if __name__ == "__main__":
    main()
