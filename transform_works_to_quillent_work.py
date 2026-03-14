#!/usr/bin/env python3
"""
Transform Open Library works CSV to quillent_work schema for PostgreSQL COPY.

Reads from works_csv/ (output of openlibrary_works_to_csv.py) and writes
DB-ready CSV files into quillent_work_csv/ matching:

    quillent_work (
        -- id BIGINT (PK, auto) -- excluded; DB generates this
        uuid                  VARCHAR   -- OL work key e.g. /works/OL1W
        title                 VARCHAR
        sub_title             VARCHAR
        description           TEXT      -- (CLOB/LOB in schema)
        first_publication_date VARCHAR
        publication_date_epoch BIGINT   -- epoch day, best-effort parse
        isbn_ten              VARCHAR   -- empty (lives in editions)
        isbn_thirteen         VARCHAR   -- empty (lives in editions)
        language_code         VARCHAR   -- empty (lives in editions)
        num_of_pages          INTEGER   -- empty (lives in editions)
        ol_id                 VARCHAR   -- bare OL ID e.g. OL1W
        cover_id              BIGINT    -- first cover ID from covers list
        featured_edition      VARCHAR   -- empty (denormalized, set later)
        featured_edition_id   VARCHAR   -- empty (legacy, set later)
        featured_edition_fk   BIGINT    -- empty (FK set later)
        series                VARCHAR   -- empty (not in OL works)
        position_in_series    VARCHAR   -- empty
        reading_id            VARCHAR   -- empty
        prh_id                VARCHAR   -- empty
        goodreads_resolved    BOOLEAN   -- false
        google_resolved       BOOLEAN   -- false
        featured_covers       TEXT      -- JSON array of cover IDs
    )

Usage:
    python3 transform_works_to_quillent_work.py           # transform all files
    python3 transform_works_to_quillent_work.py --test    # first file only
"""

import csv
import json
import os
import re
import sys
from datetime import date, datetime
from typing import Optional


csv.field_size_limit(10_000_000)

INPUT_DIR = "works_csv"
OUTPUT_DIR = "quillent_work_csv"
MAX_DESCRIPTION = 5000  # choose your limit

# Include id in output (pre-assigned, starts at 1)
FIELDNAMES = [
    "id",
    "uuid",
    "title",
    "sub_title",
    "description",
    "first_publication_date",
    "publication_date_epoch",
    "isbn_ten",
    "isbn_thirteen",
    "language_code",
    "num_of_pages",
    "ol_id",
    "cover_id",
    "featured_edition",
    "featured_edition_id",
    "featured_edition_fk",
    "series",
    "position_in_series",
    "reading_id",
    "prh_id",
    "goodreads_resolved",
    "google_resolved",
    "featured_covers",
]

# Epoch day reference: days since 1970-01-01
EPOCH = date(1970, 1, 1)

# Patterns tried in order when parsing first_publication_date
_DATE_PATTERNS = [
    ("%Y-%m-%d", re.compile(r"^\d{4}-\d{2}-\d{2}$")),
    ("%B %d, %Y", re.compile(r"^[A-Za-z]+ \d{1,2}, \d{4}$")),
    ("%b %d, %Y", re.compile(r"^[A-Za-z]{3}\.? \d{1,2}, \d{4}$")),
    ("%B %Y", re.compile(r"^[A-Za-z]+ \d{4}$")),
    ("%Y", re.compile(r"^\d{4}$")),
]


def parse_epoch_day(date_str: str) -> Optional[int]:
    """
    Convert a human-readable date string to epoch day (days since 1970-01-01).
    Returns None if the string can't be parsed.
    """
    if not date_str:
        return None
    s = date_str.strip()
    for fmt, pattern in _DATE_PATTERNS:
        if pattern.match(s):
            try:
                d = datetime.strptime(s, fmt).date()
                return (d - EPOCH).days
            except ValueError:
                pass
    # Last-ditch: try to extract a bare 4-digit year anywhere in the string
    m = re.search(r"\b(1[0-9]{3}|20[0-2][0-9])\b", s)
    if m:
        try:
            d = date(int(m.group(1)), 1, 1)
            return (d - EPOCH).days
        except ValueError:
            pass
    return None


def ol_key_to_id(key: str) -> str:
    """'/works/OL1W' -> 'OL1W'"""
    return key.rstrip("/").rsplit("/", 1)[-1]


def first_cover_id(covers_str: str) -> str:
    """Return the first numeric cover ID from a comma-separated list, or ''."""
    if not covers_str:
        return ""
    for part in covers_str.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit() and not part.startswith("-"):
            return part
    return ""


