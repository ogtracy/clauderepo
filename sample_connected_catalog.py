#!/usr/bin/env python3
"""Create a relationship-connected Open Library sample from full dumps.

The ordinary first-N slices of the three independent dumps do not line up.
This sampler chooses works first, then retains editions that reference those
works and author records referenced by either works or retained editions.
The result can be passed directly to run_catalog_pipeline.py.
"""

import argparse
import gzip
import json
import random
from pathlib import Path


def open_text(path: Path, mode: str):
    if path.suffix == ".gz":
        return gzip.open(path, mode + "t", encoding="utf-8")
    return path.open(mode, encoding="utf-8")


def raw_record(line: str):
    parts = line.rstrip("\n").split("\t", 4)
    if len(parts) != 5:
        return None
    try:
        return parts[1], json.loads(parts[4])
    except (TypeError, ValueError):
        return None


def reference_keys(values):
    result = []
    if not isinstance(values, list):
        return result
    for value in values:
        if not isinstance(value, dict):
            continue
        reference = value.get("author", value)
        if isinstance(reference, dict):
            key = reference.get("key")
        else:
            key = reference if isinstance(reference, str) else None
        if key:
            result.append(key)
    return result


def choose_works(path: Path, count: int, selection: str, seed: int):
    chosen = []
    valid_seen = 0
    generator = random.Random(seed)
    with open_text(path, "r") as source:
        for line in source:
            parsed = raw_record(line)
            if parsed is None or not parsed[0].startswith("/works/"):
                continue
            valid_seen += 1
            if len(chosen) < count:
                chosen.append((parsed[0], parsed[1], line))
            elif selection == "reservoir":
                replacement = generator.randrange(valid_seen)
                if replacement < count:
                    chosen[replacement] = (parsed[0], parsed[1], line)
            elif selection == "first":
                break
    if len(chosen) < count:
        raise ValueError(f"Requested {count} works but found only {len(chosen)}")
    return sorted(chosen, key=lambda item: item[0]), valid_seen


def build_sample(args):
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if any(args.output_dir.iterdir()):
        raise FileExistsError(f"{args.output_dir} must be empty")

    works, works_seen = choose_works(
        args.works, args.work_count, args.selection, args.seed
    )
    work_keys = {key for key, _, _ in works}
    author_keys = {
        author_key
        for _, data, _ in works
        for author_key in reference_keys(data.get("authors", []))
    }

    works_output = args.output_dir / "works.txt.gz"
    editions_output = args.output_dir / "editions.txt.gz"
    authors_output = args.output_dir / "authors.txt.gz"
    with gzip.open(works_output, "wt", encoding="utf-8") as target:
        for _, _, line in works:
            target.write(line if line.endswith("\n") else line + "\n")

    edition_counts = {key: 0 for key in work_keys}
    editions_written = 0
    editions_seen = 0
    with open_text(args.editions, "r") as source, \
            gzip.open(editions_output, "wt", encoding="utf-8") as target:
        for line in source:
            parsed = raw_record(line)
            if parsed is None:
                continue
            editions_seen += 1
            data = parsed[1]
            referenced = set(reference_keys(data.get("works", []))) & work_keys
            eligible = {
                key for key in referenced
                if args.max_editions_per_work == 0
                or edition_counts[key] < args.max_editions_per_work
            }
            if not eligible:
                continue
            target.write(line if line.endswith("\n") else line + "\n")
            editions_written += 1
            for key in eligible:
                edition_counts[key] += 1
            author_keys.update(reference_keys(data.get("authors", [])))

    authors_written = 0
    authors_seen = 0
    found_author_keys = set()
    with open_text(args.authors, "r") as source, \
            gzip.open(authors_output, "wt", encoding="utf-8") as target:
        for line in source:
            parsed = raw_record(line)
            if parsed is None:
                continue
            authors_seen += 1
            if parsed[0] not in author_keys:
                continue
            target.write(line if line.endswith("\n") else line + "\n")
            authors_written += 1
            found_author_keys.add(parsed[0])

    manifest = {
        "selection": args.selection,
        "seed": args.seed,
        "works_seen": works_seen,
        "works_written": len(works),
        "works_without_editions": sum(count == 0 for count in edition_counts.values()),
        "editions_seen": editions_seen,
        "editions_written": editions_written,
        "authors_seen": authors_seen,
        "authors_referenced": len(author_keys),
        "authors_written": authors_written,
        "missing_author_records": sorted(author_keys - found_author_keys),
    }
    (args.output_dir / "sample_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--authors", required=True, type=Path)
    parser.add_argument("--works", required=True, type=Path)
    parser.add_argument("--editions", required=True, type=Path)
    parser.add_argument("--work-count", type=int, default=10_000)
    parser.add_argument("--max-editions-per-work", type=int, default=25,
                        help="0 keeps every edition")
    parser.add_argument("--selection", choices=("reservoir", "first"),
                        default="reservoir")
    parser.add_argument("--seed", type=int, default=20260904)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    for path in (args.authors, args.works, args.editions):
        if not path.is_file():
            parser.error(f"file not found: {path}")
    if args.work_count < 1 or args.max_editions_per_work < 0:
        parser.error("counts must be positive (edition cap may be zero)")
    print(json.dumps(build_sample(args), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
