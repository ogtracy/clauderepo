#!/usr/bin/env python3
"""Run the resumable full canonical catalog build from Open Library dumps."""

import argparse
import json
from pathlib import Path

from canonical_catalog import CatalogBuilder
from openlibrary_authors_to_csv import convert_to_csv as parse_authors
from openlibrary_editions_to_csv import convert_to_csv as parse_editions
from openlibrary_works_to_csv import convert_to_csv as parse_works
from transform_authors_to_work_creator import transform_files as transform_authors
from transform_editions_to_work_editions import transform_files as transform_editions
from transform_works_to_quillent_work import transform_files as transform_works


def stage(root: Path, name: str, action):
    marker = root / ".stages" / f"{name}.complete"
    if marker.exists():
        print(f"Skipping completed stage: {name}")
        return
    print(f"\n=== {name} ===")
    action()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("complete\n", encoding="utf-8")


def require_empty_or_resumable(root: Path):
    if not root.exists():
        root.mkdir(parents=True)
        return
    if any(root.iterdir()) and not (root / ".stages").exists():
        raise FileExistsError(
            f"{root} is non-empty and has no pipeline checkpoints; use a new directory"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--authors", required=True, type=Path)
    parser.add_argument("--works", required=True, type=Path)
    parser.add_argument("--editions", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--similar-authors-limit", type=int, default=20)
    parser.add_argument("--minimum-shared-tags", type=int, default=2)
    args = parser.parse_args()
    for path in (args.authors, args.works, args.editions):
        if not path.is_file() or path.suffix != ".gz":
            parser.error(f"expected an existing .gz dump: {path}")

    require_empty_or_resumable(args.output_dir)
    parsed = args.output_dir / "parsed"
    transformed = args.output_dir / "transformed"
    canonical = args.output_dir / "canonical"

    stage(args.output_dir, "parse_authors", lambda: parse_authors(
        str(args.authors), str(parsed / "authors_csv")))
    stage(args.output_dir, "parse_works", lambda: parse_works(
        str(args.works), str(parsed / "works_csv")))
    stage(args.output_dir, "parse_editions", lambda: parse_editions(
        str(args.editions), str(parsed / "editions_csv")))
    stage(args.output_dir, "transform_authors", lambda: transform_authors(
        str(parsed / "authors_csv"), str(transformed / "work_creator_csv")))
    stage(args.output_dir, "transform_works", lambda: transform_works(
        str(parsed / "works_csv"), str(transformed / "quillent_work_csv")))
    stage(args.output_dir, "transform_editions", lambda: transform_editions(
        str(parsed / "editions_csv"),
        str(transformed / "work_editions_csv"), work_mapping=None))

    def canonical_build():
        builder = CatalogBuilder(
            transformed, canonical, canonical / "catalog.duckdb",
            similar_limit=args.similar_authors_limit,
            minimum_shared_tags=args.minimum_shared_tags,
        )
        try:
            summary = builder.run()
        finally:
            builder.close()
        print(json.dumps(summary, indent=2, sort_keys=True))

    stage(args.output_dir, "canonical_build", canonical_build)
    print(f"\nComplete canonical bundle: {canonical}")


if __name__ == "__main__":
    main()
