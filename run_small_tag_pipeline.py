#!/usr/bin/env python3
"""Run the works/tag pipeline on a small local subset.

Examples:
    python3 run_small_tag_pipeline.py
    python3 run_small_tag_pipeline.py --input ol_dump_works_latest.txt.gz --limit 10000
"""

import argparse
import csv
import gzip
import os
from pathlib import Path

from audit_tags import audit_tags
from openlibrary_works_to_csv import parse_work_record
from process_tags import process_tags
from transform_works_to_quillent_work import transform_files


def open_dump(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def parse_subset(input_path: Path, output_file: Path, limit: int):
    output_file.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    writer = None
    with open_dump(input_path) as source, \
         output_file.open("w", encoding="utf-8", newline="") as target:
        for line in source:
            record = parse_work_record(line)
            if record is None:
                continue
            if writer is None:
                writer = csv.DictWriter(target, fieldnames=list(record.keys()))
                writer.writeheader()
            writer.writerow(record)
            written += 1
            if written >= limit:
                break
    if written == 0:
        raise ValueError(f"No valid work records found in {input_path}")
    return written


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="test_works_sample.txt")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--output-dir", default="sample_tag_run")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_root = Path(args.output_dir)
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(
            f"{output_root} is not empty; choose a new --output-dir"
        )

    works_dir = output_root / "works_csv"
    transformed_dir = output_root / "quillent_work_csv"
    tags_dir = output_root / "tags_csv"
    parsed_file = works_dir / "works_0001.csv"

    count = parse_subset(input_path, parsed_file, args.limit)
    transform_files(str(works_dir), str(transformed_dir))
    process_tags(str(transformed_dir / "work_subjects.csv"), str(tags_dir))
    audit_file = output_root / "tag_audit.csv"
    audit_counts = audit_tags(
        str(transformed_dir / "work_subjects.csv"), str(audit_file)
    )

    print("\nSmall tag pipeline completed")
    print(f"Works parsed: {count:,}")
    print(f"Subjects audited: {audit_counts['rows']:,}")
    print(f"Subjects accepted: {audit_counts['accepted']:,}")
    print(f"Subjects rejected: {audit_counts['rejected']:,}")
    print(f"Inspect: {audit_file}")
    print(f"Inspect: {tags_dir / 'search_tag.csv'}")
    print(f"Inspect: {tags_dir / 'work_tags.csv'}")


if __name__ == "__main__":
    main()
