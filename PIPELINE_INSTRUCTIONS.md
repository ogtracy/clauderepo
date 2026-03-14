# Open Library → PostgreSQL Pipeline

End-to-end instructions for downloading the Open Library data dumps, parsing
them to CSV, transforming the CSV to match the database schema, and loading
everything into PostgreSQL.

---

## Overview

The pipeline has four stages:

```
Stage 1 — Download    Raw .gz dumps from openlibrary.org
Stage 2 — Parse       .gz JSONL → split CSV files
Stage 3 — Transform   Generic CSV → DB-schema CSV
Stage 4 — Load        CSV → PostgreSQL via COPY
```

Three data types flow through the pipeline:

| Data type | Dump file (~compressed size) | Target table |
|-----------|------------------------------|--------------|
| Authors   | ol_dump_authors_latest.txt.gz (~1 GB)  | work_creator |
| Works     | ol_dump_works_latest.txt.gz (~3 GB)    | quillent_work |
| Editions  | ol_dump_editions_latest.txt.gz (~25 GB) | work_editions |

Estimated total disk space required:

| Artifact | Size |
|----------|------|
| Compressed dumps | ~30 GB |
| Parsed CSV (all three) | ~150 GB |
| DB-schema CSV (all three) | ~100 GB |
| PostgreSQL data (loaded) | ~200–300 GB |
| **Total peak** | **~450–500 GB** |

---

## Prerequisites

### Software

- Python 3.6+, standard library only (no pip installs needed)
- PostgreSQL 13+ with enough disk for the tables above
- `psql` available on the command line

### Python

```bash
python3 --version   # must be 3.6+
```

### PostgreSQL

```bash
psql --version
psql -d <db> -c "SELECT version();"
```

The tables must already exist. The pipeline does not create them.

---

## Stage 1 — Download the dump files

Open Library publishes monthly snapshots at:
`https://openlibrary.org/developers/dumps`

Download all three dumps. Each is a gzip-compressed text file.

```bash
# Authors (~1 GB)
curl -O https://openlibrary.org/data/ol_dump_authors_latest.txt.gz

# Works (~3 GB)
curl -O https://openlibrary.org/data/ol_dump_works_latest.txt.gz

# Editions (~25 GB) — largest file, allow several hours
curl -O https://openlibrary.org/data/ol_dump_editions_latest.txt.gz
```

Or download in parallel (three terminals / background jobs):

```bash
curl -O https://openlibrary.org/data/ol_dump_authors_latest.txt.gz &
curl -O https://openlibrary.org/data/ol_dump_works_latest.txt.gz &
curl -O https://openlibrary.org/data/ol_dump_editions_latest.txt.gz &
wait
```

### Dump file format

Each `.txt.gz` file is a gzip-compressed, UTF-8 encoded text file. Each line
is a record with five tab-separated columns:

```
type    key    revision    last_modified    json_data
```

Example author line (truncated):
```
/type/author    /authors/OL1A    3    2010-04-24T17:54:27    {"name": "Foo Bar", ...}
```

The scripts read the files line-by-line (streaming) and never load the full
file into memory, so RAM usage stays low regardless of file size.

---

## Stage 2 — Parse dumps to CSV

Each converter script reads the `.gz` file directly and writes split CSV files
(10,000 records per file) into an output directory.

### Authors → authors_csv/

```bash
python3 openlibrary_authors_to_csv.py
```

- Input:  `ol_dump_authors_latest.txt.gz`
- Output: `authors_csv/authors_0001.csv`, `authors_0002.csv`, …
- Columns: `key, type, revision, last_modified, name, personal_name,`
           `birth_date, death_date, bio, alternate_names, wikipedia, website`

### Works → works_csv/

```bash
python3 openlibrary_works_to_csv.py
```

- Input:  `ol_dump_works_latest.txt.gz`
- Output: `works_csv/works_0001.csv`, `works_0002.csv`, …
- Columns: `key, type, revision, last_modified, title, subtitle, authors,`
           `subjects, subject_places, subject_times, description,`
           `first_publish_date, covers, number_of_editions`

### Editions → editions_csv/

```bash
python3 openlibrary_editions_to_csv.py
```

- Input:  `ol_dump_editions_latest.txt.gz`
- Output: `editions_csv/editions_0001.csv`, `editions_0002.csv`, …
- Columns: `key, type, revision, last_modified, title, subtitle, authors,`
           `works, publishers, publish_date, publish_places, isbn_10, isbn_13,`
           `lccn, oclc_numbers, number_of_pages, pagination, physical_format,`
           `covers, languages`

### Running all three in parallel

The three scripts are fully independent and can run simultaneously:

