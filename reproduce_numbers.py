"""
Recreate the numbers reported in the paper from files already on disk.

This script does not contact Snapshot.
"""

import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

FOLDER = Path(__file__).resolve().parent
SPACES_PATH = FOLDER / "output" / "spaces_2026-09-13.csv"
DATES_PATH = FOLDER / "output" / "last_proposal_dates_2026-09-19.csv"
MANIFEST_PATH = FOLDER / "corpus" / "manifest.csv"
TABLE1_PATH = FOLDER / "output" / "table1.csv"

CUTOFF = date(2025, 9, 13)

STRATUM_ORDER = [
    "Protocol and Infrastructure",
    "Capital",
    "Public Goods and Service",
    "Social and Cultural",
]

# Printed names for the activity table. Unlisted spaces have no category.
ACTIVITY_LABELS = {
    "Protocol and Infrastructure": "Protocol and Infrastructure",
    "Capital": "Capital",
    "Public Goods and Service": "Public Goods and Service",
    "Social and Cultural": "Social and Cultural",
    "Unlisted": "Uncategorized",
    "Unassigned": "Unassigned",
}
ACTIVITY_ORDER = STRATUM_ORDER + ["Unlisted", "Unassigned"]

TABLE1_COLUMNS = [
    "row_type",
    "stratum",
    "organization",
    "proposals",
    "proposals_50_or_more",
    "pct_50_or_more",
    "first_year",
    "last_year",
]


def require_file(path):
    """Stop with a clear message if an input file is missing."""
    if not path.exists():
        print(f"Missing file: {path}")
        print("This script only reads local files. It does not download anything.")
        sys.exit(1)


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def is_verified(value):
    """The spreadsheet stores verified as the words True and False."""
    return str(value).strip() == "True"


def proposal_count(row):
    return int(float(row["proposalsCount"] or 0))


def had_proposal_after_cutoff(date_row):
    """True only for a successful lookup with a date after the cutoff."""
    if date_row is None:
        return False
    if date_row.get("status") != "ok":
        return False
    raw = (date_row.get("last_proposal_date") or "").strip()
    if not raw:
        return False
    return date.fromisoformat(raw) > CUTOFF


def percent(part, whole):
    if whole == 0:
        return "0.0"
    return f"{(100 * part / whole):.1f}"


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_dates(path):
    by_id = {}
    for row in read_csv(path):
        by_id[row["space_id"]] = row
    return by_id


def print_space_counts(spaces, dates_by_id):
    verified = [row for row in spaces if is_verified(row["verified"])]
    with_20 = [row for row in verified if proposal_count(row) >= 20]
    still_active = [
        row
        for row in with_20
        if had_proposal_after_cutoff(dates_by_id.get(row["id"]))
    ]

    print("Space list")
    print(f"  Total spaces: {len(spaces)}")
    print(f"  Verified: {len(verified)}")
    print(f"  Verified with 20 or more proposals: {len(with_20)}")
    print(
        f"  Of those, a proposal after {CUTOFF.isoformat()} (UTC): {len(still_active)}"
    )
    print()
    return with_20


def print_activity_table(with_20, dates_by_id):
    grouped = defaultdict(list)
    for row in with_20:
        grouped[row["stratum"]].append(row)

    known = set(ACTIVITY_ORDER)
    extra = sorted(set(grouped) - known)

    print("Verified spaces with 20 or more proposals, by stratum")
    print(
        f"  {'stratum':<32} {'count':>6} {'after cutoff':>13} {'percent':>8}"
    )
    for key in ACTIVITY_ORDER + extra:
        group = grouped.get(key, [])
        if not group and key in extra:
            continue
        if not group:
            continue
        active = sum(
            1
            for row in group
            if had_proposal_after_cutoff(dates_by_id.get(row["id"]))
        )
        label = ACTIVITY_LABELS.get(key, key)
        print(
            f"  {label:<32} {len(group):>6} {active:>13} {percent(active, len(group)):>7}%"
        )
    print()


def organization_stats(rows):
    """Summarize one organization's proposals."""
    words_50 = sum(1 for row in rows if int(row["word_count"] or 0) >= 50)
    years = [int(row["date"][:4]) for row in rows if row.get("date")]
    return {
        "proposals": len(rows),
        "proposals_50_or_more": words_50,
        "pct_50_or_more": percent(words_50, len(rows)),
        "first_year": min(years) if years else "",
        "last_year": max(years) if years else "",
    }


def table_row(row_type, stratum, organization, stats):
    return {
        "row_type": row_type,
        "stratum": stratum,
        "organization": organization,
        "proposals": stats["proposals"],
        "proposals_50_or_more": stats["proposals_50_or_more"],
        "pct_50_or_more": stats["pct_50_or_more"],
        "first_year": stats["first_year"],
        "last_year": stats["last_year"],
    }


def build_table1(manifest_rows):
    by_stratum = defaultdict(lambda: defaultdict(list))
    for row in manifest_rows:
        by_stratum[row["stratum"]][row["organization"]].append(row)

    known = set(STRATUM_ORDER)
    extra = sorted(set(by_stratum) - known)
    order = [name for name in STRATUM_ORDER if name in by_stratum] + extra

    table_rows = []
    all_rows = []

    for stratum in order:
        orgs = by_stratum[stratum]
        org_items = []
        stratum_rows = []
        for organization, rows in orgs.items():
            org_items.append((organization, rows))
            stratum_rows.extend(rows)
        org_items.sort(key=lambda item: (-len(item[1]), item[0]))

        for organization, rows in org_items:
            table_rows.append(
                table_row(
                    "organization",
                    stratum,
                    organization,
                    organization_stats(rows),
                )
            )
        table_rows.append(
            table_row("subtotal", stratum, "", organization_stats(stratum_rows))
        )
        all_rows.extend(stratum_rows)

    table_rows.append(table_row("total", "", "", organization_stats(all_rows)))
    return table_rows


def print_table1(table_rows):
    print("Table 1")
    print(
        f"  {'stratum':<32} {'organization':<28} {'proposals':>10} "
        f"{'50+ words':>10} {'percent':>8} {'first':>6} {'last':>6}"
    )
    for row in table_rows:
        if row["row_type"] == "subtotal":
            name = "Subtotal"
        elif row["row_type"] == "total":
            name = "Total"
        else:
            name = row["organization"]
        stratum = row["stratum"] if row["row_type"] == "organization" else ""
        if row["row_type"] == "subtotal":
            stratum = row["stratum"]
        print(
            f"  {stratum:<32} {name:<28} {row['proposals']:>10} "
            f"{row['proposals_50_or_more']:>10} {row['pct_50_or_more']:>7}% "
            f"{str(row['first_year']):>6} {str(row['last_year']):>6}"
        )
    print()


def main():
    for path in (SPACES_PATH, DATES_PATH, MANIFEST_PATH):
        require_file(path)

    spaces = read_csv(SPACES_PATH)
    dates_by_id = load_dates(DATES_PATH)
    manifest_rows = read_csv(MANIFEST_PATH)

    with_20 = print_space_counts(spaces, dates_by_id)
    print_activity_table(with_20, dates_by_id)

    table_rows = build_table1(manifest_rows)
    print_table1(table_rows)
    write_csv(TABLE1_PATH, table_rows, TABLE1_COLUMNS)
    print(f"Wrote {TABLE1_PATH.relative_to(FOLDER)}")


if __name__ == "__main__":
    main()
