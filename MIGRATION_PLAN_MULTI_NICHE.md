# LeadClaw Scraper — Multi-Industry Migration Plan

**Scope:** Architecture & audit only. No code changed, nothing committed.
**Author role:** Lead-gen engineering / PECR compliance / SaaS growth / Python architecture
**Date:** 11 June 2026
**Goal:** Turn a beauty-clinic-specific scraper into a config-driven, multi-industry lead engine for plumbers, electricians, heating engineers, roofers, pest control, landscapers, garages, estate agents, beauty clinics, and dental clinics.

---

## 1. Pipeline audit (current state)

The pipeline is orchestrated by `auto_pipeline.py` and runs five stages:

`scrape (places_batch → places_run) → enrich emails (enrich_emails) → compliance classify + suppression (auto_pipeline) → generate messages (generate_outreach_messages) → trigger outreach (POST to LeadClaw app)`

| Stage | File | What it does | Niche-coupling |
|---|---|---|---|
| Discovery | `places_batch.py` | Fan-out over cities × niches → calls `places_run.py` per query | **High** — `DEFAULT_QUERIES` is all beauty |
| Fetch + score | `places_run.py` | Google Places text search + details; fetches each site; scores fit; filters | **High** — booking tools + thresholds beauty-tuned |
| Email enrich | `enrich_emails.py` | Scrapes business site for a contact email; vendor/asset filtering | **Low** — niche-agnostic |
| Orchestration | `auto_pipeline.py` | City rotation, daily caps, Companies House PECR classify, suppression, dry-run | **Medium** — `DEFAULT_NICHES=["beauty"]`, no niche rotation |
| Message gen | `generate_outreach_messages.py` | Picks angle, fills templates, writes to Supabase | **Low (now)** — templates already neutralised in Stage 1; angle logic is generic |
| Send | `auto_pipeline.py` → app `/api/outreach/run` | App sends + records | **None** in this repo |

Data flow is unchanged across niches: Google Places → business website → Supabase `leads`. **No new data source is needed to add industries** — every target industry is discoverable via Places text search and has a public website to scan.

---

## 2. Every file where industry targeting is hardcoded

| File | Line(s) | Hardcoded item | Type |
|---|---|---|---|
| `places_batch.py` | ~18–25 | `DEFAULT_QUERIES` dict (beauty/hair/nails/lashes/brows/facials) | **Queries** |
| `places_batch.py` | ~32 | `--niches` default `["beauty","hair","nails"]` | **Niche default** |
| `auto_pipeline.py` | 92 | `DEFAULT_NICHES = ["beauty"]` (the automated daily run) | **Niche default** |
| `places_run.py` | 43–58 | `BOOKING_PATTERNS` includes Fresha/Treatwell/Phorest/Booksy (beauty SaaS) | **Scoring assumption** |
| `places_run.py` | 262–279 | `should_keep_lead` thresholds: `review_count < 5` drop, `rating < 3.5` drop | **Scoring assumption** |
| `places_run.py` | 206–258 | `score_lead` weighting tuned to salon norms | **Scoring assumption** |
| `places_run.py` | 383–384 | CLI defaults `--niche beauty`, `--query "beauty salon"` | **Niche default** |
| `run-pipeline.ps1` | 8 | `--niches beauty aesthetics skin laser cosmetic` | **Niche default** |
| `README.md` | 24–53 | Beauty/nail-salon examples | **Docs** |
| `generate_outreach_messages.py` | templates | ✅ Already niche-neutral (Stage 1) | n/a |

Everything else (`enrich_emails.py`, the Companies House classifier, suppression, the Supabase schema usage) is industry-agnostic.

---

## 3. Beauty-specific items, itemised

**Beauty-specific queries** (`places_batch.py` `DEFAULT_QUERIES`):
`beauty salon`, `beauty clinic`, `hair salon`, `hairdresser`, `nail salon`, `nail bar`, `lash studio`, `eyelash extensions`, `brow bar`, `eyebrow studio`, `facial clinic`, `skin clinic`. Plus PowerShell runner: `aesthetics`, `skin`, `laser`, `cosmetic`.

**Clinic-specific assumptions:**
- The `niche` field default everywhere is `beauty`.
- `query = f"{args.query} {args.city} uk"` (`places_run.py`) assumes a UK consumer-local-service search — fine for all 10 niches, no change needed.
- The "found you on Google Maps" provenance line assumes a Maps-listed business — true for all target niches.

