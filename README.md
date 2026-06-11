# Lead Scraper Bot (Compliant MVP)

This bot collects public business leads, scores them, and can queue outreach-ready records into Supabase.

## Safety/Compliance
- Public business data only
- No CAPTCHA bypassing
- Respect robots.txt and site Terms
- Include unsubscribe in outreach
- Start with low-volume batches

## Setup
```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
copy .env.example .env
```

Fill `.env` values.

## Run (manual public web mode)
```bash
.venv\Scripts\python run.py --query "beauty salon london" --max-sites 30
.venv\Scripts\python run.py --query "nail salon manchester" --max-sites 30
```

## Run (Google Places API mode)
Add `GOOGLE_PLACES_API_KEY` to `.env`, then:
```bash
.venv\Scripts\python places_run.py --city London --niche beauty --query "beauty salon" --limit 30
.venv\Scripts\python places_run.py --city Manchester --niche nails --query "nail salon" --limit 30
```

## Run (multi-city batch mode)
One command to pull multiple cities + niches:
```bash
.venv\Scripts\python places_batch.py --limit 20
```
Custom example:
```bash
.venv\Scripts\python places_batch.py --cities London Manchester Birmingham --niches beauty nails lashes --limit 15
```

## Niche configuration (`niches.json`)

Niches are defined in `niches.json`, loaded by the read-only helpers in
`niche_config.py` (`load_niches`, `get_niche_config`, `queries_for`,
`thresholds_for`, `booking_tools_for`, `list_niches`). Each niche entry has:

- `queries` – Google Places search terms used by `places_batch.py`
- `min_reviews` / `min_rating` – advisory thresholds (read-only helpers; not
  yet wired into live scoring, which still lives in `places_run.py`)
- `booking_tools` – booking-platform keywords associated with the niche

Configured niches: `beauty`, `dental`, `plumber`, `electrician`, `heating`,
`roofer`, `pest_control`, `landscaper`, `garage`, `estate_agent`.

`places_batch.py` resolves a niche's queries in this order: (1) `niches.json`
config if the niche is defined there, (2) the legacy built-in `DEFAULT_QUERIES`
map (keeps `hair`, `nails`, `lashes`, `brows`, `facials` working), (3) the
niche string itself as a single query. Adding a niche to `niches.json` does
**not** enable it in the daily automated run — `auto_pipeline.py` still targets
`DEFAULT_NICHES = ["beauty"]` only.

### Safe test (no outreach sent)
Inspect lead quality for a niche without contacting anyone. Use a tiny limit
and always pass `--skip-outreach`:
```bash
.venv\Scripts\python places_batch.py --cities London --niches plumber --limit 2
.venv\Scripts\python auto_pipeline.py --limit 2 --cities London --niches beauty --skip-outreach
```
`--skip-outreach` runs scrape + enrich + compliance + message generation but
**does not** trigger the outreach endpoint, so no emails are sent.

> ⚠️ **Do not run live outreach for a newly enabled niche until the first
> generated message batch has been manually reviewed in Supabase.** Trades and
> other non-beauty niches are config-only for now and are intentionally NOT in
> the daily pipeline defaults.

## What it does
1. Pulls structured local business data from Google Places API (or public web mode)
2. Extracts website/phone/address
3. Scores lead quality
4. Inserts into Supabase `leads` table (`source=google-places` or `web-public`)

## Fully automated pipeline (scrape -> dedupe -> outreach)
```bash
.venv\Scripts\python auto_pipeline.py --limit 4 --cities London Manchester --niches beauty
```

Options:
- `--skip-scrape` (dedupe + outreach only)
- `--skip-outreach` (scrape + dedupe only)
- `--dedupe-hours 72`

This pipeline:
1. Runs `places_batch.py`
2. Marks duplicate leads as `status=duplicate` (website > email > company+city key)
3. Triggers app outreach endpoint (`/api/outreach/run`)

Required `.env` values for full automation:
- `SUPABASE_URL` (or `NEXT_PUBLIC_SUPABASE_URL`)
- `SUPABASE_SERVICE_ROLE_KEY`
- `GOOGLE_PLACES_API_KEY` (optional; pipeline gracefully skips scraping if missing)
- `OUTREACH_BASE_URL`
- `OUTREACH_RUN_TOKEN`
- `FREE_TIER_MODE=1`
- `SCRAPER_DAILY_NEW_CAP=40`

Windows scheduled runner:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-pipeline.ps1
```

## Next
- Add email enrichment provider (business-only)
- Add lead-quality threshold by niche/service intent
