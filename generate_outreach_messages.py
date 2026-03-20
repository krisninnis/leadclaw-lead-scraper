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

# -----------------------------
# NEW DEMO-LED TEMPLATES
# -----------------------------

TEMPLATE_NO_CHAT = (
    "Hi, I came across {business}{city_hint} and wanted to reach out.\n\n"
    "I'm building LeadClaw, a brand-new startup for clinics that helps capture website enquiries when staff are busy or out of hours.\n\n"
    "It's free to get started, with an optional paid subscription later, and there's a no-obligation free trial as well.\n\n"
    "I put together a quick demo for your clinic here:\n"
    "{demo_url}\n\n"
    "Because we're still early, we're improving the product constantly and listening closely to feedback.\n\n"
    "We're also giving the first 100 clients founding-client perks like priority support, early feature access, and future benefits that won't be offered once we grow.\n\n"
    "Worth a quick look?\n\n"
    "Best,\n"
    "Kris\n"
    "LeadClaw"
)

TEMPLATE_CONTACT_FORM_ONLY = (
    "Hi, I came across {business}{city_hint} and noticed the site appears to rely mainly on a contact form.\n\n"
    "I'm building LeadClaw, a brand-new startup for clinics that helps capture and convert more website enquiries before visitors drop off.\n\n"
    "It's free to get started, with an optional paid subscription later, and there's a no-obligation free trial too.\n\n"
    "I put together a quick demo for your clinic here:\n"
    "{demo_url}\n\n"
    "Because the product is still early, we're shipping updates continuously and taking real feedback from clinics seriously.\n\n"
    "The first 100 clients will also get founding-client perks like priority support, early access to future features, and extra benefits we won't offer later.\n\n"
    "Worth a quick look?\n\n"
    "Best,\n"
    "Kris\n"
    "LeadClaw"
)

TEMPLATE_WEAK_BOOKING = (
    "Hi, I came across {business}{city_hint} and noticed there may be some friction in the booking journey.\n\n"
    "I'm building LeadClaw, a brand-new startup for clinics that helps capture missed enquiries and make follow-up easier.\n\n"
    "It's free to get started, with an optional paid subscription later, and there's a no-obligation free trial available.\n\n"
    "I put together a quick demo for your clinic here:\n"
    "{demo_url}\n\n"
    "We're still in the early stage, which means the product is improving all the time and early users get a real chance to shape what we build.\n\n"
    "The first 100 clients will also get founding-client perks like priority support, early feature access, and future benefits that won't be available once LeadClaw grows.\n\n"
    "Worth a quick look?\n\n"
    "Best,\n"
    "Kris\n"
    "LeadClaw"
)


def normalize_email(raw: str | None) -> str:
    value = str(raw or "").strip().lower()
    value = value.replace("mailto:", "")
    value = value.strip("<>\"'()[]{}")
    value = value.rstrip(".,;:)>]}'\"")
    return value


def normalize_phone(raw: str | None) -> str:
    return str(raw or "").strip()


def is_bad_email(email: str) -> bool:
    email = normalize_email(email)

    if not email or "@" not in email:
        return True

    if not EMAIL_RE.match(email):
        return True

    if any(email.startswith(prefix) for prefix in BLOCKED_EMAIL_PREFIXES):
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


def build_subject(angle, business):
    return f"Quick idea for {business}"


def choose_angle(row: dict):

    business = (row.get("company_name") or "your clinic").strip()
    city = (row.get("city") or "").strip()

    city_hint = f" in {city}" if city else ""

    notes = parse_notes(row.get("notes"))

    lead_id = row.get("id") or ""
    demo_url = f"{DEMO_URL}&lead={lead_id}" if lead_id else DEMO_URL

    has_contact_form = row.get("has_contact_form")

    notes_angle = notes.get("outreach_angle")

    has_booking_cta = parse_bool(notes.get("has_booking_cta"))

    primary_cta = notes.get("primary_cta")

    lead_fit_score = parse_int(notes.get("lead_fit_score")) or 0

    if notes_angle == "contact_form_only" or has_contact_form:

        angle = "contact_form_only"

        subject = build_subject(angle, business)

        message = TEMPLATE_CONTACT_FORM_ONLY.format(
            business=business,
            city_hint=city_hint,
            demo_url=demo_url,
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
            demo_url=demo_url,
        )

        return angle, subject, message

    angle = "no_live_chat"

    if lead_fit_score >= 70:
        angle = "no_live_chat"

    subject = build_subject(angle, business)

    message = TEMPLATE_NO_CHAT.format(
        business=business,
        city_hint=city_hint,
        demo_url=demo_url,
    )

    return angle, subject, message


def main():

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Missing Supabase env")

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    raw_rows = (
        supabase.table("leads")
        .select(
            "id,company_name,contact_email,contact_phone,city,score,status,"
            "has_live_chat,has_contact_form,google_rating,review_count,website,notes"
        )
        .in_("status", ["new", "queued"])
        .limit(100)
        .execute()
        .data
        or []
    )

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

        business = (row.get("company_name") or "your clinic").strip()

        contact = best_contact(row)

        angle, subject, message = choose_angle(row)

        out_lines.append(f"## {index}. {business}")
        out_lines.append(f"- lead_id: {row.get('id')}")
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