def covers_as_json(covers_str: str) -> str:
    """Convert comma-separated cover IDs to a JSON array string, skipping -1."""
    if not covers_str:
        return ""
    ids = []
    for part in covers_str.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit() and not part.startswith("-"):
            try:
                ids.append(int(part))
            except ValueError:
                pass
    return json.dumps(ids) if ids else ""


def transform_row(row: dict, work_id: int) -> dict:
    """
    Transform a single work row from generic CSV to DB schema.

    Args:
        row: Dictionary from csv.DictReader
        work_id: Pre-assigned integer ID for this work

    Returns:
        Dictionary ready for csv.DictWriter with id included
    """
    key = row.get("key", "").strip('"')
    date_str = row.get("first_publish_date", "")
    covers_str = row.get("covers", "")

    # For integer columns, use None instead of "" for proper NULL in CSV
    epoch_day = parse_epoch_day(date_str)
    cover_id_str = first_cover_id(covers_str)
    desc = row.get("description", "")
    if desc and len(desc) > MAX_DESCRIPTION:
        desc = desc[:MAX_DESCRIPTION]

    return {
        "id":                     work_id,
        "uuid":                   key,
        "title":                  row.get("title", ""),
        "sub_title":              row.get("subtitle", ""),
        "description":            desc,
        "first_publication_date": date_str,
        "publication_date_epoch": epoch_day if epoch_day is not None else None,
        "isbn_ten":               "",
        "isbn_thirteen":          "",
        "language_code":          "",
        "num_of_pages":           None,  # INTEGER column
        "ol_id":                  ol_key_to_id(key) if key else "",
        "cover_id":               int(cover_id_str) if cover_id_str else None,
        "featured_edition":       "",
        "featured_edition_id":    "",
        "featured_edition_fk":    None,  # INTEGER column
        "series":                 "",
        "position_in_series":     None,  # INTEGER column
        "reading_id":             None,  # INTEGER column
        "prh_id":                 "",
        "goodreads_resolved":     "false",
        "google_resolved":        "false",
        "featured_covers":        covers_as_json(covers_str),
    }


def transform_files(input_dir: str, output_dir: str, test_mode: bool = False):
    if not os.path.isdir(input_dir):
        print(f"ERROR: input directory '{input_dir}' does not exist.")
        print(f"Run openlibrary_works_to_csv.py first to generate it.")
        sys.exit(1)

    csv_files = sorted(f for f in os.listdir(input_dir) if f.endswith(".csv"))
    if not csv_files:
        print(f"No CSV files found in {input_dir}/")
        sys.exit(1)

    if test_mode:
        csv_files = csv_files[:1]
        print(f"TEST MODE: processing only {csv_files[0]}")

    os.makedirs(output_dir, exist_ok=True)

    total_written = 0
    current_id = 1  # Pre-assign IDs starting from 1
    for fname in csv_files:
        in_path = os.path.join(input_dir, fname)
        out_name = fname.replace("works_", "quillent_work_")
        out_path = os.path.join(output_dir, out_name)

        written = 0
        with open(in_path, "r", encoding="utf-8", newline="") as f_in, \
             open(out_path, "w", encoding="utf-8", newline="") as f_out:

            reader = csv.DictReader(f_in)
            writer = csv.DictWriter(
                f_out,
                fieldnames=FIELDNAMES,
                quoting=csv.QUOTE_MINIMAL,
                extrasaction="ignore",
            )
            writer.writeheader()
            for row in reader:
                writer.writerow(transform_row(row, current_id))
                current_id += 1
                written += 1

        total_written += written
        print(f"  {fname} -> {out_name}  ({written:,} rows, IDs {current_id - written} to {current_id - 1})")

    col_list = ",".join(FIELDNAMES)
    print(f"\nDone. {total_written:,} rows written to {output_dir}/")
    print(f"  IDs assigned: 1 to {current_id - 1}")
    print(f"\nTo load into PostgreSQL (id is pre-assigned in CSV):")
    print(f"  \\copy quillent_work ({col_list})")
    print(f"    FROM '<absolute_path>/{output_dir}/quillent_work_0001.csv'")
    print(f"    CSV HEADER;")
    print()
    print(f"After loading, reset the sequence:")
    print(f"  SELECT setval('quillent_work_id_seq', (SELECT MAX(id) FROM quillent_work));")
    print()
    print(f"Or for all files at once (bash):")
    print(f"  for f in {output_dir}/quillent_work_*.csv; do")
    print(f"    psql -d <db> -c \"\\copy quillent_work ({col_list}) FROM '\\$f' CSV HEADER;\"")
    print(f"  done")


def main():
    test_mode = "--test" in sys.argv
    print("=" * 60)
    print("Transform works CSV -> quillent_work CSV")
    print("=" * 60)
    transform_files(INPUT_DIR, OUTPUT_DIR, test_mode)


if __name__ == "__main__":
    main()
