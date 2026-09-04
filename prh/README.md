# PRH ingestion pipeline

Restartable downloader for Penguin Random House author, work, edition, series, and keyword data.

## Design

The downloader writes two layers:

- `prh_data/raw/` — redacted API responses, retained so mappings can be rebuilt without calling PRH again.
- `prh_data/normalized/` — streamable JSONL records used by later stages and the database staging importer.

Failures are appended under `prh_data/failures/`. The author listing also keeps a checkpoint under `prh_data/state/`.

The PostgreSQL importer intentionally writes only to a separate `prh_stage` schema. It does **not** modify Quillent production tables because the final creator/series schema is still being designed.

## Files

- `config.py` — environment/configuration
- `prh_client.py` — requests, retries, redaction, pagination
- `storage.py` — JSONL, checkpoints, failures
- `models.py` — PRH-to-normalized transformations
- `download_authors.py` — enumerate all PRH contributors
- `download_author_profiles.py` — author-display + authoritative author/work lists
- `download_works.py` — work/product-display, editions, creator roles, series hints
- `download_series.py` — canonical series metadata and memberships
- `download_keywords.py` — slow second-pass tag candidates
- `import_postgres.py` — load normalized files into `prh_stage`
- `run_all.py` — convenience runner

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PRH_API_KEY="your-key"
```

Optional configuration:

```bash
export PRH_DOMAIN="PRH.US"
export PRH_DATA_DIR="prh_data"
export PRH_ROWS_PER_PAGE="1000"
export PRH_REQUEST_DELAY="0.25"
export PRH_TIMEOUT="60"
export PRH_KEYWORD_TIMEOUT="180"
export PRH_MAX_RETRIES="5"
```

## Run stages separately

Run from the directory containing this README:

```bash
python3 -m prh_import.download_authors
python3 -m prh_import.download_author_profiles
python3 -m prh_import.download_works
python3 -m prh_import.download_series
python3 -m prh_import.download_keywords
```

The stages are deliberately restartable. Existing normalized IDs are loaded on startup and skipped.

## Run the whole download pipeline

```bash
python3 -m prh_import.run_all
```

Skip the slow keyword pass:

```bash
python3 -m prh_import.run_all --skip-keywords
```

## Resulting data

```text
prh_data/
  raw/
    author_pages.jsonl
    author_display.jsonl
    author_works.jsonl
    works_basic.jsonl
    works_product_display.jsonl
    series.jsonl
    series_works.jsonl
    title_keywords.jsonl

  normalized/
    authors.jsonl
    author_profiles.jsonl
    author_works.jsonl
    works.jsonl
    editions.jsonl
    edition_contributors.jsonl
    work_contributors.jsonl
    series_hints.jsonl
    series.jsonl
    work_series.jsonl
    keywords.jsonl

  failures/
  state/
```

### Important semantics

- `authors.jsonl` contains PRH contributors, not only writers.
- `author_works.jsonl` is used to discover a deduplicated set of Works.
- `works.jsonl` uses the PRH Work as the Goodreads/Quillent-level book.
- `editions.jsonl` stores individual ISBN manifestations.
- `edition_contributors.jsonl` preserves contributor roles such as `Author` and `Read by`; it does not flatten audiobook narrators into book authors.
- `work_contributors.jsonl` aggregates those role observations across a Work while retaining the role and the ISBNs on which it was observed.
- `series_hints.jsonl` is discovery data from Work product responses.
- `work_series.jsonl` is the authoritative series-membership result from `/series/{code}/works`.
- `keywords.jsonl` preserves PRH candidates. It intentionally does not insert them into Quillent tags without the existing tag-cleaning/resolution pipeline.

## PostgreSQL staging

Set a database URL:

```bash
export DATABASE_URL="postgresql://..."
python3 -m prh_import.import_postgres
```

This creates/updates tables under `prh_stage`. It does not alter `quillent_work`, `work_creator`, or other production tables.

You can also stage after the full pipeline:

```bash
python3 -m prh_import.run_all --stage-postgres
```
