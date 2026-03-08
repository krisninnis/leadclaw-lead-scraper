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

OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE = OUTPUT_DIR / "OUTREACH_MESSAGES_TODAY.md"

EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.I)

BLOCKED_EMAIL_SUBSTRINGS = [
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

BLOCKED_EMAIL_PREFIXES = [
    "noreply@",
    "no-reply@",
    "donotreply@",
    "do-not-reply@",
    "mailer-daemon@",
    "postmaster@",
]

ASSET_MARKERS = [
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
    "@2x",
    "@3x",
]

TEMPLATE_NO_CHAT = (
    "Hey {name}, quick one — I noticed {business}{city_hint} may be missing enquiries from "
    "people visiting the website when staff are busy or out of hours. "
    "I help clinics capture those missed enquiries automatically with a simple AI "
    "receptionist widget and a 7-day free trial. "
    "No rebuild needed, just a small script on your site. "
    "Want the 2-minute setup link?"
)

TEMPLATE_CONTACT_FORM_ONLY = (
    "Hey {name}, quick one — I noticed {business}{city_hint} appears to rely on a contact form "
    "rather than a live website assistant. "
    "That usually means some visitors leave before enquiring. "
    "I help clinics capture those missed enquiries automatically with a simple AI "
    "receptionist widget and a 7-day free trial. "
    "Want the 2-minute setup link?"
)

TEMPLATE_WEAK_BOOKING = (
    "Hey {name}, quick one — I noticed {business}{city_hint} may have some booking friction on the website, "
    "which can mean visitors drop off before enquiring. "
    "I help clinics capture those missed enquiries automatically with a simple AI "
    "receptionist widget and a 7-day free trial. "
    "No rebuild needed. Want the 2-minute setup link?"
)


def normalize_email(raw: str | None) -> str:
    value = str(raw or "").strip().lower()
    value = value.replace("mailto:", "")
    value = value.replace("\\u003c", "")
    value = value.replace("\\u003e", "")
    value = value.replace("&lt;", "")
    value = value.replace("&gt;", "")
    value = value.strip("<>\"'()[]{}")
    value = value.rstrip(".,;:)>]}'\"")
    return value


def normalize_phone(raw: str | None) -> str:
    return str(raw or "").strip()


def is_bad_email(email: str) -> bool:
    email = normalize_email(email)

    if not email or "@" not in email or email.count("@") != 1:
        return True

    if " " in email:
        return True

    if not EMAIL_RE.match(email):
        return True

    if any(email.startswith(prefix) for prefix in BLOCKED_EMAIL_PREFIXES):
        return True

    if any(part in email for part in BLOCKED_EMAIL_SUBSTRINGS):
        return True

    if "u003c" in email or "u003e" in email:
        return True

    if any(marker in email for marker in ASSET_MARKERS):
        return True

    local_part = email.split("@", 1)[0]
    if not local_part or len(local_part) > 80:
        return True

    if "logo" in local_part or "icon" in local_part or "banner" in local_part:
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
    parsed: dict[str, str] = {}
    raw = str(notes or "").strip()
    if not raw:
        return parsed

    for part in raw.split("|"):
        item = part.strip()
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        parsed[key.strip()] = value.strip()

    return parsed


def parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    lowered = str(value).strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return None


def parse_int(value: str | None) -> int | None:
    try:
        return int(str(value).strip())
    except Exception:
        return None


def build_subject(angle: str, business: str) -> str:
    if angle == "contact_form_only":
        return f"Quick idea for {business}"
    if angle == "weak_booking_flow":
        return f"Quick idea for {business}"
    return f"Quick idea for {business}"


def choose_angle(row: dict) -> tuple[str, str, str]:
    business = (row.get("company_name") or "your clinic").strip()
    city = (row.get("city") or "").strip()
    city_hint = f" in {city}" if city else ""
    notes_data = parse_notes(row.get("notes"))

    has_contact_form = row.get("has_contact_form")
    notes_angle = notes_data.get("outreach_angle")
    has_booking_cta = parse_bool(notes_data.get("has_booking_cta"))
    primary_cta = notes_data.get("primary_cta")
    lead_fit_score = parse_int(notes_data.get("lead_fit_score")) or 0

    if notes_angle == "contact_form_only" or has_contact_form:
        angle = "contact_form_only"
        subject = build_subject(angle, business)
        message = TEMPLATE_CONTACT_FORM_ONLY.format(
            name="there",
            business=business,
            city_hint=city_hint,
        )
        return angle, subject, message

    if notes_angle == "weak_booking_flow" or has_booking_cta is False or primary_cta == "unknown":
        angle = "weak_booking_flow"
        subject = build_subject(angle, business)
        message = TEMPLATE_WEAK_BOOKING.format(
            name="there",
            business=business,
            city_hint=city_hint,
        )
        return angle, subject, message

    angle = "no_live_chat"
    if lead_fit_score >= 70:
        angle = "no_live_chat"

    subject = build_subject(angle, business)
    message = TEMPLATE_NO_CHAT.format(
        name="there",
        business=business,
        city_hint=city_hint,
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
        .or_("contact_email.not.is.null,contact_phone.not.is.null")
        .or_("has_live_chat.is.false,has_live_chat.is.null")
        .order("score", desc=True)
        .limit(100)
        .execute()
        .data
        or []
    )

    rows = [row for row in raw_rows if has_valid_contact(row)][:30]

    out_lines: list[str] = []
    out_lines.append(
        f"# Generated Outreach Messages ({datetime.now(timezone.utc).isoformat()})"
    )
    out_lines.append("")
    out_lines.append(f"Base URL: {APP_URL}")
    out_lines.append(f"Selected leads: {len(rows)}")
    out_lines.append(f"Filtered out: {max(0, len(raw_rows) - len(rows))}")
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