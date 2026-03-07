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
