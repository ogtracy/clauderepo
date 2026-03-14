#!/usr/bin/env python3
"""
Transform Open Library editions CSV to work_editions schema for PostgreSQL COPY.

Reads from editions_csv/ (output of openlibrary_editions_to_csv.py) and writes
DB-ready CSV files into work_editions_csv/ with work_id already resolved.

PREREQUISITE: quillent_work_csv/ must exist (output of transform_works_to_quillent_work.py).
This script reads the quillent_work CSV files to build an in-memory mapping of
ol_id → id, eliminating the need for post-load UPDATE JOIN.

Usage:
    python3 transform_editions_to_work_editions.py           # all files
    python3 transform_editions_to_work_editions.py --test    # first file only

The script will:
1. Read all quillent_work CSV files from quillent_work_csv/
2. Build a mapping dictionary: {ol_id: id}
3. Transform editions, setting work_id using the mapping
4. Write work_id=0 for editions whose work is not in the mapping
"""

import csv
import os
import re
import sys

INPUT_DIR = "editions_csv"
WORKS_DIR = "quillent_work_csv"
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


def load_work_id_mapping(works_dir: str) -> dict:
    """
    Read all quillent_work CSV files and return {ol_id: id} mapping.

    Args:
        works_dir: Directory containing quillent_work_*.csv files

    Returns:
        Dictionary mapping work ol_id (e.g. "OL1W") to database id (int)
    """
    if not os.path.isdir(works_dir):
        print(f"ERROR: works directory '{works_dir}' does not exist.", file=sys.stderr)
        print(f"Run transform_works_to_quillent_work.py first to generate it.", file=sys.stderr)
        sys.exit(1)

    csv_files = sorted(f for f in os.listdir(works_dir) if f.endswith(".csv"))
    if not csv_files:
        print(f"ERROR: No CSV files found in {works_dir}/", file=sys.stderr)
        sys.exit(1)

    print(f"Reading quillent_work CSVs from {works_dir}/...")
    mapping = {}
    total_rows = 0

    for fname in csv_files:
        path = os.path.join(works_dir, fname)
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                work_id = row.get("id")
                ol_id = row.get("ol_id")
                if work_id and ol_id:
                    mapping[ol_id] = int(work_id)
                    total_rows += 1

    print(f"  Loaded {len(mapping):,} work ID mappings from {len(csv_files)} CSV files")
    return mapping


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


def transform_row(row: dict, work_mapping: dict) -> dict:
    """
    Transform a single edition row from generic CSV to DB schema.

    Args:
        row: Dictionary from csv.DictReader
        work_mapping: Dictionary {work_ol_id: work_id} from database

    Returns:
        Dictionary ready for csv.DictWriter with work_id resolved
    """
    key = row.get("key", "").strip('"')

    # works field is comma-separated work keys; take the first
    works_str = row.get("works", "")
    first_work_key = first_value(works_str, ",")
    work_ol_id = ol_key_to_id(first_work_key) if first_work_key else ""

    # Resolve work_id from mapping (0 if not found)
    work_id = work_mapping.get(work_ol_id, 0)

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
        "work_id":          work_id,    # resolved from database mapping
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


def transform_files(input_dir: str, output_dir: str, work_mapping: dict, test_mode: bool = False):
    """
    Transform all CSV files from input_dir to output_dir.

    Args:
        input_dir: Directory containing editions_*.csv files
        output_dir: Directory to write work_editions_*.csv files
        work_mapping: Dictionary {work_ol_id: work_id} from database
        test_mode: If True, only process first file
    """
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
    unresolved_count = 0
    for fname in csv_files:
        in_path = os.path.join(input_dir, fname)
        out_name = fname.replace("editions_", "work_editions_")
        out_path = os.path.join(output_dir, out_name)

        written = 0
        file_unresolved = 0
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
                transformed = transform_row(row, work_mapping)
                if transformed["work_id"] == 0:
                    file_unresolved += 1
                writer.writerow(transformed)
                written += 1

        total_written += written
        unresolved_count += file_unresolved
        print(f"  {fname} -> {out_name}  ({written:,} rows, {file_unresolved:,} unresolved)")

    col_list = ",".join(FIELDNAMES)
    print(f"\nDone. {total_written:,} rows written to {output_dir}/")
    print(f"  {unresolved_count:,} editions have work_id=0 (work not found in database)")
    if unresolved_count > 0:
        print(f"\n  NOTE: Editions with work_id=0 reference works that don't exist in quillent_work.")
        print(f"        You can either:")
        print(f"        1. Delete them: DELETE FROM work_editions WHERE work_id = 0;")
        print(f"        2. Keep them as orphans (FK constraint will reject them)")
    print(f"\nTo load into PostgreSQL:")
    print(f"  \\copy work_editions ({col_list})")
    print(f"    FROM '<absolute_path>/{output_dir}/work_editions_0001.csv'")
    print(f"    CSV HEADER;")
    print()
    print(f"Or for all files (bash):")
    print(f"  for f in {output_dir}/work_editions_*.csv; do")
    print(f"    psql -d <db> -c \"\\copy work_editions ({col_list}) FROM '\\$f' CSV HEADER;\"")
    print(f"  done")
    print()
    print(f"NO UPDATE JOIN NEEDED — work_id is already resolved!")


def main():
    test_mode = "--test" in sys.argv
    print("=" * 80)
    print("Transform editions CSV -> work_editions CSV (with work_id pre-resolved)")
    print("=" * 80)

    # Load work ID mapping from quillent_work CSVs
    work_mapping = load_work_id_mapping(WORKS_DIR)
    print()

    # Transform files
    transform_files(INPUT_DIR, OUTPUT_DIR, work_mapping, test_mode)


if __name__ == "__main__":
    main()
