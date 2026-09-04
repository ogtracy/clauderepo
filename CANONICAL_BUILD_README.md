# Canonical catalog builder

`canonical_catalog.py` uses DuckDB as an embedded, disk-backed engine to turn
the lossless transformed CSVs into a canonical catalog. PostgreSQL is not
required for this stage.

Edition ownership is resolved from the lossless `edition_works.csv` relation.
The canonical path therefore avoids constructing the old full-catalog
`ol_id -> numeric id` Python dictionary.

## Small local test

Install the pinned dependencies in an isolated local directory:

```bash
python3 -m pip install --target .catalog-deps -r requirements.txt
```

Run the complete bundled fixture:

```bash
PYTHONPATH=.catalog-deps python3 run_small_catalog_pipeline.py \
  --limit 5 \
  --output-dir canonical_sample_run
```

The output directory must be empty. Use a new name when repeating a run.

For real dump subsets:

```bash
PYTHONPATH=.catalog-deps python3 run_small_catalog_pipeline.py \
  --authors /data/ol_dump_authors_latest.txt.gz \
  --works /data/ol_dump_works_latest.txt.gz \
  --editions /data/ol_dump_editions_latest.txt.gz \
  --limit 10000 \
  --output-dir canonical_real_10000
```

Because each dump has a different ordering, an arbitrary first-N slice may
contain editions whose referenced works or authors are outside the slice. For
a representative, relationship-connected sample, select works first and scan
the other dumps for their editions and authors:

```bash
PYTHONPATH=.catalog-deps python3 sample_connected_catalog.py \
  --authors /data/ol_dump_authors_latest.txt.gz \
  --works /data/ol_dump_works_latest.txt.gz \
  --editions /data/ol_dump_editions_latest.txt.gz \
  --work-count 10000 \
  --output-dir connected_10000

PYTHONPATH=.catalog-deps python3 run_catalog_pipeline.py \
  --authors connected_10000/authors.txt.gz \
  --works connected_10000/works.txt.gz \
  --editions connected_10000/editions.txt.gz \
  --output-dir connected_10000_build
```

Reservoir sampling is the default, so seed works are distributed throughout
the work dump rather than biased toward its beginning. `sample_manifest.json`
reports missing authors and works without retained editions.

## Full build

Run the resumable pipeline directly against all three dumps:

```bash
PYTHONPATH=.catalog-deps python3 run_catalog_pipeline.py \
  --authors /data/ol_dump_authors_latest.txt.gz \
  --works /data/ol_dump_works_latest.txt.gz \
  --editions /data/ol_dump_editions_latest.txt.gz \
  --output-dir full_catalog_build
```

Each completed stage receives a checkpoint in `.stages/`. Re-running the same
command skips completed parsing and transformation stages.

## Automatic merge rules

Works are automatically merged only when:

- editions attached to the works share a checksum-valid ISBN, and that ISBN is
  not attached to more than five distinct works; or
- normalized title, canonical author set, and parsed publication year all
  match exactly.

Authors are automatically merged only when:

- they share the same Wikipedia URL;
- they share a website URL and normalized name; or
- they have the same normalized name and are attached to the same canonical
  work after work merging.

Name-only author matches are never merged. They are written as grouped review
candidates to avoid an unbounded pairwise expansion for common names.

Every automatic decision is retained in `work_merge_audit.csv` or
`author_merge_audit.csv`. Ambiguous records remain distinct and are written to
the corresponding candidates file.

## Derived data

After merging, the builder:

- rewrites work-author relationships to numeric canonical IDs;
- selects one featured edition per work, preferring valid ISBNs and then the
  latest valid publication year;
- normalizes and deduplicates tags without splitting source subjects on
  punctuation;
- recalculates tag prevalence after work merging;
- creates weighted author tag profiles;
- creates initial materialized similar-author rows with shared-tag evidence;
- stores profile hashes for later incremental drift detection; and
- runs referential, duplicate, featured-edition, profile, and similarity
  validation checks.

## Canonical outputs

The `canonical/` directory contains authors, works, editions, tags, numeric
relationship tables, external-identifier aliases, lossless author/edition
metadata, merge audits and candidates, author profiles, initial similar
authors, `build_summary.json`, and `validation.json`.

## PostgreSQL restore

The loader expects an empty database. It refuses to run if a canonical file is
missing or `validation.json` contains a failure. It creates heap tables, uses
client-side `COPY`, and builds constraints and indexes afterward:

```bash
./load_canonical_catalog.sh "$DATABASE_URL" \
  full_catalog_build/canonical
```

The schema deliberately follows the numeric internal-ID policy. The backend's
remaining author UUID mappings must be migrated before deploying it against
this replacement database.
