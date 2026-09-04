#!/usr/bin/env python3
"""Build a complete canonical catalog from small dump subsets."""

import argparse
import csv
import gzip
import json
from pathlib import Path

from canonical_catalog import CatalogBuilder
from openlibrary_authors_to_csv import parse_author_record
from openlibrary_editions_to_csv import parse_edition_record
from openlibrary_works_to_csv import parse_work_record
from transform_authors_to_work_creator import transform_files as transform_authors
from transform_editions_to_work_editions import transform_files as transform_editions
from transform_works_to_quillent_work import transform_files as transform_works


def open_dump(path: Path):
    return gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" \
        else path.open("r", encoding="utf-8")


def parse_subset(input_path: Path, output_file: Path, parser, limit: int):
    output_file.parent.mkdir(parents=True, exist_ok=True)
    writer = None
    written = 0
    with open_dump(input_path) as source, \
         output_file.open("w", encoding="utf-8", newline="") as target:
        for line in source:
            record = parser(line)
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
        raise ValueError(f"No valid records found in {input_path}")
    return written


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--authors", type=Path, default=Path("test_authors_sample.txt"))
    parser.add_argument("--works", type=Path, default=Path("test_works_sample.txt"))
    parser.add_argument("--editions", type=Path, default=Path("test_editions_sample.txt"))
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--output-dir", type=Path, default=Path("canonical_sample_run"))
    parser.add_argument("--minimum-shared-tags", type=int, default=1)
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(
            f"{args.output_dir} is not empty; choose a new --output-dir"
        )

    parsed = args.output_dir / "parsed"
    transformed = args.output_dir / "transformed"
    canonical = args.output_dir / "canonical"

    counts = {
        "authors_parsed": parse_subset(
            args.authors, parsed / "authors_csv" / "authors_0001.csv",
            parse_author_record, args.limit,
        ),
        "works_parsed": parse_subset(
            args.works, parsed / "works_csv" / "works_0001.csv",
            parse_work_record, args.limit,
        ),
        "editions_parsed": parse_subset(
            args.editions, parsed / "editions_csv" / "editions_0001.csv",
            parse_edition_record, args.limit,
        ),
    }

    transform_authors(
        str(parsed / "authors_csv"), str(transformed / "work_creator_csv")
    )
    transform_works(
        str(parsed / "works_csv"), str(transformed / "quillent_work_csv")
    )
    transform_editions(
        str(parsed / "editions_csv"), str(transformed / "work_editions_csv"),
        work_mapping=None,
    )

    builder = CatalogBuilder(
        transformed, canonical, canonical / "catalog.duckdb",
        minimum_shared_tags=args.minimum_shared_tags,
    )
    try:
        counts.update(builder.run())
    finally:
        builder.close()

    print("\nCanonical sample pipeline completed")
    print(json.dumps(counts, indent=2, sort_keys=True))
    print(f"Final PostgreSQL-ready CSVs: {canonical}")


if __name__ == "__main__":
    main()
