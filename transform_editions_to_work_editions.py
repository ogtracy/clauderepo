#!/usr/bin/env python3
"""
Transform Open Library editions CSV to work_editions schema for PostgreSQL COPY.

Reads from editions_csv/ (output of openlibrary_editions_to_csv.py) and writes
DB-ready CSV files into work_editions_csv/ matching:

    work_editions (
        -- id BIGINT (PK, auto)   -- excluded; DB generates this
        uuid             VARCHAR   -- OL edition key e.g. /books/OL1M
        work_id          BIGINT    -- FK → quillent_work.id; set to 0 sentinel,
                                   -- must be resolved post-load (see below)
        isbn_ten         VARCHAR
        isbn_thirteen    VARCHAR
        publication_date VARCHAR
        publication_year VARCHAR
        ol_id            VARCHAR   -- bare OL ID e.g. OL1M
        work_ol_id       VARCHAR   -- bare OL work ID e.g. OL1W (denormalized)
        number_of_pages  VARCHAR
        lccn             VARCHAR
        oclc_number      VARCHAR
        publisher        VARCHAR   -- first publisher only
        series           VARCHAR   -- not in OL editions data
        goodreads_id     VARCHAR   -- not in OL editions data
        google_id        VARCHAR   -- not in OL editions data
        asin             VARCHAR   -- not in OL editions data
        is_featured      BOOLEAN   -- false (set per-work after load)
    )

Post-load SQL to resolve work_id FK:
    UPDATE work_editions we
    SET    work_id = qw.id
    FROM   quillent_work qw
    WHERE  qw.ol_id = we.work_ol_id;

    -- Optionally verify no unresolved rows remain:
    SELECT COUNT(*) FROM work_editions WHERE work_id = 0;

Usage:
    python3 transform_editions_to_work_editions.py           # all files
    python3 transform_editions_to_work_editions.py --test    # first file only
"""

import csv
import os
import re
import sys

INPUT_DIR = "editions_csv"
OUTPUT_DIR = "work_editions_csv"

# Excluded from output: id (auto PK)
FIELDNAMES = [
    "uuid",
    "work_id",
    "isbn_ten",
    "isbn_thirteen",
    "publication_date",
    "publication_year",
    "ol_id",
    "work_ol_id",
    "number_of_pages",
    "lccn",
    "oclc_number",
    "publisher",
    "series",
    "goodreads_id",
    "google_id",
    "asin",
    "is_featured",
]

_YEAR_RE = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9])\b")


def extract_year(date_str: str) -> str:
    """Pull first 4-digit year out of any date string, or return ''."""
    if not date_str:
        return ""
    m = _YEAR_RE.search(date_str)
    return m.group(1) if m else ""


def ol_key_to_id(key: str) -> str:
    """'/books/OL1M' -> 'OL1M'"""
    return key.rstrip("/").rsplit("/", 1)[-1]


def first_value(comma_or_semi_str: str, sep: str = ",") -> str:
    """Return the first non-empty token from a delimited string."""
    if not comma_or_semi_str:
        return ""
    return comma_or_semi_str.split(sep)[0].strip()


def transform_row(row: dict) -> dict:
    key = row.get("key", "").strip('"')

    # works field is comma-separated work keys; take the first
    works_str = row.get("works", "")
    first_work_key = first_value(works_str, ",")
    work_ol_id = ol_key_to_id(first_work_key) if first_work_key else ""

    pub_date = row.get("publish_date", "")

    # publishers are semicolon-separated; take the first
    publisher = first_value(row.get("publishers", ""), ";")

    # isbn lists are comma-separated; take the first value
    isbn_ten = first_value(row.get("isbn_10", ""), ",")
    isbn_thirteen = first_value(row.get("isbn_13", ""), ",")

    # lccn and oclc are comma-separated; take the first
    lccn = first_value(row.get("lccn", ""), ",")
    oclc = first_value(row.get("oclc_numbers", ""), ",")

    # For integer columns, use None instead of "" for proper NULL in CSV
    year_str = extract_year(pub_date)
    pages_str = row.get("number_of_pages", "")

    return {
        "uuid":             key,
        "work_id":          0,          # sentinel — resolve via post-load UPDATE
        "isbn_ten":         isbn_ten,
        "isbn_thirteen":    isbn_thirteen,
        "publication_date": pub_date,
        "publication_year": int(year_str) if year_str else None,
        "ol_id":            ol_key_to_id(key) if key else "",
        "work_ol_id":       work_ol_id,
        "number_of_pages":  int(pages_str) if pages_str else None,
        "lccn":             lccn,
        "oclc_number":      oclc,
        "publisher":        publisher,
        "series":           "",
        "goodreads_id":     "",
        "google_id":        "",
        "asin":             "",
        "is_featured":      "false",
    }


def transform_files(input_dir: str, output_dir: str, test_mode: bool = False):
    if not os.path.isdir(input_dir):
        print(f"ERROR: input directory '{input_dir}' does not exist.")
        print(f"Run openlibrary_editions_to_csv.py first to generate it.")
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
    for fname in csv_files:
        in_path = os.path.join(input_dir, fname)
        out_name = fname.replace("editions_", "work_editions_")
        out_path = os.path.join(output_dir, out_name)

        written = 0
        with open(in_path, "r", encoding="utf-8", newline="") as f_in, \
             open(out_path, "w", encoding="utf-8", newline="") as f_out:

            reader = csv.DictReader(f_in)
            writer = csv.DictWriter(
                f_out,
                fieldnames=FIELDNAMES,
                quoting=csv.QUOTE_NONNUMERIC,
                extrasaction="ignore",
            )
            writer.writeheader()
            for row in reader:
                writer.writerow(transform_row(row))
                written += 1

        total_written += written
        print(f"  {fname} -> {out_name}  ({written:,} rows)")

    col_list = ",".join(FIELDNAMES)
    print(f"\nDone. {total_written:,} rows written to {output_dir}/")
    print(f"\nStep 1 — load CSV (id is auto-generated, work_id starts as 0 sentinel):")
    print(f"  \\copy work_editions ({col_list})")
    print(f"    FROM '<absolute_path>/{output_dir}/work_editions_0001.csv'")
    print(f"    CSV HEADER;")
    print()
    print(f"Or for all files (bash):")
    print(f"  for f in {output_dir}/work_editions_*.csv; do")
    print(f"    psql -d <db> -c \"\\copy work_editions ({col_list}) FROM '\\$f' CSV HEADER;\"")
    print(f"  done")
    print()
    print(f"Step 2 — resolve work_id FK after both tables are loaded:")
    print(f"  UPDATE work_editions we")
    print(f"  SET    work_id = qw.id")
    print(f"  FROM   quillent_work qw")
    print(f"  WHERE  qw.ol_id = we.work_ol_id;")
    print()
    print(f"Step 3 — verify no unresolved rows:")
    print(f"  SELECT COUNT(*) FROM work_editions WHERE work_id = 0;")


def main():
    test_mode = "--test" in sys.argv
    print("=" * 60)
    print("Transform editions CSV -> work_editions CSV")
    print("=" * 60)
    transform_files(INPUT_DIR, OUTPUT_DIR, test_mode)


if __name__ == "__main__":
    main()
