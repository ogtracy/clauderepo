#!/usr/bin/env python3
"""
Generate work_creators join table CSV from works data.
Creates many-to-many relationship between works and creators (authors).
"""

import csv
import sys
from pathlib import Path
from typing import Dict, Tuple

WORKS_INPUT_DIR = "works_csv"          # Original works data with authors
QUILLENT_WORK_DIR = "quillent_work_csv"  # Transformed works with work IDs
OUTPUT_DIR = "work_creators_csv"

# Output columns for work_creators join table
FIELDNAMES = ["work_id", "creator_uuid"]

def load_work_id_mapping(quillent_work_dir: Path) -> Dict[str, str]:
    """
    Load mapping from work UUID to work ID from quillent_work CSV files.
    Returns dict: {uuid: work_id}
    """
    mapping = {}
    csv_files = sorted(quillent_work_dir.glob("*.csv"))

    for csv_file in csv_files:
        with open(csv_file, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                uuid = row.get("uuid", "")
                work_id = row.get("id", "")
                if uuid and work_id:
                    mapping[uuid] = work_id

    return mapping

def process_csv(input_path: Path, output_path: Path, work_id_mapping: Dict[str, str]) -> Tuple[int, int, int]:
    """
    Process a single works CSV file to extract work-creator relationships.
    Returns (total_works, total_relationships, skipped_works).
    """
    total_works = 0
    total_relationships = 0
    skipped_works = 0

    with open(input_path, "r", encoding="utf-8", newline="") as infile, \
         open(output_path, "w", encoding="utf-8", newline="") as outfile:

        reader = csv.DictReader(infile)
        writer = csv.DictWriter(outfile, fieldnames=FIELDNAMES)
        writer.writeheader()

        for row in reader:
            total_works += 1

            work_key = row.get("key", "").strip('"')
            authors_str = row.get("authors", "")

            # Get work_id from mapping
            work_id = work_id_mapping.get(work_key)

            if not work_id:
                skipped_works += 1
                continue

            if not authors_str:
                continue

            # Authors are comma-separated author keys: /authors/OL1A, /authors/OL2A
            author_keys = [key.strip() for key in authors_str.split(',') if key.strip()]

            for author_key in author_keys:
                writer.writerow({
                    "work_id": work_id,
                    "creator_uuid": author_key
                })
                total_relationships += 1

    return total_works, total_relationships, skipped_works

def main():
    works_dir = Path(WORKS_INPUT_DIR)
    quillent_work_dir = Path(QUILLENT_WORK_DIR)
    output_dir = Path(OUTPUT_DIR)

    if not works_dir.exists():
        print(f"ERROR: Input directory '{WORKS_INPUT_DIR}' not found", file=sys.stderr)
        sys.exit(1)

    if not quillent_work_dir.exists():
        print(f"ERROR: Quillent work directory '{QUILLENT_WORK_DIR}' not found", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(exist_ok=True)

    # Load work UUID -> work ID mapping
    print("Loading work ID mappings...")
    work_id_mapping = load_work_id_mapping(quillent_work_dir)
    print(f"Loaded {len(work_id_mapping):,} work ID mappings")

    csv_files = sorted(works_dir.glob("*.csv"))
    if not csv_files:
        print(f"WARNING: No CSV files found in '{WORKS_INPUT_DIR}'", file=sys.stderr)
        return

    grand_total_works = 0
    grand_total_relationships = 0
    grand_skipped = 0

    for input_path in csv_files:
        output_path = output_dir / input_path.name
        total_works, total_relationships, skipped = process_csv(input_path, output_path, work_id_mapping)

        grand_total_works += total_works
        grand_total_relationships += total_relationships
        grand_skipped += skipped

        print(f"{input_path.name}: {total_relationships:,} relationships from {total_works:,} works ({skipped:,} skipped)")

    print(f"\nTotal: {grand_total_relationships:,} work-creator relationships from {grand_total_works:,} works")
    print(f"Skipped: {grand_skipped:,} works (not found in quillent_work mapping)")

    if grand_total_works - grand_skipped > 0:
        avg_authors = grand_total_relationships / (grand_total_works - grand_skipped)
        print(f"Average: {avg_authors:.2f} authors per work")

if __name__ == "__main__":
    main()
