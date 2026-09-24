"""
Download every Snapshot proposal for the spaces listed in spaces_to_fetch.csv.

Writes one text file per proposal under corpus/proposals/, plus
corpus/manifest.csv and corpus/fetch_summary.csv.

Use --test N to fetch only N proposals per space while trying things out.
"""

import argparse
import csv
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

API_URL = "https://hub.snapshot.org/graphql"
PAGE_SIZE = 1000
PAUSE_SECONDS = 1
MAX_TRIES = 3
RETRY_WAIT_SECONDS = 5
STUB_WORD_LIMIT = 50

FOLDER = Path(__file__).resolve().parent
SPACES_CSV = FOLDER / "spaces_to_fetch.csv"
CORPUS_FOLDER = FOLDER / "corpus"
PROPOSALS_FOLDER = CORPUS_FOLDER / "proposals"
MANIFEST_PATH = CORPUS_FOLDER / "manifest.csv"
SUMMARY_PATH = CORPUS_FOLDER / "fetch_summary.csv"

MANIFEST_COLUMNS = [
    "organization",
    "stratum",
    "space_id",
    "proposal_id",
    "date",
    "title",
    "author",
    "state",
    "votes",
    "scores_total",
    "quorum",
    "word_count",
    "stub_flag",
    "file_path",
    "url",
    "discussion",
]

SUMMARY_COLUMNS = [
    "run_started_at",
    "organization",
    "space_id",
    "proposals_fetched",
    "proposals_count_reported",
    "match",
    "status",
]


# --- Reusable helpers (for later tools / other APIs) ---


def pause_for_rate_limit(seconds=PAUSE_SECONDS):
    """Wait briefly between requests so we stay under the rate limit."""
    time.sleep(seconds)


def request_with_retries(query, label="request"):
    """
    POST a GraphQL query. Retry a few times on failure.
    Returns (payload, None) on success, or (None, error) after giving up.
    """
    last_error = None
    for attempt in range(1, MAX_TRIES + 1):
        try:
            response = requests.post(API_URL, json={"query": query}, timeout=120)
            response.raise_for_status()
            payload = response.json()
            if payload.get("errors"):
                raise RuntimeError(payload["errors"])
            return payload, None
        except Exception as error:
            last_error = error
            print(f"  {label} failed (try {attempt} of {MAX_TRIES}): {error}")
            if attempt < MAX_TRIES:
                print(f"  Waiting {RETRY_WAIT_SECONDS} seconds, then retrying.")
                time.sleep(RETRY_WAIT_SECONDS)
    return None, last_error


def write_csv(path, rows, fieldnames):
    """Write rows to a UTF-8 CSV with BOM so Excel opens it cleanly."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_progress(message):
    """Print a progress line."""
    print(message)


# --- Script-specific helpers ---


def organization_slug(organization):
    """Turn an organization name into a folder name: lowercase with hyphens."""
    slug = organization.lower()
    slug = slug.replace("'", "").replace("'", "")
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def timestamp_to_date(value):
    """Convert a Unix timestamp to YYYY-MM-DD in UTC."""
    if value is None or value == "":
        return ""
    return datetime.fromtimestamp(int(value), tz=timezone.utc).strftime("%Y-%m-%d")


def word_count(body):
    """Count whitespace-separated words in the proposal body only."""
    if not body:
        return 0
    return len(body.split())


def format_scores(choices, scores):
    """Pair each choice with its score: 'For: 150; Against: 0'."""
    choices = choices or []
    scores = scores or []
    pairs = []
    for index, choice in enumerate(choices):
        if index < len(scores):
            pairs.append(f"{choice}: {scores[index]}")
        else:
            pairs.append(f"{choice}: (missing score)")
    if len(scores) > len(choices):
        pairs.append(f"(extra scores without choices: {scores[len(choices):]})")
    return "; ".join(pairs)


def proposal_url(proposal, space_id):
    """Prefer Snapshot's link field; otherwise build a snapshot.box URL."""
    link = proposal.get("link")
    if link:
        return link
    proposal_id = proposal.get("id", "")
    return f"https://snapshot.box/#/s:{space_id}/proposal/{proposal_id}"


def discussion_value(proposal):
    """Return the discussion link, or 'none' if Snapshot left it empty."""
    discussion = (proposal.get("discussion") or "").strip()
    return discussion if discussion else "none"


def load_spaces(path):
    """Read organization / space_id / stratum rows from spaces_to_fetch.csv."""
    rows = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                {
                    "organization": row["organization"].strip(),
                    "space_id": row["space_id"].strip(),
                    "stratum": row["stratum"].strip(),
                }
            )
    return rows


def fetch_proposals_count(space_id):
    """Ask Snapshot how many proposals it reports for this space."""
    query = f"""
    query {{
      space(id: "{space_id}") {{
        id
        proposalsCount
      }}
    }}
    """
    payload, error = request_with_retries(query, label=f"proposalsCount for {space_id}")
    if error is not None:
        return None, error
    space = (payload.get("data") or {}).get("space")
    if not space:
        return None, RuntimeError(f"Space not found: {space_id}")
    return space.get("proposalsCount"), None


