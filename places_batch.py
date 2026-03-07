import argparse
import itertools
import sys
from subprocess import run

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

DEFAULT_QUERIES = {
    "beauty": ["beauty salon", "beauty clinic"],
    "hair": ["hair salon", "hairdresser"],
    "nails": ["nail salon", "nail bar"],
    "lashes": ["lash studio", "eyelash extensions"],
    "brows": ["brow bar", "eyebrow studio"],
    "facials": ["facial clinic", "skin clinic"],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cities", nargs="*", default=DEFAULT_CITIES)
    parser.add_argument("--niches", nargs="*", default=["beauty", "hair", "nails"])
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    jobs = []
    for city, niche in itertools.product(args.cities, args.niches):
        for query in DEFAULT_QUERIES.get(niche, [niche]):
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