```bash
python3 openlibrary_authors_to_csv.py  > parse_authors.log 2>&1 &
python3 openlibrary_works_to_csv.py    > parse_works.log   2>&1 &
python3 openlibrary_editions_to_csv.py > parse_editions.log 2>&1 &
wait
echo "All parsing complete"
```

### Test mode

Each script accepts a `--test` flag that limits the download to 10 MB and
processes only 1,000 records — useful for verifying the pipeline before
committing to the full run:

```bash
python3 openlibrary_authors_to_csv.py --test
python3 openlibrary_works_to_csv.py --test
python3 openlibrary_editions_to_csv.py --test
```

---

## Stage 3 — Transform CSV to DB schema

Each transform script reads the generic CSV files from Stage 2, remaps and
renames columns to match the target table, and writes new CSV files ready for
PostgreSQL `COPY`.

### authors_csv/ → work_creator_csv/

```bash
python3 transform_authors_to_work_creator.py
```

- Input:  `authors_csv/`
- Output: `work_creator_csv/work_creator_0001.csv`, …
- Column mapping:

  | authors CSV | work_creator |
  |-------------|--------------|
  | key | uuid (`/authors/OL1A`) |
  | name | creator_name |
  | personal_name | personal_name |
  | birth_date | birth_date |
  | death_date | death_date |
  | key (suffix) | ol_id (`OL1A`) |

### works_csv/ → quillent_work_csv/

```bash
python3 transform_works_to_quillent_work.py
```

- Input:  `works_csv/`
- Output: `quillent_work_csv/quillent_work_0001.csv`, …
- Notable mappings:
  - `key` → `uuid` and `ol_id` (bare suffix)
  - `subtitle` → `sub_title`
  - `first_publish_date` → `first_publication_date` (raw) and
    `publication_date_epoch` (epoch days, best-effort parse)
  - `covers` → `cover_id` (first valid ID) and
    `featured_covers` (JSON int array, `-1` placeholders removed)
  - `goodreads_resolved`, `google_resolved` → `false`
  - Fields not in OL works data (`isbn_ten/thirteen`, `language_code`,
    `num_of_pages`, `featured_edition*`, `series`, `prh_id`) → empty

### editions_csv/ → work_editions_csv/

**PREREQUISITE:** quillent_work_csv/ must exist first (output of transform_works_to_quillent_work.py).

```bash
python3 transform_editions_to_work_editions.py
```

This script reads the quillent_work CSV files to resolve `work_id` during transformation,
eliminating the need for post-load UPDATE JOIN.