def fetch_proposals_page(space_id, created_lte=None):
    """Fetch one page of proposals for a space, newest first."""
    if created_lte is None:
        where_clause = f'space: "{space_id}"'
    else:
        where_clause = f'space: "{space_id}", created_lte: {created_lte}'

    query = f"""
    query {{
      proposals(
        first: {PAGE_SIZE},
        where: {{ {where_clause} }},
        orderBy: "created",
        orderDirection: desc
      ) {{
        id
        title
        body
        author
        created
        start
        end
        state
        choices
        votes
        scores
        scores_total
        quorum
        link
        discussion
      }}
    }}
    """
    payload, error = request_with_retries(query, label=f"proposals for {space_id}")
    if error is not None:
        return None, error
    return (payload.get("data") or {}).get("proposals") or [], None


def build_text_file(proposal, space_id):
    """Build the UTF-8 text content for one proposal file."""
    body = proposal.get("body") or ""
    choices = proposal.get("choices") or []
    lines = [
        f"title: {proposal.get('title') or ''}",
        f"space_id: {space_id}",
        f"author: {proposal.get('author') or ''}",
        f"created: {timestamp_to_date(proposal.get('created'))}",
        f"start: {timestamp_to_date(proposal.get('start'))}",
        f"end: {timestamp_to_date(proposal.get('end'))}",
        f"state: {proposal.get('state') or ''}",
        f"choices: {'; '.join(choices)}",
        f"scores: {format_scores(choices, proposal.get('scores'))}",
        f"scores_total: {proposal.get('scores_total') if proposal.get('scores_total') is not None else ''}",
        f"quorum: {proposal.get('quorum') if proposal.get('quorum') is not None else ''}",
        f"votes: {proposal.get('votes') if proposal.get('votes') is not None else ''}",
        f"url: {proposal_url(proposal, space_id)}",
        f"discussion: {discussion_value(proposal)}",
        "",
        body,
    ]
    # Ensure the file ends with a newline.
    return "\n".join(lines).rstrip("\n") + "\n"


def write_proposal_file(proposal, organization, space_id):
    """
    Write one proposal text file if it does not already exist.
    Returns (path_relative_to_folder, was_written).
    """
    org_folder = PROPOSALS_FOLDER / organization_slug(organization)
    org_folder.mkdir(parents=True, exist_ok=True)

    proposal_id = proposal.get("id", "")
    date_str = timestamp_to_date(proposal.get("created"))
    filename = f"{date_str}_{proposal_id}.txt"
    path = org_folder / filename
    relative = path.relative_to(FOLDER).as_posix()

    if path.exists():
        return relative, False

    path.write_text(build_text_file(proposal, space_id), encoding="utf-8")
    return relative, True


def build_manifest_row(proposal, organization, stratum, space_id, file_path):
    """Turn one proposal into one manifest.csv row."""
    body = proposal.get("body") or ""
    words = word_count(body)
    return {
        "organization": organization,
        "stratum": stratum,
        "space_id": space_id,
        "proposal_id": proposal.get("id", ""),
        "date": timestamp_to_date(proposal.get("created")),
        "title": proposal.get("title") or "",
        "author": proposal.get("author") or "",
        "state": proposal.get("state") or "",
        "votes": proposal.get("votes") if proposal.get("votes") is not None else "",
        "scores_total": (
            proposal.get("scores_total")
            if proposal.get("scores_total") is not None
            else ""
        ),
        "quorum": proposal.get("quorum") if proposal.get("quorum") is not None else "",
        "word_count": words,
        "stub_flag": "TRUE" if words < STUB_WORD_LIMIT else "FALSE",
        "file_path": file_path,
        "url": proposal_url(proposal, space_id),
        "discussion": discussion_value(proposal),
    }


