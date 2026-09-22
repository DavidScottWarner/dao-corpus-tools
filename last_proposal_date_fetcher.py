"""
Look up the most recent proposal date for each Snapshot space ID
listed in space_ids.txt.

This script only pulls data. It does not choose a sample.
"""

import csv
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

API_URL = "https://hub.snapshot.org/graphql"
PAUSE_SECONDS = 1
MAX_TRIES = 3
RETRY_WAIT_SECONDS = 5

FOLDER = Path(__file__).resolve().parent
SPACE_IDS_PATH = FOLDER / "space_ids.txt"
OUTPUT_FOLDER = FOLDER / "output"

COLUMNS = [
    "space_id",
    "last_proposal_date",
    "last_proposal_title",
    "status",
]


def load_space_ids(path):
    """Read space IDs from a text file, one per line. Skip blanks."""
    ids = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            space_id = line.strip()
            if space_id:
                ids.append(space_id)
    return ids


def fetch_latest_proposal(space_id):
    """Ask Snapshot for the most recent proposal for one space."""
    query = f"""
    query {{
      proposals(
        first: 1,
        where: {{ space: "{space_id}" }},
        orderBy: "created",
        orderDirection: desc
      ) {{
        title
        created
      }}
    }}
    """
    response = requests.post(API_URL, json={"query": query}, timeout=60)
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload["data"]["proposals"]


def fetch_with_retries(space_id):
    """Try up to MAX_TRIES times. Returns (proposals, None) or (None, error)."""
    last_error = None
    for attempt in range(1, MAX_TRIES + 1):
        try:
            return fetch_latest_proposal(space_id), None
        except Exception as error:
            last_error = error
            print(f"  Request failed (try {attempt} of {MAX_TRIES}): {error}")
            if attempt < MAX_TRIES:
                print(f"  Waiting {RETRY_WAIT_SECONDS} seconds, then retrying.")
                time.sleep(RETRY_WAIT_SECONDS)
    return None, last_error


def timestamp_to_date(created):
    """Convert a Unix timestamp to YYYY-MM-DD in UTC."""
    return datetime.fromtimestamp(created, tz=timezone.utc).strftime("%Y-%m-%d")


def build_row(space_id, proposals, error):
    """Turn one API result into one CSV row."""
    if error is not None:
        return {
            "space_id": space_id,
            "last_proposal_date": "",
            "last_proposal_title": "",
            "status": "error",
        }

    if not proposals:
        return {
            "space_id": space_id,
            "last_proposal_date": "",
            "last_proposal_title": "",
            "status": "no proposals",
        }

    proposal = proposals[0]
    return {
        "space_id": space_id,
        "last_proposal_date": timestamp_to_date(proposal["created"]),
        "last_proposal_title": proposal.get("title") or "",
        "status": "ok",
    }


def write_csv(path, rows):
    OUTPUT_FOLDER.mkdir(exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows, output_path):
    ok = sum(1 for row in rows if row["status"] == "ok")
    no_proposals = sum(1 for row in rows if row["status"] == "no proposals")
    errors = sum(1 for row in rows if row["status"] == "error")

    print()
    print(f"Wrote {len(rows)} rows to {output_path}")
    print(f"Spaces looked up: {len(rows)}")
    print(f"Returned a date: {ok}")
    print(f"No proposals: {no_proposals}")
    print(f"Errors: {errors}")


def main():
    space_ids = load_space_ids(SPACE_IDS_PATH)
    total = len(space_ids)
    print(f"Looking up {total} spaces from {SPACE_IDS_PATH.name}")

    rows = []
    for index, space_id in enumerate(space_ids, start=1):
        proposals, error = fetch_with_retries(space_id)
        row = build_row(space_id, proposals, error)
        rows.append(row)

        if row["status"] == "ok":
            print(f"[{index}/{total}] {space_id} -> {row['last_proposal_date']} (ok)")
        else:
            print(f"[{index}/{total}] {space_id} -> {row['status']}")

        if index < total:
            time.sleep(PAUSE_SECONDS)

    today = date.today().isoformat()
    output_path = OUTPUT_FOLDER / f"last_proposal_dates_{today}.csv"
    write_csv(output_path, rows)
    print_summary(rows, output_path)


if __name__ == "__main__":
    main()
