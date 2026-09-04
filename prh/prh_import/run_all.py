from __future__ import annotations

import argparse

from .config import Config
from . import download_authors, download_author_profiles, download_works, download_series, download_keywords
from . import import_postgres


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the PRH ingestion pipeline")
    parser.add_argument("--skip-keywords", action="store_true", help="Skip slow keyword enrichment")
    parser.add_argument("--stage-postgres", action="store_true", help="Load normalized JSONL into prh_stage tables")
    args = parser.parse_args()

    config = Config.from_env()
    print("1/5 Downloading authors")
    download_authors.run(config)
    print("2/5 Downloading author profiles and work lists")
    download_author_profiles.run(config)
    print("3/5 Downloading works and editions")
    download_works.run(config)
    print("4/5 Downloading series")
    download_series.run(config)

    if args.skip_keywords:
        print("5/5 Keywords skipped")
    else:
        print("5/5 Downloading keywords")
        download_keywords.run(config)

    if args.stage_postgres:
        import_postgres.run(Config.from_env(require_api_key=False))


if __name__ == "__main__":
    main()
