import os
from pathlib import Path
from datetime import datetime
from supabase import create_client
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / '.env')

SUPABASE_URL = os.getenv('SUPABASE_URL') or os.getenv('NEXT_PUBLIC_SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
APP_URL = os.getenv('OUTREACH_BASE_URL', 'https://leadclawai.vercel.app').rstrip('/')

TEMPLATE = (
    "Hey {name}, quick one — I help beauty clinics recover missed enquiries automatically "
    "(plus rebooking nudges) with a 7-day free trial. "
    "No rebuild needed, just a small script on your site. "
    "Want the 2-minute setup link for {business}?"
)


def clean_name(raw: str | None):
    if not raw:
        return 'there'
    s = raw.strip()
    if not s:
        return 'there'
    # naive first-name extraction
    return s.split()[0][:30]


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError('Missing Supabase env')

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    rows = (
        sb.table('leads')
        .select('id,company_name,contact_email,contact_phone,city,score,status')
        .in_('status', ['new', 'queued'])
        .order('score', desc=True)
        .limit(30)
        .execute()
        .data
        or []
    )

    out_lines = []
    out_lines.append(f'# Generated Outreach Messages ({datetime.utcnow().isoformat()}Z)')
    out_lines.append('')

    for i, r in enumerate(rows, start=1):
        business = (r.get('company_name') or 'your clinic').strip()
        name = 'there'
        msg = TEMPLATE.format(name=name, business=business)
        contact = r.get('contact_email') or r.get('contact_phone') or 'NO_CONTACT'
        out_lines.append(f'## {i}. {business}')
        out_lines.append(f'- lead_id: {r.get("id")}')
        out_lines.append(f'- contact: {contact}')
        out_lines.append(f'- city: {r.get("city") or "-"}')
        out_lines.append(f'- score: {r.get("score") or 0}')
        out_lines.append(f'- message: {msg}')
        out_lines.append('')

    out_path = Path('C:/Users/KRIS/.openclaw/workspace/playbooks/OUTREACH_MESSAGES_TODAY.md')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text('\n'.join(out_lines), encoding='utf-8')
    print(f'Wrote {len(rows)} messages -> {out_path}')


if __name__ == '__main__':
    main()
