# Open Library → PostgreSQL Load Instructions

This document covers the full end-to-end process for loading Open Library data
into the three target tables.

## Tables and dependencies

```
work_creator          (no FK dependencies)
quillent_work         (no FK dependencies)
work_editions         (work_id FK → quillent_work.id — resolved during transform)
```

**IMPORTANT:** Editions are transformed AFTER works are loaded. The editions
transform script queries the database to resolve work_id during transformation,
eliminating the need for post-load UPDATE JOIN.

---

## Step 0 — Generate the CSV files

### Phase 1: Parse dumps and transform authors/works

Run the three parser scripts in parallel (they are independent):

```bash
# Each takes several hours on the full dump; --test flag for a quick trial
python3 openlibrary_authors_to_csv.py  > parse_authors.log  2>&1 &
python3 openlibrary_works_to_csv.py    > parse_works.log    2>&1 &
python3 openlibrary_editions_to_csv.py > parse_editions.log 2>&1 &
wait
```

Then transform authors and works (editions come later):

```bash
python3 transform_authors_to_work_creator.py  # → work_creator_csv/
python3 transform_works_to_quillent_work.py   # → quillent_work_csv/
```

### Phase 2: Transform editions (after loading works)

The editions transform script requires works to be loaded first:

```bash
# Run AFTER Step 4 (loading quillent_work)
python3 transform_editions_to_work_editions.py --db <database> \
    [--host <host>] [--port <port>] [--user <user>]
# → work_editions_csv/ with work_id already resolved
```

---

## Step 1 — Pre-load: drop secondary indexes

Dropping indexes before bulk-loading and rebuilding them afterward is
significantly faster than maintaining them row-by-row during COPY.
Keep only primary keys and unique constraints in place so duplicates
are still rejected during load.

```sql
-- work_creator
DROP INDEX IF EXISTS idx_work_creator_ol_id;
DROP INDEX IF EXISTS idx_work_creator_creator_name;

-- quillent_work
DROP INDEX IF EXISTS idx_quillent_work_ol_id;
DROP INDEX IF EXISTS idx_quillent_work_title;
DROP INDEX IF EXISTS idx_quillent_work_isbn_ten;
DROP INDEX IF EXISTS idx_quillent_work_isbn_thirteen;

-- work_editions
DROP INDEX IF EXISTS idx_work_editions_work_id;
DROP INDEX IF EXISTS idx_work_editions_work_ol_id;
DROP INDEX IF EXISTS idx_work_editions_ol_id;
DROP INDEX IF EXISTS idx_work_editions_isbn_ten;
DROP INDEX IF EXISTS idx_work_editions_isbn_thirteen;
DROP INDEX IF EXISTS idx_work_editions_publisher;
```

---

## Step 2 — Load work_creator

No FK dependencies. Load first.

```bash
for f in work_creator_csv/work_creator_*.csv; do
    psql -d <db> -c "\copy work_creator \
        (uuid, creator_name, personal_name, birth_date, death_date, ol_id) \
        FROM '$f' CSV HEADER;"
done
```

Verify:
```sql
SELECT COUNT(*) FROM work_creator;
-- Expected: ~9 million rows
```

---

## Step 3 — Load quillent_work

No FK dependencies. Load second (must precede work_editions transform so the
editions transform script can query for work_id mappings).

```bash
for f in quillent_work_csv/quillent_work_*.csv; do
    psql -d <db> -c "\copy quillent_work \
        (uuid, title, sub_title, description, first_publication_date, \
         publication_date_epoch, isbn_ten, isbn_thirteen, language_code, \
         num_of_pages, ol_id, cover_id, featured_edition, \
         featured_edition_id, featured_edition_fk, series, \
         position_in_series, reading_id, prh_id, goodreads_resolved, \
         google_resolved, featured_covers) \
        FROM '$f' CSV HEADER;"
done
```

Verify:
```sql
SELECT COUNT(*) FROM quillent_work;
-- Expected: ~30–35 million rows
```

---

## Step 4 — Transform editions (with work_id resolution)

**NOW** run the editions transform script, which queries the database to resolve
work_id during transformation:

```bash
python3 transform_editions_to_work_editions.py --db <database> \
    [--host <host>] [--port <port>] [--user <user>]
# → work_editions_csv/ with work_id already resolved
```

The script will:
1. Query `SELECT id, ol_id FROM quillent_work` to build an in-memory mapping
2. Transform each edition, setting `work_id` from the mapping
3. Write `work_id=0` for editions whose work is not in the database
4. Report how many editions have unresolved work_id

---

## Step 5 — Load work_editions

`work_id` is already resolved — no UPDATE JOIN needed!

```bash
for f in work_editions_csv/work_editions_*.csv; do
    psql -d <db> -c "\copy work_editions \
        (uuid, work_id, isbn_ten, isbn_thirteen, publication_date, \
         publication_year, ol_id, work_ol_id, number_of_pages, lccn, \
         oclc_number, publisher, series, goodreads_id, google_id, \
         asin, is_featured) \
        FROM '$f' CSV HEADER;"
done
```