**Clinic-specific scoring logic** (`places_run.py`):
- `BOOKING_PATTERNS` rewards detection of **beauty booking platforms** (Fresha, Treatwell, Phorest, Booksy). Trades/garages/estate agents use different tools (Jobber, ServiceM8, Housecall Pro, Calendly, Acuity, Checkatrade, Rightmove/Zoopla widgets), so booking detection silently under-fires for non-beauty niches → those leads look "weak booking" even when they're not.
- `should_keep_lead`: drops any business with **<5 Google reviews** or **rating <3.5**. Salons accumulate many reviews; a one-van plumber or independent garage often has fewer reviews despite being a great LeadClaw fit. This threshold will over-filter trades.
- `score_lead`: review-count and rating bands (`>=20` reviews, `>=4.2` rating) are salon-calibrated.
- None of this is *broken* for other niches — it's *miscalibrated*. The site-signal logic (no live chat, contact-form-only, weak booking) is genuinely niche-agnostic and transfers well.

**Clinic-specific outreach logic:**
- Already removed in Stage 1. The three templates and the angle-selection (`choose_angle`: `contact_form_only` / `weak_booking_flow` / `no_live_chat`) are now industry-neutral. The `notes` packing/parsing that feeds angle selection is generic. **No outreach change required for the migration.**

---

## 4. New niche configuration system (design)

**Principle:** one source of truth for *what* to search and *how* to score it per industry; code reads config, never hardcodes a niche.

### 4.1 Config file — `niches.json` (new file, repo root)

```json
{
  "beauty":      { "queries": ["beauty salon", "beauty clinic", "aesthetics clinic", "skin clinic"],
                   "min_reviews": 5, "min_rating": 3.5,
                   "booking_tools": ["fresha", "treatwell", "phorest", "booksy", "timely", "cliniko"] },

  "dental":      { "queries": ["dentist", "dental practice", "dental clinic", "private dentist"],
                   "min_reviews": 5, "min_rating": 3.5,
                   "booking_tools": ["dentally", "software of excellence", "zesty"] },

  "plumber":     { "queries": ["plumber", "emergency plumber", "plumbing services", "boiler repair"],
                   "min_reviews": 3, "min_rating": 3.2,
                   "booking_tools": ["checkatrade", "jobber", "servicem8", "housecall"] },

  "electrician": { "queries": ["electrician", "electrical contractor", "emergency electrician", "rewiring"],
                   "min_reviews": 3, "min_rating": 3.2,
                   "booking_tools": ["checkatrade", "jobber", "servicem8", "tradify"] },

  "heating":     { "queries": ["heating engineer", "boiler installation", "gas engineer", "central heating"],
                   "min_reviews": 3, "min_rating": 3.2,
                   "booking_tools": ["checkatrade", "jobber", "servicem8", "commusoft"] },

  "roofer":      { "queries": ["roofer", "roofing company", "roof repairs", "flat roofing"],
                   "min_reviews": 3, "min_rating": 3.2,
                   "booking_tools": ["checkatrade", "mybuilder", "jobber"] },

  "pest_control":{ "queries": ["pest control", "pest control services", "rat removal", "wasp nest removal"],
                   "min_reviews": 3, "min_rating": 3.2,
                   "booking_tools": ["servicem8", "jobber", "pestpac"] },

  "landscaper":  { "queries": ["landscaper", "landscaping company", "garden design", "driveways and patios"],
                   "min_reviews": 3, "min_rating": 3.2,
                   "booking_tools": ["checkatrade", "mybuilder", "jobber"] },

  "garage":      { "queries": ["car garage", "mot test centre", "car servicing", "auto repair"],
                   "min_reviews": 4, "min_rating": 3.3,
                   "booking_tools": ["bookmygarage", "calendly", "acuity", "garagehive"] },

  "estate_agent":{ "queries": ["estate agent", "letting agent", "property management", "lettings"],
                   "min_reviews": 4, "min_rating": 3.3,
                   "booking_tools": ["rightmove", "zoopla", "calendly", "acuity"] }
}
```

Notes:
- `queries` replaces the per-niche list in `DEFAULT_QUERIES`.
- `min_reviews` / `min_rating` make `should_keep_lead` thresholds **per-niche** (trades get lower bars).
- `booking_tools` are merged into the global `BOOKING_PATTERNS` at scan time so booking detection fires correctly per industry.
- Optional future keys: `value_prop_hint` (to vary outreach emphasis), `entity_bias` (expected incorporation rate, for compliance prioritisation).

### 4.2 Loader — `niche_config.py` (new, small)

