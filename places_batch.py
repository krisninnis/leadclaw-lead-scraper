import argparse
import itertools
import sys
from subprocess import run

# Config-driven niche queries. Imported defensively so this script keeps
# working even if niche_config.py / niches.json are absent (backwards compat).
try:
    from niche_config import load_niches, queries_for
except Exception:  # pragma: no cover - fallback if config module missing
    load_niches = None
    queries_for = None

DEFAULT_CITIES = [
    "London",
    "Manchester",
    "Birmingham",
    "Leeds",
    "Liverpool",
    "Bristol",
    "Glasgow",
    "Edinburgh",
    "Newcastle",
    "Nottingham",
]

# Legacy hardcoded query map. Retained as a fallback so existing niches
# (hair, nails, lashes, brows, facials) that are not yet in niches.json keep
# their original search terms. beauty is also present in niches.json with the
# same queries, so behaviour is unchanged.
DEFAULT_QUERIES = {
    "beauty": ["beauty salon", "beauty clinic"],
    "hair": ["hair salon", "hairdresser"],
    "nails": ["nail salon", "nail bar"],
    "lashes": ["lash studio", "eyelash extensions"],
    "brows": ["brow bar", "eyebrow studio"],
    "facials": ["facial clinic", "skin clinic"],
}


def resolve_queries(niche: str) -> list[str]:
    """Resolve search queries for a niche, preferring niches.json config.

    Resolution order (first match wins):
      1. niches.json config (via niche_config.queries_for) if the niche is
         defined there.
      2. Legacy DEFAULT_QUERIES map (keeps hair/nails/etc. working).
      3. The niche string itself, e.g. ["plumber"], matching the old
         ``DEFAULT_QUERIES.get(niche, [niche])`` behaviour.
    """
    # 1. Config-driven, only when the niche is actually defined in niches.json.
    if load_niches is not None and queries_for is not None:
        try:
            if niche in load_niches():
                queries = queries_for(niche)
                if queries:
                    return queries
        except Exception:
            pass  # fall through to legacy behaviour on any config error

    # 2 & 3. Legacy map, then the niche string itself.
    return DEFAULT_QUERIES.get(niche, [niche])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cities", nargs="*", default=DEFAULT_CITIES)
    parser.add_argument("--niches", nargs="*", default=["beauty", "hair", "nails"])
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    jobs = []
    for city, niche in itertools.product(args.cities, args.niches):
        for query in resolve_queries(niche):
            jobs.append((city, niche, query))

    print(f"Running {len(jobs)} jobs...")

    for city, niche, query in jobs:
        cmd = [
            sys.executable,
            "places_run.py",
            "--city",
            city,
            "--niche",
            niche,
            "--query",
            query,
            "--limit",
            str(args.limit),
        ]
        print(" ".join(cmd))
        run(cmd, check=False)


if __name__ == "__main__":
    main()
