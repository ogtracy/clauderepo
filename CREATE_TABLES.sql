-- ============================================================================
-- Open Library Database Schema
-- ============================================================================
--
-- This script creates the three main tables for storing Open Library data:
--   1. work_creator   (authors)
--   2. quillent_work  (works)
--   3. work_editions  (editions)
--
-- Run this script before loading any data from the pipeline.
--
-- Usage:
--   psql -d <database_name> -f CREATE_TABLES.sql
--
-- ============================================================================

-- Drop tables if they exist (careful: this will delete all data)
DROP TABLE IF EXISTS work_editions CASCADE;
DROP TABLE IF EXISTS quillent_work CASCADE;
DROP TABLE IF EXISTS work_creator CASCADE;

-- ============================================================================
-- Table: work_creator
-- ============================================================================
-- Stores author/creator information from Open Library authors dump
-- Source: ol_dump_authors_latest.txt.gz
-- ============================================================================

CREATE TABLE work_creator (
    -- Primary key: auto-incrementing ID
    id SERIAL PRIMARY KEY,

    -- Open Library key (e.g., "/authors/OL1A")
    uuid VARCHAR(255) NOT NULL UNIQUE,

    -- Author's display name
    creator_name TEXT,

    -- Personal name (alternative form)
    personal_name TEXT,

    -- Birth date (free-form text, may be year only, full date, or descriptive)
    birth_date VARCHAR(100),

    -- Death date (free-form text, may be year only, full date, or descriptive)
    death_date VARCHAR(100),

    -- Open Library ID (bare suffix, e.g., "OL1A")
    ol_id VARCHAR(50) NOT NULL UNIQUE,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for work_creator
CREATE INDEX idx_work_creator_creator_name ON work_creator(creator_name);
CREATE INDEX idx_work_creator_ol_id ON work_creator(ol_id);

COMMENT ON TABLE work_creator IS 'Authors and creators from Open Library';
COMMENT ON COLUMN work_creator.uuid IS 'Full Open Library key (e.g., /authors/OL1A)';
COMMENT ON COLUMN work_creator.ol_id IS 'Bare Open Library ID (e.g., OL1A)';
COMMENT ON COLUMN work_creator.creator_name IS 'Primary display name for the author';
COMMENT ON COLUMN work_creator.birth_date IS 'Birth date (free-form text)';
COMMENT ON COLUMN work_creator.death_date IS 'Death date (free-form text)';

-- ============================================================================
-- Table: quillent_work
-- ============================================================================
-- Stores work information from Open Library works dump
-- Source: ol_dump_works_latest.txt.gz
-- ============================================================================

CREATE TABLE quillent_work (
    -- Primary key: auto-incrementing ID
    id SERIAL PRIMARY KEY,

    -- Open Library key (e.g., "/works/OL1W")
    uuid VARCHAR(255) NOT NULL UNIQUE,

    -- Work title
    title TEXT NOT NULL,

    -- Subtitle
    sub_title TEXT,

    -- Description/synopsis (may be very long)
    description TEXT,

    -- First publication date (free-form text from OL)
    first_publication_date VARCHAR(100),

    -- First publication date converted to epoch days (NULL if unparseable)
    publication_date_epoch INTEGER,

    -- ISBN-10 (typically empty for works; populated at edition level)
    isbn_ten VARCHAR(20),

    -- ISBN-13 (typically empty for works; populated at edition level)
    isbn_thirteen VARCHAR(20),

    -- Language code (ISO 639, typically empty for works)
    language_code VARCHAR(10),

    -- Number of pages (typically empty for works)
    num_of_pages INTEGER,

    -- Open Library ID (bare suffix, e.g., "OL1W")
    ol_id VARCHAR(50) NOT NULL UNIQUE,

    -- Cover ID (first valid cover from the covers array)
    cover_id INTEGER,

    -- Featured edition title (reserved for future use)
    featured_edition TEXT,

    -- Featured edition OL ID (reserved for future use)
    featured_edition_id VARCHAR(50),

    -- Featured edition foreign key (reserved for future use)
    featured_edition_fk INTEGER,

    -- Series name (reserved for future use)
    series TEXT,

    -- Position in series (reserved for future use)
    position_in_series INTEGER,

    -- Reading ID (reserved for future use)
    reading_id INTEGER,

    -- Penguin Random House ID (reserved for future use)
    prh_id VARCHAR(50),

    -- Flag: has Goodreads data been resolved?
    goodreads_resolved BOOLEAN DEFAULT FALSE,

    -- Flag: has Google Books data been resolved?
    google_resolved BOOLEAN DEFAULT FALSE,

    -- Featured covers (JSON array of cover IDs, e.g., [123, 456])
    featured_covers JSONB,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for quillent_work
CREATE INDEX idx_quillent_work_title ON quillent_work(title);
CREATE INDEX idx_quillent_work_ol_id ON quillent_work(ol_id);
CREATE INDEX idx_quillent_work_isbn_ten ON quillent_work(isbn_ten) WHERE isbn_ten IS NOT NULL;
CREATE INDEX idx_quillent_work_isbn_thirteen ON quillent_work(isbn_thirteen) WHERE isbn_thirteen IS NOT NULL;
CREATE INDEX idx_quillent_work_publication_date_epoch ON quillent_work(publication_date_epoch) WHERE publication_date_epoch IS NOT NULL;

COMMENT ON TABLE quillent_work IS 'Works (book titles/editions group) from Open Library';
COMMENT ON COLUMN quillent_work.uuid IS 'Full Open Library key (e.g., /works/OL1W)';
COMMENT ON COLUMN quillent_work.ol_id IS 'Bare Open Library ID (e.g., OL1W)';
COMMENT ON COLUMN quillent_work.publication_date_epoch IS 'Days since Unix epoch (1970-01-01), best-effort parse';
COMMENT ON COLUMN quillent_work.featured_covers IS 'JSON array of cover IDs';

-- ============================================================================
-- Table: work_editions
-- ============================================================================
-- Stores edition information from Open Library editions dump
-- Source: ol_dump_editions_latest.txt.gz
-- ============================================================================

CREATE TABLE work_editions (
    -- Primary key: auto-incrementing ID
    id SERIAL PRIMARY KEY,

    -- Open Library key (e.g., "/books/OL1M")
    uuid VARCHAR(255) NOT NULL UNIQUE,

    -- Foreign key to quillent_work (resolved after initial load)
    -- Initially loaded as 0, then updated via JOIN on work_ol_id
    work_id INTEGER NOT NULL DEFAULT 0,

    -- ISBN-10
    isbn_ten VARCHAR(20),

    -- ISBN-13
    isbn_thirteen VARCHAR(20),

    -- Publication date (free-form text from OL)
    publication_date VARCHAR(100),

    -- Publication year (4-digit year extracted via regex)
    publication_year INTEGER,

    -- Open Library ID (bare suffix, e.g., "OL1M")
    ol_id VARCHAR(50) NOT NULL UNIQUE,

    -- OL ID of the parent work (bare suffix, e.g., "OL1W")
    -- Used to resolve work_id during Stage 4 load
    work_ol_id VARCHAR(50),

    -- Number of pages
    number_of_pages INTEGER,

    -- Library of Congress Control Number
    lccn VARCHAR(50),

    -- OCLC number
    oclc_number VARCHAR(50),

    -- Publisher (first publisher from the publishers array)
    publisher TEXT,

    -- Series name (reserved for future use)
    series TEXT,

    -- Goodreads ID (reserved for future use)
    goodreads_id VARCHAR(50),

    -- Google Books ID (reserved for future use)
    google_id VARCHAR(50),

    -- Amazon ASIN (reserved for future use)
    asin VARCHAR(20),

    -- Flag: is this a featured edition?
    is_featured BOOLEAN DEFAULT FALSE,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for work_editions (partial set; see DB_LOAD_INSTRUCTIONS.md)
-- NOTE: During bulk load, drop these indexes first, then rebuild after COPY
CREATE INDEX idx_work_editions_work_id ON work_editions(work_id);
CREATE INDEX idx_work_editions_ol_id ON work_editions(ol_id);
CREATE INDEX idx_work_editions_work_ol_id ON work_editions(work_ol_id);
CREATE INDEX idx_work_editions_isbn_ten ON work_editions(isbn_ten) WHERE isbn_ten IS NOT NULL;
CREATE INDEX idx_work_editions_isbn_thirteen ON work_editions(isbn_thirteen) WHERE isbn_thirteen IS NOT NULL;
CREATE INDEX idx_work_editions_publication_year ON work_editions(publication_year) WHERE publication_year IS NOT NULL;

-- Foreign key constraint (add AFTER resolving work_id via UPDATE JOIN)
-- See DB_LOAD_INSTRUCTIONS.md Stage 4 step 8
-- ALTER TABLE work_editions ADD CONSTRAINT fk_work_editions_work
--     FOREIGN KEY (work_id) REFERENCES quillent_work(id) ON DELETE CASCADE;

COMMENT ON TABLE work_editions IS 'Editions (specific published versions) from Open Library';
COMMENT ON COLUMN work_editions.uuid IS 'Full Open Library key (e.g., /books/OL1M)';
COMMENT ON COLUMN work_editions.ol_id IS 'Bare Open Library ID (e.g., OL1M)';
COMMENT ON COLUMN work_editions.work_id IS 'FK to quillent_work.id (initially 0, resolved post-load)';
COMMENT ON COLUMN work_editions.work_ol_id IS 'Parent work OL ID for FK resolution (e.g., OL1W)';
COMMENT ON COLUMN work_editions.publication_year IS '4-digit year extracted from publication_date';

-- ============================================================================
-- Post-creation notes
-- ============================================================================
--
-- 1. The foreign key constraint on work_editions.work_id is commented out.
--    During bulk load, work_id starts as 0 (sentinel value). The FK is added
--    AFTER running the UPDATE JOIN to resolve work_id. See DB_LOAD_INSTRUCTIONS.md.
--
-- 2. Many indexes are created here for convenience. During bulk load (Stage 4),
--    you should DROP all secondary indexes before COPY, then rebuild them after.
--    See DB_LOAD_INSTRUCTIONS.md for the full sequence.
--
-- 3. The created_at/updated_at timestamps are auto-populated on insert.
--    You may want to add triggers to auto-update updated_at on row modification.
--
-- 4. All TEXT columns allow NULL by default except where marked NOT NULL.
--    The pipeline may write empty strings or NULL depending on the transform logic.
--
-- 5. Disk space: Expect ~200-300 GB for the full Open Library dataset.
--    Ensure your PostgreSQL data directory has sufficient space.
--
-- ============================================================================

-- Optional: Add update trigger for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_work_creator_updated_at BEFORE UPDATE ON work_creator
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_quillent_work_updated_at BEFORE UPDATE ON quillent_work
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_work_editions_updated_at BEFORE UPDATE ON work_editions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Verification queries
-- ============================================================================
-- Run these after loading data to verify the tables:
--
-- Count rows in each table:
--   SELECT COUNT(*) FROM work_creator;
--   SELECT COUNT(*) FROM quillent_work;
--   SELECT COUNT(*) FROM work_editions;
--
-- Check for unresolved work_id (should be 0 after load completes):
--   SELECT COUNT(*) FROM work_editions WHERE work_id = 0;
--
-- Sample data:
--   SELECT * FROM work_creator LIMIT 10;
--   SELECT * FROM quillent_work LIMIT 10;
--   SELECT * FROM work_editions LIMIT 10;
--
-- Table sizes:
--   SELECT
--       schemaname,
--       tablename,
--       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
--   FROM pg_tables
--   WHERE tablename IN ('work_creator', 'quillent_work', 'work_editions')
--   ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
--
-- ============================================================================
