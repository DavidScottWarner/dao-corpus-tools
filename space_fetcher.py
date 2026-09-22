"""
Download every Snapshot space into a dated CSV.

This script only pulls data. It does not choose a sample.
"""

import csv
import time
from collections import Counter
from datetime import date
from pathlib import Path

import requests

API_URL = "https://hub.snapshot.org/graphql"
PAGE_SIZE = 1000
PAUSE_SECONDS = 1
MAX_TRIES = 3
RETRY_WAIT_SECONDS = 5

FOLDER = Path(__file__).resolve().parent
STRATA_PATH = FOLDER / "strata.csv"
OUTPUT_FOLDER = FOLDER / "output"

COLUMNS = [
    "id",
    "name",
    "categories",
    "category_count",
    "first_category",
    "stratum",
    "followersCount",
    "proposalsCount",
    "votesCount",
    "votes_per_proposal",
    "verified",
]


def load_strata(path):
    """Read category -> stratum from strata.csv."""
    mapping = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            mapping[row["category"]] = row["stratum"]
    return mapping


def fetch_page(skip):
    """Ask Snapshot for one page of spaces. Raises on HTTP or GraphQL errors."""
    query = f"""
    query {{
      spaces(first: {PAGE_SIZE}, skip: {skip}, orderBy: "created", orderDirection: asc) {{
        id
        name
        categories
        followersCount
        proposalsCount
        votesCount
        verified
      }}
    }}
    """
    response = requests.post(API_URL, json={"query": query}, timeout=60)
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload["data"]["spaces"]


def fetch_page_with_retries(skip):
    """Try a page up to MAX_TRIES times. Returns (spaces, None) or (None, error)."""
    last_error = None
    for attempt in range(1, MAX_TRIES + 1):
        try:
            return fetch_page(skip), None
        except Exception as error:
            last_error = error
            print(f"  Page failed (try {attempt} of {MAX_TRIES}): {error}")
            if attempt < MAX_TRIES:
                print(f"  Waiting {RETRY_WAIT_SECONDS} seconds, then retrying.")
                time.sleep(RETRY_WAIT_SECONDS)
    return None, last_error


def build_row(space, strata):
    """Turn one Snapshot space into one CSV row."""
    raw_categories = space.get("categories") or []
    first_category = raw_categories[0] if raw_categories else ""
    proposals = space.get("proposalsCount") or 0
    votes = space.get("votesCount") or 0

    if proposals == 0:
        votes_per_proposal = ""
    else:
        votes_per_proposal = round(votes / proposals, 1)

    return {
        "id": space.get("id", ""),
        "name": space.get("name", ""),
        "categories": ";".join(raw_categories),
        "category_count": len(raw_categories),
        "first_category": first_category,
        "stratum": strata.get(first_category, "Unlisted"),
        "followersCount": space.get("followersCount", ""),
        "proposalsCount": proposals,
        "votesCount": votes,
        "votes_per_proposal": votes_per_proposal,
        "verified": space.get("verified", ""),
    }


def write_csv(path, rows):
    OUTPUT_FOLDER.mkdir(exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows, duplicates_removed, output_path):
    no_category = sum(1 for row in rows if row["category_count"] == 0)
    verified = sum(1 for row in rows if row["verified"] in (True, "true", "True"))
    stratum_counts = Counter(row["stratum"] for row in rows)

    print()
    print(f"Wrote {len(rows)} spaces to {output_path}")
    print(f"Duplicates removed: {duplicates_removed}")
    print(f"Spaces with no category: {no_category}")
    print(f"Verified spaces: {verified}")
    print("Spaces per stratum:")
    for name, count in sorted(stratum_counts.items()):
        print(f"  {name}: {count}")


def main():
    strata = load_strata(STRATA_PATH)
    rows = []
    seen_ids = set()
    duplicates_removed = 0
    skip = 0
    page_number = 1
    stopped_early = False

    while True:
        print(f"Page {page_number} (skip {skip}): requesting...")
        spaces, error = fetch_page_with_retries(skip)

        if error is not None:
            print("Giving up on this page. Writing everything collected so far.")
            stopped_early = True
            break

        if not spaces:
            print(f"Page {page_number} (skip {skip}): empty page. Done.")
            break

        new_on_page = 0
        for space in spaces:
            space_id = space.get("id")
            if space_id in seen_ids:
                duplicates_removed += 1
                continue
            seen_ids.add(space_id)
            rows.append(build_row(space, strata))
            new_on_page += 1

        print(
            f"Page {page_number} (skip {skip}): "
            f"received {len(spaces)}, unique so far {len(rows)}"
        )

        skip += PAGE_SIZE
        page_number += 1
        time.sleep(PAUSE_SECONDS)

    today = date.today().isoformat()
    output_path = OUTPUT_FOLDER / f"spaces_{today}.csv"
    write_csv(output_path, rows)

    if stopped_early:
        print("Finished early because a page failed after three tries.")

    print_summary(rows, duplicates_removed, output_path)


if __name__ == "__main__":
    main()