Verify:
```sql
SELECT COUNT(*) FROM work_editions;
-- Expected: ~50–60 million rows

-- Check for unresolved work_id (should match transform script output)
SELECT COUNT(*) FROM work_editions WHERE work_id = 0;
```

If there are orphan editions (work_id=0), decide whether to keep or delete:

```sql
-- Option A: delete orphans (FK constraint will reject them anyway)
DELETE FROM work_editions WHERE work_id = 0;

-- Option B: keep them for investigation
-- (requires NOT NULL constraint to allow 0, or make work_id nullable)
```

---

## Step 6 — Rebuild all secondary indexes

Create indexes after the data is fully loaded. Building on a populated table
uses a single sequential scan and is much faster than incremental updates.

```sql
-- work_creator
CREATE INDEX idx_work_creator_ol_id
    ON work_creator (ol_id);
CREATE INDEX idx_work_creator_creator_name
    ON work_creator (creator_name);

-- quillent_work
CREATE INDEX idx_quillent_work_ol_id
    ON quillent_work (ol_id);
CREATE INDEX idx_quillent_work_title
    ON quillent_work (title);
CREATE INDEX idx_quillent_work_isbn_ten
    ON quillent_work (isbn_ten)
    WHERE isbn_ten IS NOT NULL AND isbn_ten <> '';
CREATE INDEX idx_quillent_work_isbn_thirteen
    ON quillent_work (isbn_thirteen)
    WHERE isbn_thirteen IS NOT NULL AND isbn_thirteen <> '';

-- work_editions
CREATE INDEX idx_work_editions_work_id
    ON work_editions (work_id);
CREATE INDEX idx_work_editions_work_ol_id
    ON work_editions (work_ol_id);
CREATE INDEX idx_work_editions_ol_id
    ON work_editions (ol_id);
CREATE INDEX idx_work_editions_isbn_ten
    ON work_editions (isbn_ten)
    WHERE isbn_ten IS NOT NULL AND isbn_ten <> '';
CREATE INDEX idx_work_editions_isbn_thirteen
    ON work_editions (isbn_thirteen)
    WHERE isbn_thirteen IS NOT NULL AND isbn_thirteen <> '';
CREATE INDEX idx_work_editions_publisher
    ON work_editions (publisher)
    WHERE publisher IS NOT NULL AND publisher <> '';
```

> The partial indexes (`WHERE column <> ''`) skip the large number of empty
> strings and keep the index compact and fast for real lookups.

---

## Step 7 — Analyze

Update the query planner statistics now that the data and indexes are in place:

```sql
ANALYZE work_creator;
ANALYZE quillent_work;
ANALYZE work_editions;
```

---

## Summary of load order

| Step | Action |
|------|--------|
| 0a | Parse dumps → CSV (authors, works, editions) |
| 0b | Transform authors and works → DB-ready CSV |
| 1 | Drop secondary indexes |
| 2 | COPY work_creator |
| 3 | COPY quillent_work |
| 4 | Transform editions (queries DB for work_id mapping) |
| 5 | COPY work_editions (work_id already resolved) |
| 6 | Rebuild all secondary indexes |
| 7 | ANALYZE |

**Key difference from traditional workflows:** Editions are transformed AFTER
works are loaded, eliminating the need for post-load UPDATE JOIN. This saves
hours on large datasets.

---

## Fields left blank — expected values

Several columns in `quillent_work` and `work_editions` are not present in the
Open Library data and will be empty after load. They are intended to be
populated from other sources (Penguin Random House feed, Goodreads, Google
Books, etc.):

| Table | Column | Source |
|-------|--------|--------|
| quillent_work | isbn_ten, isbn_thirteen | Editions data (see note below) |
| quillent_work | language_code, num_of_pages | Editions data |
| quillent_work | featured_edition, featured_edition_id, featured_edition_fk | Set after choosing canonical edition |
| quillent_work | series, position_in_series | PRH or Goodreads feed |
| quillent_work | prh_id, reading_id | PRH feed |
| quillent_work | goodreads_resolved, google_resolved | Set after enrichment runs |
| work_editions | series | PRH or Goodreads feed |
| work_editions | goodreads_id | Goodreads enrichment |
| work_editions | google_id | Google Books enrichment |
| work_editions | asin | Amazon feed |

> **Populating quillent_work ISBN / language / pages from editions**: once
> `work_editions` is loaded you can back-fill a representative value per work
> with a query such as:
>
> ```sql
> UPDATE quillent_work qw
> SET    isbn_thirteen = sub.isbn_thirteen
> FROM (
>     SELECT DISTINCT ON (work_id)
>            work_id, isbn_thirteen
>     FROM   work_editions
>     WHERE  isbn_thirteen <> ''
>     ORDER  BY work_id, id
> ) sub
> WHERE qw.id = sub.work_id
>   AND (qw.isbn_thirteen IS NULL OR qw.isbn_thirteen = '');
> ```
