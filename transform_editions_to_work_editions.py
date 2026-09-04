#!/usr/bin/env python3
"""
Transform Open Library editions CSV to work_editions schema for PostgreSQL COPY.

Reads from editions_csv/ (output of openlibrary_editions_to_csv.py) and writes
DB-ready CSV files into work_editions_csv/. The legacy PostgreSQL-load workflow
can resolve work_id eagerly; the canonical DuckDB workflow deliberately defers
that join and uses edition_works.csv instead.

PREREQUISITE: quillent_work_csv/ must exist (output of transform_works_to_quillent_work.py).
This script reads the quillent_work CSV files to build an in-memory mapping of
ol_id → id, eliminating the need for post-load UPDATE JOIN.

Usage:
    python3 transform_editions_to_work_editions.py           # all files
    python3 transform_editions_to_work_editions.py --test    # first file only
    python3 transform_editions_to_work_editions.py --defer-work-ids

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

from collection_fields import parse_json_list, string_values

INPUT_DIR = "editions_csv"
WORKS_DIR = "quillent_work_csv"
OUTPUT_DIR = "work_editions_csv"
WORK_RELATIONSHIPS_FILE = "edition_works.csv"
AUTHOR_RELATIONSHIPS_FILE = "edition_authors.csv"
IDENTIFIERS_FILE = "edition_identifiers.csv"
PUBLISHERS_FILE = "edition_publishers.csv"
COVERS_FILE = "edition_covers.csv"
LANGUAGES_FILE = "edition_languages.csv"

# Maximum field lengths
MAX_PUBLISHER_LENGTH = 1000
MAX_DATE_LENGTH = 1000

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

    csv_files = sorted(
        f for f in os.listdir(works_dir)
        if f.startswith("quillent_work_") and f.endswith(".csv")
    )
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


def first_string(json_array: str) -> str:
    """Return the first non-empty string in a JSON-array CSV field."""
    values = string_values(json_array)
    return values[0] if values else ""


def transform_row(row: dict, work_mapping: dict | None = None) -> dict:
    """
    Transform a single edition row from generic CSV to DB schema.

    Args:
        row: Dictionary from csv.DictReader
        work_mapping: Optional {work_ol_id: work_id}. When omitted, work_id is
            left as 0 and edition_works.csv is authoritative.

    Returns:
        Dictionary ready for csv.DictWriter with work_id resolved
    """
    key = row.get("key", "").strip('"')

    # The canonical table currently has one parent work. Keep the first source
    # relationship here while preserving every relationship in edition_works.csv.
    first_work_key = first_string(row.get("works", "[]"))
    work_ol_id = ol_key_to_id(first_work_key) if first_work_key else ""

    # Resolve work_id from mapping (0 if not found)
    work_id = work_mapping.get(work_ol_id, 0) if work_mapping is not None else 0

    pub_date = row.get("publish_date", "")

    publisher = first_string(row.get("publishers", "[]"))

    isbn_ten = first_string(row.get("isbn_10", "[]"))
    isbn_thirteen = first_string(row.get("isbn_13", "[]"))

    lccn = first_string(row.get("lccn", "[]"))
    oclc = first_string(row.get("oclc_numbers", "[]"))

    # Truncate long fields
    if pub_date and len(pub_date) > MAX_DATE_LENGTH:
        pub_date = pub_date[:MAX_DATE_LENGTH]

    if publisher and len(publisher) > MAX_PUBLISHER_LENGTH:
        publisher = publisher[:MAX_PUBLISHER_LENGTH]

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
    }


def transform_files(
        input_dir: str,
        output_dir: str,
        work_mapping: dict | None = None,
        test_mode: bool = False):
    """
    Transform all CSV files from input_dir to output_dir.

    Args:
        input_dir: Directory containing editions_*.csv files
        output_dir: Directory to write work_editions_*.csv files
        work_mapping: Optional {work_ol_id: work_id}; omit for canonical builds
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
    relationship_paths = {
        "works": os.path.join(output_dir, WORK_RELATIONSHIPS_FILE),
        "authors": os.path.join(output_dir, AUTHOR_RELATIONSHIPS_FILE),
        "identifiers": os.path.join(output_dir, IDENTIFIERS_FILE),
        "publishers": os.path.join(output_dir, PUBLISHERS_FILE),
        "covers": os.path.join(output_dir, COVERS_FILE),
        "languages": os.path.join(output_dir, LANGUAGES_FILE),
    }
    relationship_files = {
        name: open(path, "w", encoding="utf-8", newline="")
        for name, path in relationship_paths.items()
    }
    relationship_writers = {
        name: csv.writer(handle, quoting=csv.QUOTE_MINIMAL)
        for name, handle in relationship_files.items()
    }
    relationship_writers["works"].writerow(
        ["edition_external_id", "work_external_id", "position"]
    )
    relationship_writers["authors"].writerow(
        ["edition_external_id", "author_external_id", "position"]
    )
    relationship_writers["identifiers"].writerow(
        ["edition_external_id", "identifier_type", "identifier", "position"]
    )
    relationship_writers["publishers"].writerow(
        ["edition_external_id", "publisher", "position"]
    )
    relationship_writers["covers"].writerow(
        ["edition_external_id", "cover_id", "position"]
    )
    relationship_writers["languages"].writerow(
        ["edition_external_id", "language_code", "position"]
    )

    try:
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
                    if work_mapping is not None and transformed["work_id"] == 0:
                        file_unresolved += 1
                    writer.writerow(transformed)
                    written += 1

                    edition_key = transformed["uuid"]
                    for position, work_key in enumerate(
                            string_values(row.get("works", "[]")), start=1):
                        relationship_writers["works"].writerow(
                            [edition_key, work_key, position]
                        )
                    for position, author_key in enumerate(
                            string_values(row.get("authors", "[]")), start=1):
                        relationship_writers["authors"].writerow(
                            [edition_key, author_key, position]
                        )
                    for identifier_type, field in (
                            ("isbn10", "isbn_10"), ("isbn13", "isbn_13"),
                            ("lccn", "lccn"), ("oclc", "oclc_numbers")):
                        for position, identifier in enumerate(
                                string_values(row.get(field, "[]")), start=1):
                            relationship_writers["identifiers"].writerow(
                                [edition_key, identifier_type, identifier, position]
                            )
                    for position, publisher_value in enumerate(
                            string_values(row.get("publishers", "[]")), start=1):
                        relationship_writers["publishers"].writerow(
                            [edition_key, publisher_value, position]
                        )
                    for position, cover_id in enumerate(
                            parse_json_list(row.get("covers", "[]")), start=1):
                        if isinstance(cover_id, int) and cover_id > 0:
                            relationship_writers["covers"].writerow(
                                [edition_key, cover_id, position]
                            )
                    for position, language_code in enumerate(
                            string_values(row.get("languages", "[]")), start=1):
                        relationship_writers["languages"].writerow(
                            [edition_key, language_code, position]
                        )

            total_written += written
            unresolved_count += file_unresolved
            print(f"  {fname} -> {out_name}  ({written:,} rows, {file_unresolved:,} unresolved)")
    finally:
        for handle in relationship_files.values():
            handle.close()

    col_list = ",".join(FIELDNAMES)
    print(f"\nDone. {total_written:,} rows written to {output_dir}/")
    if work_mapping is None:
        print("  work_id resolution deferred to the canonical relationship join")
    else:
        print(f"  {unresolved_count:,} editions have work_id=0 (work not found in database)")
    for path in relationship_paths.values():
        print(f"  Relationship data written to: {path}")
    if work_mapping is not None and unresolved_count > 0:
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
    if work_mapping is None:
        print("Canonical builds resolve work ownership from edition_works.csv.")
    else:
        print(f"NO UPDATE JOIN NEEDED — work_id is already resolved!")


def main():
    test_mode = "--test" in sys.argv
    defer_work_ids = "--defer-work-ids" in sys.argv
    print("=" * 80)
    print("Transform editions CSV -> work_editions CSV (with work_id pre-resolved)")
    print("=" * 80)

    # The canonical path avoids loading tens of millions of work IDs into a
    # Python dictionary. DuckDB resolves edition_works.csv on disk instead.
    work_mapping = None
    if not defer_work_ids:
        work_mapping = load_work_id_mapping(WORKS_DIR)
        print()

    # Transform files
    transform_files(INPUT_DIR, OUTPUT_DIR, work_mapping, test_mode)


if __name__ == "__main__":
    main()
