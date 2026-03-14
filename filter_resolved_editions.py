#!/usr/bin/env python3
"""
Filter work_editions CSV to keep only rows with resolved work_id (work_id != 0).
Removes editions that couldn't be matched to a work in the database.
"""

import csv
import sys
from pathlib import Path
from typing import Tuple

INPUT_DIR = "work_editions_csv"
OUTPUT_DIR = "work_editions_resolved_csv"

def filter_csv(input_path: Path, output_path: Path) -> Tuple[int, int]:
    """
    Filter a single CSV file, keeping only rows with work_id != 0.
    Returns (total_rows, kept_rows).
    """
    total = 0
    kept = 0

    with open(input_path, "r", encoding="utf-8", newline="") as infile, \
         open(output_path, "w", encoding="utf-8", newline="") as outfile:

        reader = csv.DictReader(infile)
        writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames)
        writer.writeheader()

        for row in reader:
            total += 1
            work_id = row.get("work_id", "0")

            # Keep only resolved works (work_id != 0)
            if work_id and work_id != "0":
                writer.writerow(row)
                kept += 1

    return total, kept

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

    grand_total = 0
    grand_kept = 0

    for input_path in csv_files:
        output_path = output_dir / input_path.name
        total, kept = filter_csv(input_path, output_path)

        grand_total += total
        grand_kept += kept
        removed = total - kept

        print(f"{input_path.name}: {kept:,} kept, {removed:,} removed ({total:,} total)")

    print(f"\nTotal: {grand_kept:,} kept, {grand_total - grand_kept:,} removed ({grand_total:,} total)")
    removed_pct = 100 * (grand_total - grand_kept) / grand_total if grand_total > 0 else 0
    print(f"Removed {removed_pct:.1f}% of editions with unresolved works")

if __name__ == "__main__":
    main()
