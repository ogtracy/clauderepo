# Open Library → PostgreSQL Load Instructions

This document covers the full end-to-end process for loading Open Library data
into the three target tables.

## Tables and dependencies

```
work_creator          (no FK dependencies)
quillent_work         (no FK dependencies)
work_editions         (work_id FK → quillent_work.id — resolved post-load)
```

---

## Step 0 — Generate the CSV files

Run the three converter scripts in any order (they are independent):

```bash
# Each takes several hours on the full dump; --test flag for a quick trial
python3 openlibrary_authors_to_csv.py      # → authors_csv/
python3 openlibrary_works_to_csv.py        # → works_csv/
python3 openlibrary_editions_to_csv.py     # → editions_csv/
```

Then run the three transform scripts to produce DB-ready CSV:

```bash
python3 transform_authors_to_work_creator.py     # → work_creator_csv/
python3 transform_works_to_quillent_work.py      # → quillent_work_csv/
python3 transform_editions_to_work_editions.py   # → work_editions_csv/
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

## Step 2 — Pre-load: disable the work_editions FK constraint

`work_editions.work_id` is a NOT NULL FK to `quillent_work.id`. The CSV files
contain `work_id = 0` as a sentinel value (the real integer ID is only known
after `quillent_work` is loaded). Disable the constraint before loading and
re-enable it after the FK is resolved.

```sql
ALTER TABLE work_editions
    DISABLE TRIGGER ALL;          -- suppresses FK trigger checks during COPY

-- If the constraint is defined as NOT DEFERRABLE you may need to drop and
-- re-add it instead:
--
-- ALTER TABLE work_editions DROP CONSTRAINT fk_work_editions_work_id;
```

> **Alternative without ALTER TABLE** — connect with a superuser and run:
> ```sql
> SET session_replication_role = replica;
> -- (run all COPY commands in this session)
> SET session_replication_role = DEFAULT;
> ```
> This suppresses all FK and trigger checks for the session without touching
> the table definition.

---

## Step 3 — Load work_creator

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

## Step 4 — Load quillent_work

No FK dependencies. Load second (must precede work_editions so the FK
resolution UPDATE in Step 7 has rows to join against).

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

## Step 5 — Load work_editions

`work_id` is loaded as 0 (sentinel) and resolved in Step 7.

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
```

---

## Step 6 — Create the index needed for FK resolution

Before running the UPDATE in Step 7, create an index on `quillent_work.ol_id`
so the join does not perform a sequential scan across tens of millions of rows.

```sql
CREATE INDEX idx_quillent_work_ol_id ON quillent_work (ol_id);
```

---

## Step 7 — Resolve work_editions.work_id FK

```sql
UPDATE work_editions we
SET    work_id = qw.id
FROM   quillent_work qw
WHERE  qw.ol_id = we.work_ol_id;
```

This may take several minutes on the full dataset. Run it inside a transaction
if you want to be able to roll back:

```sql
BEGIN;
UPDATE work_editions we
SET    work_id = qw.id
FROM   quillent_work qw
WHERE  qw.ol_id = we.work_ol_id;
-- Check before committing:
SELECT COUNT(*) FROM work_editions WHERE work_id = 0;
COMMIT;
```

Check how many editions had no matching work (OL editions that reference a
work key not present in the works dump — expected to be a small minority):

```sql
SELECT COUNT(*) FROM work_editions WHERE work_id = 0;
```

Decide whether to delete or keep these orphan rows:

```sql
-- Option A: delete orphans
DELETE FROM work_editions WHERE work_id = 0;

-- Option B: keep them (requires relaxing the NOT NULL constraint temporarily
--            or accepting that work_id = 0 is a known sentinel)
```

---

## Step 8 — Re-enable the FK constraint

```sql
ALTER TABLE work_editions
    ENABLE TRIGGER ALL;

-- If you dropped the constraint in Step 2, recreate it:
--
-- ALTER TABLE work_editions
--     ADD CONSTRAINT fk_work_editions_work_id
--     FOREIGN KEY (work_id) REFERENCES quillent_work (id);
```

If using `session_replication_role`, nothing to do — it was per-session.

---

## Step 9 — Rebuild all secondary indexes

Create indexes after the data is fully loaded. Building on a populated table
uses a single sequential scan and is much faster than incremental updates.

```sql
-- work_creator
CREATE INDEX idx_work_creator_ol_id
    ON work_creator (ol_id);
CREATE INDEX idx_work_creator_creator_name
    ON work_creator (creator_name);

-- quillent_work (idx_quillent_work_ol_id already created in Step 6)
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

## Step 10 — Analyze

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
| 0 | Generate CSVs |
| 1 | Drop secondary indexes |
| 2 | Disable work_editions FK / triggers |
| 3 | COPY work_creator |
| 4 | COPY quillent_work |
| 5 | COPY work_editions (work_id = 0 sentinel) |
| 6 | Create idx_quillent_work_ol_id |
| 7 | UPDATE work_editions SET work_id (FK resolution) |
| 8 | Re-enable FK constraint |
| 9 | Rebuild all secondary indexes |
| 10 | ANALYZE |

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
