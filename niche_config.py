"""Config-driven niche lookup for LeadClaw.

Loads niche definitions from ``niches.json`` (sitting next to this file) and
exposes small, safe read-only helpers. Designed to be backwards compatible:

* No network calls.
* No environment variables required.
* Config is loaded once and cached.
* Every helper returns a sane fallback when a niche (or the file) is missing,
  so callers never crash on an unknown niche.

IMPORTANT: This module is metadata only. It does NOT change scraping
behaviour, scoring thresholds, the daily pipeline target, or outreach.
``auto_pipeline.py`` still owns ``DEFAULT_NICHES`` and ``places_run.py`` still
owns the live scoring thresholds.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
NICHES_FILE = BASE_DIR / "niches.json"

# Fallbacks used when niches.json is missing/unreadable or a niche is absent.
# These mirror the conservative global behaviour already in places_run.py
# (min rating 3.5, min reviews 5) so nothing gets stricter by accident.
_FALLBACK_MIN_REVIEWS = 5
_FALLBACK_MIN_RATING = 3.5
_FALLBACK_BOOKING_TOOLS: list[str] = []

# Module-level cache. ``None`` means "not loaded yet".
_CACHE: dict[str, dict[str, Any]] | None = None


def _load_raw() -> dict[str, dict[str, Any]]:
    """Read and parse niches.json, returning the inner niches mapping.

    Never raises: any error (missing file, bad JSON, wrong shape) results in an
    empty mapping so callers fall back to safe defaults.
    """
    try:
        with NICHES_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}

    if not isinstance(data, dict):
        return {}

    niches = data.get("niches", {})
    if not isinstance(niches, dict):
        return {}

    # Keep only well-formed entries (dict values), normalise keys to str.
    cleaned: dict[str, dict[str, Any]] = {}
    for key, value in niches.items():
        if isinstance(value, dict):
            cleaned[str(key)] = value
    return cleaned


def load_niches(force_reload: bool = False) -> dict[str, dict[str, Any]]:
    """Return the full niche mapping, loading and caching on first use.

    Pass ``force_reload=True`` to re-read the file (e.g. in tests).
    """
    global _CACHE
    if _CACHE is None or force_reload:
        _CACHE = _load_raw()
    return _CACHE


def list_niches() -> list[str]:
    """Return the sorted list of configured niche names (may be empty)."""
    return sorted(load_niches().keys())


def get_niche_config(niche: str) -> dict[str, Any]:
    """Return the raw config dict for a niche, or a safe fallback.

    The fallback always includes the same keys as a real entry, with
    ``queries`` defaulting to ``[niche]`` so the niche string itself is used as
    a search term when unknown.
    """
    niche = (niche or "").strip()
    config = load_niches().get(niche)
    if isinstance(config, dict):
        return config

    return {
        "queries": [niche] if niche else [],
        "min_reviews": _FALLBACK_MIN_REVIEWS,
        "min_rating": _FALLBACK_MIN_RATING,
        "booking_tools": list(_FALLBACK_BOOKING_TOOLS),
    }


def queries_for(niche: str) -> list[str]:
    """Return search queries for a niche.

    Falls back to ``[niche]`` (search the niche string itself) when the niche
    is unknown or has no/invalid queries configured. Never returns an empty
    list for a non-empty niche.
    """
    niche = (niche or "").strip()
    config = load_niches().get(niche)
    if isinstance(config, dict):
        queries = config.get("queries")
        if isinstance(queries, list):
            cleaned = [str(q) for q in queries if str(q).strip()]
            if cleaned:
                return cleaned

    return [niche] if niche else []


def thresholds_for(niche: str) -> dict[str, float]:
    """Return ``{"min_reviews": int, "min_rating": float}`` for a niche.

    Read-only advisory values. NOT currently wired into scoring. Falls back to
    conservative global defaults when missing or malformed.
    """
    config = get_niche_config(niche)

    try:
        min_reviews = int(config.get("min_reviews", _FALLBACK_MIN_REVIEWS))
    except (TypeError, ValueError):
        min_reviews = _FALLBACK_MIN_REVIEWS

    try:
        min_rating = float(config.get("min_rating", _FALLBACK_MIN_RATING))
    except (TypeError, ValueError):
        min_rating = _FALLBACK_MIN_RATING

    return {"min_reviews": min_reviews, "min_rating": min_rating}


def booking_tools_for(niche: str) -> list[str]:
    """Return the configured booking-tool keywords for a niche.

    Read-only helper. Falls back to an empty list when missing or malformed.
    """
    config = get_niche_config(niche)
    tools = config.get("booking_tools", _FALLBACK_BOOKING_TOOLS)
    if isinstance(tools, list):
        return [str(t) for t in tools if str(t).strip()]
    return list(_FALLBACK_BOOKING_TOOLS)


if __name__ == "__main__":
    # Manual smoke test (no network, no env). Safe to run.
    print("Configured niches:", list_niches())
    for _n in ["beauty", "plumber", "does-not-exist"]:
        print(_n, "->", queries_for(_n), thresholds_for(_n), booking_tools_for(_n))