```python
# pseudocode
import json, functools
from pathlib import Path

BASE = Path(__file__).resolve().parent

@functools.lru_cache
def load_niches() -> dict:
    return json.loads((BASE / "niches.json").read_text(encoding="utf-8"))

def queries_for(niche: str) -> list[str]:
    return load_niches().get(niche, {}).get("queries", [niche])

def thresholds_for(niche: str) -> tuple[int, float]:
    n = load_niches().get(niche, {})
    return n.get("min_reviews", 5), n.get("min_rating", 3.5)

def booking_tools_for(niche: str) -> list[str]:
    return load_niches().get(niche, {}).get("booking_tools", [])
```

### 4.3 Wiring (described, not implemented)

- `places_batch.py`: replace `DEFAULT_QUERIES` lookup with `queries_for(niche)`; `--niches` default reads `load_niches().keys()` or a configured shortlist.
- `places_run.py`: `should_keep_lead` and `score_lead` take `min_reviews`/`min_rating` from `thresholds_for(niche)`; `scan_website` merges `booking_tools_for(niche)` into `BOOKING_PATTERNS`. `niche` already flows through `places_run.py` as `--niche`, so plumbing it into scoring is a small change.
- `auto_pipeline.py`: `DEFAULT_NICHES` becomes a configured/rotated list (mirror the existing `get_rotating_cities` pattern with a `get_rotating_niches`).

This keeps the architecture identical — only the *parameters* become data, not code.

---

## 5–7. Niche recommendations

### 5. Safest first expansion niche → **Plumbers**
High incorporation rate (many are Ltd → clean PECR corporate gate), acute and obvious "missed call = lost job" pain that maps perfectly to LeadClaw's AI-receptionist pitch, abundant on Google Maps, and low reputational sensitivity (no health/regulated-advertising overlay). Easiest to validate end-to-end.

### 6. Highest-converting niche → **Heating engineers / boiler installers** (with plumbers a close second)
High job value (£2k–£5k installs) means one captured lead pays for LeadClaw many times over, so willingness-to-pay is strong. They are frequently on jobs and physically unable to answer the phone — the exact gap LeadClaw closes — and demand is seasonal-urgent (no heat = call the next result). Strong ability-to-pay + strong pain = best expected conversion.

### 7. Easiest niche for PECR compliance → **Estate / letting agents**
Almost universally incorporated limited companies (very clean "corporate subscriber" classification under PECR, so the Companies House gate passes them through with high confidence), they publish role inboxes (`info@`, `lettings@`) rather than personal addresses (lower UK-GDPR personal-data exposure), and they are an established B2B-marketing-receptive audience. Dental and beauty are *messier* for PECR because more are sole traders/partnerships and more expose personal-format emails.

> Combined read: start with **plumbers** (safe + easy to prove), monetise hardest with **heating engineers**, and use **estate agents** as the lowest-compliance-risk lane to scale volume once the system is proven.

**Handle with care:** dental and any medical-adjacent beauty (laser/injectables) carry higher data sensitivity and advertising-standards overlay — keep them behind the corporate-only gate and personal-email exclusion before scaling.

---

## 8. Dry-run mode design (scrape + enrich + score, never send)

**Problem with today's `--dry-run`:** it logs the plan and `raise SystemExit(0)` *before* scraping (`auto_pipeline.py` ~534–543). It's a "preview", not a real no-send run.

**What you want:** run the full collection + scoring + message-generation path, write everything to Supabase as inspectable rows, and guarantee **zero outreach**.

This is already 90% achievable with existing flags — the architecture just needs one explicit, safe mode rather than a flag combo people can get wrong.

### Recommended design — a true `--dry-run` ("safe mode")

Redefine `--dry-run` to mean **"do the work, never contact anyone"**:

| Stage | Dry-run behaviour |
|---|---|
| Scrape (`places_batch`/`places_run`) | **Runs** |
| Enrich emails | **Runs** |
| Compliance classify + suppression | **Runs** (so you can inspect PECR outcomes) |
| Generate messages | **Runs** but writes rows with `status="dry_run"` (or `outreach_status="preview"`) instead of `new`/`queued` |
| Trigger outreach (`/api/outreach/run`) | **Hard-skipped** + asserted off |

