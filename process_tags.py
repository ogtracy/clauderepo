#!/usr/bin/env python3
"""
Process Open Library subjects into clean tags.

Reads work_subjects.csv (output of transform_works_to_quillent_work.py) and
generates two CSV files:
  - search_tag.csv     (id, uuid, tag_name, prevalence, weight)
  - work_tags.csv      (work_id, tag_id)

Tag cleaning strategy:
  1. Split on multiple delimiters: ;  ,  |  /  :
  2. Normalize: lowercase, trim, normalize whitespace
  3. Remove leading/trailing punctuation
  4. Filter by length (min 2, max 80 characters)
  5. Keep all tags (no deduplication)

Usage:
    python3 process_tags.py                # process all
    python3 process_tags.py --test         # first 1000 works only
"""

import csv
import os
import re
import sys
from collections import defaultdict
from typing import List, Dict, Set

INPUT_FILE = "quillent_work_csv/work_subjects.csv"
OUTPUT_DIR = "tags_csv"
TAGS_FILE = "search_tag.csv"
WORK_TAGS_FILE = "work_tags.csv"

# Tag constraints
MIN_TAG_LENGTH = 2
MAX_TAG_LENGTH = 80

# Regex for splitting on multiple delimiters
# Split on: semicolon, pipe, comma, colon (when followed by space), slash (when surrounded by spaces)
SPLIT_PATTERN = re.compile(r'\s*[;|,]\s*|\s+/\s+|\s*:\s+')

# Regex for removing leading/trailing punctuation
PUNCT_PATTERN = re.compile(r'^[\W_]+|[\W_]+$')


def clean_tag(raw_tag: str) -> str:
    """
    Clean a single tag string.

    Args:
        raw_tag: Raw tag string from Open Library

    Returns:
        Cleaned tag string, or empty string if invalid
    """
    # Lowercase
    tag = raw_tag.lower()

    # Normalize whitespace (multiple spaces/tabs → single space)
    tag = ' '.join(tag.split())

    # Remove leading/trailing punctuation
    tag = PUNCT_PATTERN.sub('', tag)

    # Trim again after punctuation removal
    tag = tag.strip()

    # Filter by length
    if len(tag) < MIN_TAG_LENGTH or len(tag) > MAX_TAG_LENGTH:
        return ""

    return tag


def split_and_clean_subjects(subjects_str: str) -> List[str]:
    """
    Split a subjects string into individual cleaned tags.

    Args:
        subjects_str: Semicolon/comma/pipe-separated subjects string

    Returns:
        List of cleaned, unique tags
    """
    if not subjects_str:
        return []

    # Split on multiple delimiters
    raw_tags = SPLIT_PATTERN.split(subjects_str)

    # Clean each tag
    cleaned = []
    seen = set()  # Deduplicate within single work (but not across works)

    for raw in raw_tags:
        tag = clean_tag(raw)
        if tag and tag not in seen:
            cleaned.append(tag)
            seen.add(tag)

    return cleaned


