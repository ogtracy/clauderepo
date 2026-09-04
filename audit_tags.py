#!/usr/bin/env python3
"""Create a human-readable audit of raw Open Library subjects.

The audit never changes the data. It shows the exact source subject, the
normalized tag, and whether the tag would be retained by process_tags.py.
"""

import argparse
import csv
from collections import Counter

from process_tags import MAX_TAG_LENGTH, MIN_TAG_LENGTH, clean_tag


def rejection_reason(source_subject: str, normalized_tag: str) -> str:
    if not source_subject or not source_subject.strip():
        return "empty source subject"
    if not normalized_tag:
        # clean_tag returns empty for both bounds; reproduce the normalized
        # length only to make the audit actionable.
        compact = " ".join(source_subject.split())
        if len(compact) < MIN_TAG_LENGTH:
            return "shorter than minimum length"
        if len(compact) > MAX_TAG_LENGTH:
            return "longer than maximum length"
        return "empty after normalization"
    return ""


def audit_tags(input_file: str, output_file: str, limit=None):
    counts = Counter()
    with open(input_file, "r", encoding="utf-8", newline="") as source, \
         open(output_file, "w", encoding="utf-8", newline="") as target:
        reader = csv.DictReader(source)
        required = {"work_id", "work_external_id", "subject"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(
                "work_subjects.csv must contain work_id, work_external_id, and subject"
            )

        writer = csv.DictWriter(target, fieldnames=[
            "work_id", "work_external_id", "source_subject",
            "normalized_tag", "accepted", "rejection_reason",
        ])
        writer.writeheader()

        for index, row in enumerate(reader):
            if limit is not None and index >= limit:
                break
            source_subject = row["subject"]
            normalized_tag = clean_tag(source_subject)
            reason = rejection_reason(source_subject, normalized_tag)
            accepted = not reason
            counts["rows"] += 1
            counts["accepted" if accepted else "rejected"] += 1
            if any(mark in source_subject for mark in (",", ";", "/", ":", "|")):
                counts["punctuated"] += 1
            writer.writerow({
                "work_id": row["work_id"],
                "work_external_id": row["work_external_id"],
                "source_subject": source_subject,
                "normalized_tag": normalized_tag,
                "accepted": str(accepted).lower(),
                "rejection_reason": reason,
            })
    return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="quillent_work_csv/work_subjects.csv")
    parser.add_argument("--output", default="tag_audit.csv")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    counts = audit_tags(args.input, args.output, args.limit)
    print(f"Audited {counts['rows']:,} source subjects")
    print(f"Accepted: {counts['accepted']:,}")
    print(f"Rejected: {counts['rejected']:,}")
    print(f"Subjects containing punctuation: {counts['punctuated']:,}")
    print(f"Audit file: {args.output}")


if __name__ == "__main__":
    main()