Implementation shape (described only):
- Replace the early `SystemExit` block with: `effective_skip_outreach = args.skip_outreach or args.dry_run`.
- In `generate_outreach_messages.py`, if a `DRY_RUN` env/flag is set, tag generated rows so the app's sender can never pick them up (belt-and-braces beyond skipping the HTTP call).
- Keep the existing `--dry-run` "plan only" behaviour available as a separate `--plan-only` flag so nothing regresses.
- Add a one-line guard in `trigger_outreach()`: if `DRY_RUN` truthy → `log_event("outreach_blocked_dry_run")` and return, so even a stray call can't send.

**Two layers of safety** (skip the HTTP trigger *and* tag rows un-sendable) is the right pattern for a system that emails real businesses — a single missed flag should never result in an accidental send.

For a quick win **today with zero code change**, the equivalent is:
```bash
python auto_pipeline.py --limit 2 --skip-outreach
# scrapes, enriches, classifies, generates messages into Supabase + output/OUTREACH_MESSAGES_TODAY.md; sends nothing
```
The `--dry-run` redesign just makes that intent first-class and harder to get wrong.

---

## 9. Files requiring modification (exact list)

| File | Change | Touch size |
|---|---|---|
| `niches.json` | **New** — niche → queries/thresholds/booking tools | new file |
| `niche_config.py` | **New** — loader (`queries_for`, `thresholds_for`, `booking_tools_for`) | new file |
| `places_batch.py` | Read queries + niche list from config instead of `DEFAULT_QUERIES` | small |
| `places_run.py` | Per-niche thresholds in `should_keep_lead`/`score_lead`; merge per-niche booking tools in `scan_website`; CLI defaults | medium |
| `auto_pipeline.py` | `DEFAULT_NICHES` → configured/rotated niches; redefine `--dry-run` as safe-mode; add `--plan-only`; dry-run guard in `trigger_outreach()` | medium |
| `generate_outreach_messages.py` | Tag rows as un-sendable under dry-run (defensive) | small |
| `run-pipeline.ps1` | Replace hardcoded beauty niches with config-driven list | small |
| `README.md` | Document niches.json, multi-industry usage, dry-run | small |
| Supabase (out of repo) | Optional `dry_run` status value / `outreach_status` column for preview rows | external |

**Do-not-touch:** `enrich_emails.py` (already generic), the Companies House classifier, suppression logic, the compliance footer/unsubscribe wording (already neutral + compliant), and API tokens/env.

---

## 10. Effort estimate

**Low effort (≈half a day):**
- Create `niches.json` + `niche_config.py` loader.
- Point `places_batch.py` and `auto_pipeline.py` `DEFAULT_NICHES` at config.
- Update `run-pipeline.ps1` and `README.md`.
- Add the defensive dry-run guard in `trigger_outreach()`.

**Medium effort (≈1–2 days):**
- Per-niche thresholds + booking-tool merging in `places_run.py` (`should_keep_lead`, `score_lead`, `scan_website`), with a small test harness over a handful of cached HTML samples per niche.
- Redefine `--dry-run` as true safe-mode + add `--plan-only`; tag preview rows in `generate_outreach_messages.py`.
- Add `get_rotating_niches` mirroring city rotation.

**High effort (≈3–5 days, optional/later):**
- Per-niche scoring *calibration* from real data (review-count/rating distributions differ a lot between a salon and a roofer) — requires a dry-run data-collection pass, then tuning.
- Compliance hardening that becomes more important at multi-industry scale: robots.txt respect + politeness delay in `places_run.py`/`enrich_emails.py`, and exclusion of personal-format emails from outreach (vs current "deprioritise").
- Optional per-niche `value_prop_hint` so outreach emphasis adapts (missed-call angle for trades, enquiry-capture angle for agents) without re-introducing hardcoded niche copy.

---

## Recommended staged rollout

1. **Stage 2a (Low):** ship `niches.json` + loader; wire discovery only; keep `DEFAULT_NICHES=["beauty"]` so nothing changes in production yet.
2. **Stage 2b (Low/Med):** add `plumber` to config; run **dry-run** (`--skip-outreach` today, or the new `--dry-run` once built) at `--limit 2`; inspect lead quality + PECR classifications in Supabase. No sending.
3. **Stage 3 (Med):** per-niche thresholds + booking tools so plumber leads score fairly; re-run dry-run; compare yield vs beauty.
4. **Stage 4 (Med):** formalise true `--dry-run` safe-mode + un-sendable row tagging; review a generated batch by hand.
5. **Stage 5 (Med/High):** enable live outreach for plumbers only, low caps; then layer in heating engineers (revenue) and estate agents (compliance-easy volume); finally calibrate scoring per niche from collected data.

*Architecture and audit only — no code modified, nothing committed.*
