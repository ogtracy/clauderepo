#!/usr/bin/env python3
"""
Generate work_cover_urls CSV from quillent_work CSV files.
Creates cover URLs from cover_id using OpenLibrary's cover image URL pattern.
"""

import csv
import sys
from pathlib import Path

INPUT_DIR = "quillent_work_csv"
OUTPUT_DIR = "work_cover_urls_csv"

OL_COVER_BASE = "https://covers.openlibrary.org/b/id/"
COVER_SIZE = "M"  # S, M, or L

# Output columns for work_cover_urls table
FIELDNAMES = ["work_id", "url"]

def generate_cover_url(cover_id: str) -> str:
    """Generate OpenLibrary cover URL from cover ID."""
    return f"{OL_COVER_BASE}{cover_id}-{COVER_SIZE}.jpg"

def process_csv(input_path: Path, output_path: Path) -> tuple:
    """
    Process a single quillent_work CSV file to extract cover URLs.
    Returns (total_works, urls_generated).
    """
    total_works = 0
    urls_generated = 0

    with open(input_path, "r", encoding="utf-8", newline="") as infile, \
         open(output_path, "w", encoding="utf-8", newline="") as outfile:

        reader = csv.DictReader(infile)
        writer = csv.DictWriter(outfile, fieldnames=FIELDNAMES)
        writer.writeheader()

        for row in reader:
            total_works += 1

            work_id = row.get("id", "")
            cover_id = row.get("cover_id", "")

            # Only generate URL if both work_id and cover_id exist
            if work_id and cover_id:
                url = generate_cover_url(cover_id)
                writer.writerow({
                    "work_id": work_id,
                    "url": url
                })
                urls_generated += 1

    return total_works, urls_generated

def main():
    input_dir = Path(INPUT_DIR)
    output_dir = Path(OUTPUT_DIR)

    if not input_dir.exists():
        print(f"ERROR: Input directory '{INPUT_DIR}' not found", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(exist_ok=True)

    csv_files = sorted(input_dir.glob("*.csv"))
    if not csv_files:
        print(f"WARNING: No CSV files found in '{INPUT_DIR}'", file=sys.stderr)
        return

    grand_total_works = 0
    grand_total_urls = 0

    for input_path in csv_files:
        output_path = output_dir / input_path.name
        total_works, urls_generated = process_csv(input_path, output_path)

        grand_total_works += total_works
        grand_total_urls += urls_generated

        print(f"{input_path.name}: {urls_generated:,} cover URLs generated from {total_works:,} works")

    print(f"\nTotal: {grand_total_urls:,} cover URLs generated from {grand_total_works:,} works")

    if grand_total_works > 0:
        coverage_pct = 100 * grand_total_urls / grand_total_works
        print(f"Coverage: {coverage_pct:.1f}% of works have cover images")

if __name__ == "__main__":
    main()