def process_tags(input_file: str, output_dir: str, test_mode: bool = False):
    """
    Process work subjects into clean tag tables.

    Args:
        input_file: Path to work_subjects.csv
        output_dir: Directory to write output CSVs
        test_mode: If True, only process first 1000 works
    """
    if not os.path.isfile(input_file):
        print(f"ERROR: input file '{input_file}' does not exist.", file=sys.stderr)
        print(f"Run transform_works_to_quillent_work.py first to generate it.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    print("=" * 80)
    print("Processing Open Library subjects → tags")
    print("=" * 80)
    print(f"Input:  {input_file}")
    print(f"Output: {output_dir}/")
    print()

    # Phase 1: Read all subjects and build vocabulary
    print("Phase 1: Reading subjects and building vocabulary...")
    tag_vocabulary = defaultdict(int)  # {tag_name: count}
    work_tags_map = {}  # {work_id: [tag1, tag2, ...]}
    works_processed = 0

    with open(input_file, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            work_id = int(row["work_id"])
            subjects_str = row["subjects"]

            # Split and clean
            tags = split_and_clean_subjects(subjects_str)

            if tags:
                work_tags_map[work_id] = tags
                for tag in tags:
                    tag_vocabulary[tag] += 1

            works_processed += 1
            if works_processed % 100000 == 0:
                print(f"  Processed {works_processed:,} works, {len(tag_vocabulary):,} unique tags found")

            if test_mode and works_processed >= 1000:
                print(f"  TEST MODE: stopping at 1,000 works")
                break

    print(f"\nPhase 1 complete:")
    print(f"  Works with subjects: {len(work_tags_map):,}")
    print(f"  Unique tags: {len(tag_vocabulary):,}")
    print()

    # Phase 2: Assign IDs and calculate weights
    print("Phase 2: Assigning IDs and calculating weights...")

    # Sort tags by prevalence (descending) for consistent ordering
    sorted_tags = sorted(tag_vocabulary.items(), key=lambda x: x[1], reverse=True)

    tag_to_id = {}  # {tag_name: tag_id}
    tag_records = []  # List of dicts for search_tag.csv

    total_works = works_processed
    for idx, (tag_name, prevalence) in enumerate(sorted_tags, start=1):
        tag_id = idx
        uuid = f"/tags/{tag_name.replace(' ', '-')}"

        # Calculate weight (inverse document frequency style)
        # More common tags get lower weight
        # weight = log(total_works / prevalence), normalized to 0-1 range
        import math
        if total_works > 0:
            idf = math.log(total_works / prevalence)
            max_idf = math.log(total_works)
            weight = round(idf / max_idf, 4) if max_idf > 0 else 0.5
        else:
            weight = 0.5

        tag_to_id[tag_name] = tag_id
        tag_records.append({
            "id": tag_id,
            "uuid": uuid,
            "tag_name": tag_name,
            "prevalence": prevalence,
            "weight": weight,
        })

    print(f"  Assigned IDs: 1 to {len(tag_records):,}")
    print()

    # Phase 3: Write search_tag.csv
    print("Phase 3: Writing search_tag.csv...")
    tags_path = os.path.join(output_dir, TAGS_FILE)
    with open(tags_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["id", "uuid", "tag_name", "prevalence", "weight"],
            quoting=csv.QUOTE_MINIMAL,
        )
        writer.writeheader()
        writer.writerows(tag_records)

    print(f"  Wrote {len(tag_records):,} tags to {tags_path}")
    print()

    # Phase 4: Write work_tags.csv
    print("Phase 4: Writing work_tags.csv...")
    work_tags_path = os.path.join(output_dir, WORK_TAGS_FILE)
    total_associations = 0

    with open(work_tags_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(["work_id", "tag_id"])

        for work_id in sorted(work_tags_map.keys()):
            tags = work_tags_map[work_id]
            for tag_name in tags:
                tag_id = tag_to_id[tag_name]
                writer.writerow([work_id, tag_id])
                total_associations += 1

    print(f"  Wrote {total_associations:,} work-tag associations to {work_tags_path}")
    print()

    # Summary
    print("=" * 80)
    print("Tag processing complete!")
    print("=" * 80)
    print(f"Files created:")
    print(f"  {tags_path}")
    print(f"  {work_tags_path}")
    print()
    print(f"Statistics:")
    print(f"  Works processed:      {works_processed:,}")
    print(f"  Works with subjects:  {len(work_tags_map):,}")
    print(f"  Unique tags:          {len(tag_records):,}")
    print(f"  Work-tag associations: {total_associations:,}")
    print(f"  Avg tags per work:    {total_associations / len(work_tags_map):.1f}")
    print()
    print(f"To load into PostgreSQL:")
    print(f"  \\copy search_tag (id,uuid,tag_name,prevalence,weight)")
    print(f"    FROM '{tags_path}' CSV HEADER;")
    print()
    print(f"  -- Reset sequence")
    print(f"  SELECT setval('search_tag_id_seq', (SELECT MAX(id) FROM search_tag));")
    print()
    print(f"  \\copy work_tags (work_id,tag_id)")
    print(f"    FROM '{work_tags_path}' CSV HEADER;")


def main():
    test_mode = "--test" in sys.argv
    if test_mode:
        print("TEST MODE: Processing first 1,000 works only")
        print()

    process_tags(INPUT_FILE, OUTPUT_DIR, test_mode)


if __name__ == "__main__":
    main()