- Input:  `editions_csv/` and `quillent_work_csv/` (for ID mapping)
- Output: `work_editions_csv/work_editions_0001.csv`, …
- Reads quillent_work CSVs to build ol_id → id mapping in memory
- Notable mappings:
  - `key` → `uuid` and `ol_id` (bare suffix e.g. `OL1M`)
  - `works[0]` → `work_ol_id` (first linked work's bare ID e.g. `OL1W`)
  - `work_id` → resolved from quillent_work CSV mapping (0 if work not found)
  - `publishers[0]` → `publisher` (first semicolon-delimited value)
  - `isbn_10[0]` / `isbn_13[0]` → `isbn_ten` / `isbn_thirteen`
  - `lccn[0]` → `lccn`, `oclc_numbers[0]` → `oclc_number`
  - `publish_date` → `publication_date` (raw) and
    `publication_year` (4-digit year extracted via regex)
  - `is_featured` → `false`
  - Fields not in OL data (`series`, `goodreads_id`, `google_id`, `asin`)
    → empty

### Running transforms

**Authors and works** can run in parallel. **Editions** must run AFTER works transform completes:

```bash
# Step 1: Transform authors and works in parallel
python3 transform_authors_to_work_creator.py   > transform_authors.log 2>&1 &
python3 transform_works_to_quillent_work.py    > transform_works.log   2>&1 &
wait

# Step 2: Transform editions (requires quillent_work CSVs)
python3 transform_editions_to_work_editions.py > transform_editions.log 2>&1
```

---

## Stage 4 — Load into PostgreSQL

See **[DB_LOAD_INSTRUCTIONS.md](DB_LOAD_INSTRUCTIONS.md)** for the complete
loading procedure. The condensed sequence is:

```
1. Drop secondary indexes on all three tables
2. COPY work_creator       (work_creator_csv/)
3. COPY quillent_work      (quillent_work_csv/, with pre-assigned IDs)
4. Reset quillent_work sequence
5. COPY work_editions      (work_editions_csv/, work_id already resolved)
6. Rebuild all secondary indexes
7. ANALYZE
```

**Key workflow change:** IDs are pre-assigned in the works CSV, and editions
reference these IDs directly. No database queries or post-load UPDATE JOIN needed.

---

## Running the full pipeline end-to-end

```bash
# Stage 1 — download (sequential; each file is large)
curl -O https://openlibrary.org/data/ol_dump_authors_latest.txt.gz
curl -O https://openlibrary.org/data/ol_dump_works_latest.txt.gz
curl -O https://openlibrary.org/data/ol_dump_editions_latest.txt.gz

# Stage 2 — parse (run in parallel)
python3 openlibrary_authors_to_csv.py  > parse_authors.log  2>&1 &
python3 openlibrary_works_to_csv.py    > parse_works.log    2>&1 &
python3 openlibrary_editions_to_csv.py > parse_editions.log 2>&1 &
wait

# Stage 3 — transform (authors + works in parallel, then editions)
python3 transform_authors_to_work_creator.py > transform_authors.log 2>&1 &
python3 transform_works_to_quillent_work.py  > transform_works.log   2>&1 &
wait
python3 transform_editions_to_work_editions.py > transform_editions.log 2>&1

# Stage 4 — load (see DB_LOAD_INSTRUCTIONS.md for full SQL)
psql -d <db> -f pre_load.sql          # drop indexes

# Load authors
for f in work_creator_csv/work_creator_*.csv; do
    psql -d <db> -c "\copy work_creator (uuid,creator_name,personal_name,birth_date,death_date,ol_id) FROM '$f' CSV HEADER;"
done

# Load works (with pre-assigned IDs)
for f in quillent_work_csv/quillent_work_*.csv; do
    psql -d <db> -c "\copy quillent_work (id,uuid,title,sub_title,description,first_publication_date,publication_date_epoch,isbn_ten,isbn_thirteen,language_code,num_of_pages,ol_id,cover_id,featured_edition,featured_edition_id,featured_edition_fk,series,position_in_series,reading_id,prh_id,goodreads_resolved,google_resolved,featured_covers) FROM '$f' CSV HEADER;"
done

# Reset works sequence
psql -d <db> -c "SELECT setval('quillent_work_id_seq', (SELECT MAX(id) FROM quillent_work));"

# Load editions (work_id already resolved)
for f in work_editions_csv/work_editions_*.csv; do
    psql -d <db> -c "\copy work_editions (uuid,work_id,isbn_ten,isbn_thirteen,publication_date,publication_year,ol_id,work_ol_id,number_of_pages,lccn,oclc_number,publisher,series,goodreads_id,google_id,asin,is_featured) FROM '$f' CSV HEADER;"
done

psql -d <db> -f post_load.sql         # rebuild indexes, ANALYZE
```

---

## Resuming a partial run

The scripts are safe to re-run. If a converter or transform is interrupted:

- Delete the incomplete output directory and re-run the script, or
- The scripts write complete files only; partial files from a crash will be the
  only incomplete one (identifiable by file size much smaller than the others).

If a `COPY` batch is interrupted mid-table, truncate the table and restart:

```sql
TRUNCATE work_editions;  -- or whichever table was partially loaded
```

Then re-run the COPY loop for that table.

---

## Troubleshooting

### Download fails or is slow

The OL servers can be slow. Use `curl -C -` to resume a partial download:

```bash
curl -C - -O https://openlibrary.org/data/ol_dump_editions_latest.txt.gz
```

Alternatively, download from the Internet Archive mirror, which is typically
faster:
`https://archive.org/details/ol_exports`

### "invalid byte sequence for encoding UTF8"

The dumps are UTF-8 but occasionally contain stray bytes. The scripts open
files with `encoding='utf-8'`. If PostgreSQL rejects a file, re-encode it:

```bash
iconv -f utf-8 -t utf-8 -c work_creator_csv/work_creator_0001.csv \
    -o work_creator_csv/work_creator_0001_clean.csv
```

The `-c` flag silently drops invalid characters.

### COPY is slower than expected

- Make sure `synchronous_commit = off` for the session (safe for bulk loads):
  ```sql
  SET synchronous_commit = off;
  ```
- Increase `maintenance_work_mem` for index builds:
  ```sql
  SET maintenance_work_mem = '2GB';
  ```
- Use `UNLOGGED` tables during load, then `ALTER TABLE ... SET LOGGED` after:
  ```sql
  ALTER TABLE work_editions SET UNLOGGED;
  -- run COPY
  ALTER TABLE work_editions SET LOGGED;
  ```

### work_id still 0 after FK resolution UPDATE

Editions whose `work_ol_id` does not match any row in `quillent_work` will
keep `work_id = 0`. This happens when an edition references a work that was
deleted from OL or is missing from the dump. Check the count and decide:

```sql
SELECT COUNT(*) FROM work_editions WHERE work_id = 0;
DELETE FROM work_editions WHERE work_id = 0;   -- or keep as orphans
```
