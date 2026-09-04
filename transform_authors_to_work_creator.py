#!/usr/bin/env python3
"""
Transform Open Library authors CSV to work_creator schema for PostgreSQL COPY.

Reads from authors_csv/ (output of openlibrary_authors_to_csv.py) and writes
DB-ready CSV files into work_creator_csv/ with the following schema:

    work_creator (
        uuid         VARCHAR (PK)  -- OL author key e.g. /authors/OL1A
        creator_name VARCHAR       -- display name
        personal_name VARCHAR      -- legal/full name
        birth_date   VARCHAR
        death_date   VARCHAR
        ol_id        VARCHAR       -- bare OL ID e.g. OL1A
    )

Usage:
    python3 transform_authors_to_work_creator.py               # transform all files
    python3 transform_authors_to_work_creator.py --test        # only first file
"""

import csv
import os
import sys

from collection_fields import string_values

INPUT_DIR = "authors_csv"
OUTPUT_DIR = "work_creator_csv"
ALTERNATE_NAMES_FILE = "author_alternate_names.csv"
EXTERNAL_LINKS_FILE = "author_external_links.csv"

# Exact column order for PostgreSQL COPY
FIELDNAMES = ["uuid", "creator_name", "personal_name", "birth_date", "death_date", "ol_id"]

# Maximum field lengths
MAX_NAME_LENGTH = 1000


def ol_key_to_id(key: str) -> str:
    """Extract bare OL ID from a full key.  '/authors/OL1A' -> 'OL1A'"""
    return key.rstrip('/').rsplit('/', 1)[-1]


def transform_row(row: dict) -> dict:
    key = row.get("key", "").strip('"')

    # Truncate long names
    creator_name = row.get("name", "")
    if creator_name and len(creator_name) > MAX_NAME_LENGTH:
        creator_name = creator_name[:MAX_NAME_LENGTH]

    personal_name = row.get("personal_name", "")
    if personal_name and len(personal_name) > MAX_NAME_LENGTH:
        personal_name = personal_name[:MAX_NAME_LENGTH]

    return {
        "uuid":          key,
        "creator_name":  creator_name,
        "personal_name": personal_name,
        "birth_date":    row.get("birth_date", ""),
        "death_date":    row.get("death_date", ""),
        "ol_id":         ol_key_to_id(key) if key else "",
    }


def transform_files(input_dir: str, output_dir: str, test_mode: bool = False):
    if not os.path.isdir(input_dir):
        print(f"ERROR: input directory '{input_dir}' does not exist.")
        print(f"Run openlibrary_authors_to_csv.py first to generate it.")
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
    alternate_names_path = os.path.join(output_dir, ALTERNATE_NAMES_FILE)
    external_links_path = os.path.join(output_dir, EXTERNAL_LINKS_FILE)
    with open(alternate_names_path, "w", encoding="utf-8", newline="") as alternate_file, \
         open(external_links_path, "w", encoding="utf-8", newline="") as links_file:
      alternate_writer = csv.writer(alternate_file, quoting=csv.QUOTE_MINIMAL)
      links_writer = csv.writer(links_file, quoting=csv.QUOTE_MINIMAL)
      alternate_writer.writerow(["author_external_id", "alternate_name", "position"])
      links_writer.writerow(["author_external_id", "link_type", "url"])

      for fname in csv_files:
        in_path = os.path.join(input_dir, fname)
        # Rename: authors_0001.csv -> work_creator_0001.csv
        out_name = fname.replace("authors_", "work_creator_")
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
                transformed = transform_row(row)
                writer.writerow(transformed)
                written += 1

                author_key = transformed["uuid"]
                for position, alternate_name in enumerate(
                        string_values(row.get("alternate_names", "[]")), start=1):
                    alternate_writer.writerow([author_key, alternate_name, position])
                for link_type in ("wikipedia", "website"):
                    url = row.get(link_type, "").strip()
                    if url:
                        links_writer.writerow([author_key, link_type, url])

        total_written += written
        print(f"  {fname} -> {out_name}  ({written:,} rows)")

    print(f"\nDone. {total_written:,} rows written to {output_dir}/")
    print(f"  Alternate names written to: {alternate_names_path}")
    print(f"  External links written to: {external_links_path}")
    print(f"\nTo load into PostgreSQL:")
    print(f"  \\copy work_creator (uuid,creator_name,personal_name,birth_date,death_date,ol_id)")
    print(f"    FROM '<absolute_path>/{output_dir}/work_creator_0001.csv'")
    print(f"    CSV HEADER;")
    print()
    print(f"Or for all files at once (bash):")
    print(f"  for f in {output_dir}/work_creator_*.csv; do")
    print(f"    psql -d <db> -c \"\\copy work_creator (uuid,creator_name,personal_name,birth_date,death_date,ol_id) FROM '$f' CSV HEADER;\"")
    print(f"  done")


def main():
    test_mode = "--test" in sys.argv
    print("=" * 60)
    print("Transform authors CSV -> work_creator CSV")
    print("=" * 60)
    transform_files(INPUT_DIR, OUTPUT_DIR, test_mode)


if __name__ == "__main__":
    main()