def fetch_space(space_row, test_limit, run_started_at):
    """
    Fetch all (or --test N) proposals for one space.
    Returns (manifest_rows, summary_row).
    """
    organization = space_row["organization"]
    space_id = space_row["space_id"]
    stratum = space_row["stratum"]

    print_progress(f"\n=== {organization} ({space_id}) ===")

    reported_count, count_error = fetch_proposals_count(space_id)
    pause_for_rate_limit()

    if count_error is not None:
        print_progress(f"  Could not get proposalsCount. Continuing anyway: {count_error}")
        reported_count = ""

    seen_ids = set()
    manifest_rows = []
    created_lte = None
    status = "ok"
    wrote_count = 0
    skipped_existing = 0

    while True:
        if test_limit is not None and len(seen_ids) >= test_limit:
            print_progress(f"  Reached --test limit of {test_limit} for this space.")
            break

        proposals, error = fetch_proposals_page(space_id, created_lte=created_lte)
        if error is not None:
            print_progress(f"  Giving up on {space_id} after failed requests: {error}")
            status = "error"
            break

        if not proposals:
            print_progress(f"  Empty page. Done with {space_id}.")
            break

        new_proposals = []
        for proposal in proposals:
            proposal_id = proposal.get("id")
            if proposal_id in seen_ids:
                continue
            new_proposals.append(proposal)

        if not new_proposals:
            print_progress(
                f"  No new proposals on this page; stopping space {space_id}."
            )
            break

        for proposal in new_proposals:
            if test_limit is not None and len(seen_ids) >= test_limit:
                break

            proposal_id = proposal.get("id")
            seen_ids.add(proposal_id)
            file_path, was_written = write_proposal_file(
                proposal, organization, space_id
            )
            if was_written:
                wrote_count += 1
            else:
                skipped_existing += 1

            manifest_rows.append(
                build_manifest_row(
                    proposal, organization, stratum, space_id, file_path
                )
            )

        print_progress(
            f"  Progress: {len(seen_ids)} unique so far "
            f"(wrote {wrote_count}, already on disk {skipped_existing})"
        )

        if test_limit is not None and len(seen_ids) >= test_limit:
            print_progress(f"  Reached --test limit of {test_limit} for this space.")
            break

        # Next page: include proposals created at or before the oldest on this page.
        oldest_created = proposals[-1].get("created")
        if oldest_created is None:
            print_progress(
                f"  Last proposal on page had no created timestamp; stopping {space_id}."
            )
            break
        created_lte = oldest_created
        pause_for_rate_limit()

    fetched = len(manifest_rows)
    if status != "error":
        if reported_count == "" or reported_count is None:
            match = ""
            status = "ok"
        elif test_limit is not None:
            # Partial test run: do not treat short counts as a mismatch.
            match = "n/a (--test)"
            status = "ok"
        elif int(reported_count) == fetched:
            match = "TRUE"
            status = "ok"
        else:
            match = "FALSE"
            status = "mismatch"
            print_progress(
                f"  MISMATCH: fetched {fetched}, Snapshot reports {reported_count}"
            )
    else:
        match = "FALSE"

    summary_row = {
        "run_started_at": run_started_at,
        "organization": organization,
        "space_id": space_id,
        "proposals_fetched": fetched,
        "proposals_count_reported": (
            reported_count if reported_count is not None else ""
        ),
        "match": match,
        "status": status,
    }
    return manifest_rows, summary_row


def print_summary_table(summary_rows):
    """Print a short end-of-run table."""
    print_progress("\n=== Fetch summary ===")
    print_progress(
        f"{'space_id':<30} {'fetched':>8} {'reported':>10} {'status':<10}"
    )
    print_progress("-" * 62)
    for row in summary_rows:
        print_progress(
            f"{row['space_id']:<30} "
            f"{str(row['proposals_fetched']):>8} "
            f"{str(row['proposals_count_reported']):>10} "
            f"{row['status']:<10}"
        )

    mismatches = [row for row in summary_rows if row["status"] == "mismatch"]
    errors = [row for row in summary_rows if row["status"] == "error"]
    print_progress(
        f"\nSpaces: {len(summary_rows)} | "
        f"mismatches: {len(mismatches)} | "
        f"errors: {len(errors)} | "
        f"proposals in manifest: {sum(int(r['proposals_fetched']) for r in summary_rows)}"
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Download Snapshot proposals for spaces in spaces_to_fetch.csv"
    )
    parser.add_argument(
        "--test",
        type=int,
        metavar="N",
        help="Fetch only N proposals per space (for testing)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    test_limit = args.test
    if test_limit is not None and test_limit < 1:
        raise SystemExit("--test N must be a positive whole number")

    spaces = load_spaces(SPACES_CSV)
    run_started_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    print_progress(f"Starting proposal fetch at {run_started_at}")
    print_progress(f"Spaces to fetch: {len(spaces)}")
    if test_limit is not None:
        print_progress(f"TEST MODE: at most {test_limit} proposals per space")

    CORPUS_FOLDER.mkdir(parents=True, exist_ok=True)
    PROPOSALS_FOLDER.mkdir(parents=True, exist_ok=True)

    all_manifest_rows = []
    summary_rows = []

    for space_row in spaces:
        manifest_rows, summary_row = fetch_space(
            space_row, test_limit=test_limit, run_started_at=run_started_at
        )
        all_manifest_rows.extend(manifest_rows)
        summary_rows.append(summary_row)
        pause_for_rate_limit()

    write_csv(MANIFEST_PATH, all_manifest_rows, MANIFEST_COLUMNS)
    write_csv(SUMMARY_PATH, summary_rows, SUMMARY_COLUMNS)
    print_summary_table(summary_rows)
    print_progress(f"\nWrote {MANIFEST_PATH.relative_to(FOLDER)}")
    print_progress(f"Wrote {SUMMARY_PATH.relative_to(FOLDER)}")


if __name__ == "__main__":
    main()
