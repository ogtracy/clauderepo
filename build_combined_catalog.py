#!/usr/bin/env python3
"""Build the final canonical CSV bundle from already-downloaded OL and PRH data."""

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Parse and transform downloaded Open Library dumps, merge normalized "
            "PRH products, deduplicate the catalog, and write loadable CSVs."
        )
    )
    parser.add_argument("--authors", required=True, type=Path,
                        help="Open Library authors dump (.txt.gz)")
    parser.add_argument("--works", required=True, type=Path,
                        help="Open Library works dump (.txt.gz)")
    parser.add_argument("--editions", required=True, type=Path,
                        help="Open Library editions dump (.txt.gz)")
    parser.add_argument("--prh-products", required=True, type=Path,
                        help="PRH data root or its normalized/ directory")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--similar-authors-limit", type=int, default=20)
    parser.add_argument("--minimum-shared-tags", type=int, default=2)
    args = parser.parse_args()

    runner = Path(__file__).with_name("run_catalog_pipeline.py")
    command = [
        sys.executable, str(runner),
        "--authors", str(args.authors.resolve()),
        "--works", str(args.works.resolve()),
        "--editions", str(args.editions.resolve()),
        "--prh-data-dir", str(args.prh_products.resolve()),
        "--output-dir", str(args.output_dir.resolve()),
        "--similar-authors-limit", str(args.similar_authors_limit),
        "--minimum-shared-tags", str(args.minimum_shared_tags),
    ]
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
