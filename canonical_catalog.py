#!/usr/bin/env python3
"""Build PostgreSQL-loadable canonical catalog CSVs with DuckDB.

The input is the lossless output of this repository's transform scripts. The
builder performs only evidence-backed automatic merges and writes every merge
decision to an audit CSV. Ambiguous candidates remain separate.
"""

import argparse
import json
import re
import unicodedata
from pathlib import Path

import duckdb
from duckdb.sqltypes import BIGINT, VARCHAR

from process_tags import clean_tag


def normalized_words(value: str) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"[\w]+", value, flags=re.UNICODE))


def normalized_url(value: str) -> str:
    if not value:
        return ""
    return value.strip().casefold().rstrip("/")


def normalized_isbn(value: str) -> str:
    if not value:
        return ""
    candidate = re.sub(r"[^0-9Xx]", "", value).upper()
    if len(candidate) == 10:
        total = sum((10 - index) * (10 if char == "X" else int(char))
                    for index, char in enumerate(candidate))
        if total % 11 != 0:
            return ""
        stem = "978" + candidate[:9]
        checksum_total = sum(int(char) * (1 if index % 2 == 0 else 3)
                             for index, char in enumerate(stem))
        return stem + str((10 - checksum_total % 10) % 10)
    if len(candidate) == 13 and candidate.isdigit():
        total = sum(int(char) * (1 if index % 2 == 0 else 3)
                    for index, char in enumerate(candidate[:-1]))
        check = (10 - total % 10) % 10
        return candidate if check == int(candidate[-1]) else ""
    return ""


def extracted_year(value: str):
    if not value:
        return None
    match = re.search(r"(?<!\d)(1[4-9]\d{2}|20\d{2})(?!\d)", value)
    return int(match.group(1)) if match else None


def sql_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def require_files(pattern: Path):
    import glob
    matches = glob.glob(str(pattern))
    if not matches:
        raise FileNotFoundError(f"No files match {pattern}")
    return matches


def load_csv(connection, table: str, pattern: Path):
    require_files(pattern)
    connection.execute(f"""
        CREATE OR REPLACE TABLE {table} AS
        SELECT * FROM read_csv(
            '{sql_path(pattern)}', header = true, all_varchar = true,
            union_by_name = true, filename = true
        )
    """)


def connected_components(connection, nodes_sql: str, edges_table: str,
                         output_table: str):
    """Resolve undirected merge edges without loading the graph into RAM."""
    connection.execute(f"""
        CREATE OR REPLACE TEMP TABLE component_label AS
        SELECT node, node AS label FROM ({nodes_sql}) nodes
    """)
    iterations = 0
    while True:
        connection.execute(f"""
            CREATE OR REPLACE TEMP TABLE next_component_label AS
            WITH neighbors AS (
                SELECT node_a AS node, node_b AS neighbor FROM {edges_table}
                UNION ALL
                SELECT node_b AS node, node_a AS neighbor FROM {edges_table}
            ), candidate AS (
                SELECT current.node,
                       min(neighbor_label.label) AS neighbor_label
                FROM component_label current
                LEFT JOIN neighbors ON neighbors.node = current.node
                LEFT JOIN component_label neighbor_label
                       ON neighbor_label.node = neighbors.neighbor
                GROUP BY current.node
            )
            SELECT current.node,
                   least(current.label,
                         coalesce(candidate.neighbor_label, current.label)) AS label
            FROM component_label current
            JOIN candidate USING (node)
        """)
        changed = connection.execute("""
            SELECT count(*)
            FROM component_label old
            JOIN next_component_label new USING (node)
            WHERE old.label <> new.label
        """).fetchone()[0]
        connection.execute("DROP TABLE component_label")
        connection.execute("ALTER TABLE next_component_label RENAME TO component_label")
        iterations += 1
        if changed == 0:
            break
        if iterations > 100:
            raise RuntimeError(f"Merge graph did not converge for {edges_table}")
    connection.execute(f"""
        CREATE OR REPLACE TABLE {output_table} AS
        SELECT node, label AS canonical_source_key FROM component_label
    """)


class CatalogBuilder:
    def __init__(self, input_dir: Path, output_dir: Path, database: Path,
                 similar_limit: int = 20, minimum_shared_tags: int = 2,
                 prh_data_dir: Path | None = None):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.database = database
        self.similar_limit = similar_limit
        self.minimum_shared_tags = minimum_shared_tags
        self.prh_data_dir = self._normalized_prh_dir(prh_data_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        self.db = duckdb.connect(str(database))
        self.db.create_function("normalize_words", normalized_words, [VARCHAR], VARCHAR)
        self.db.create_function("normalize_url", normalized_url, [VARCHAR], VARCHAR)
        self.db.create_function("normalize_isbn", normalized_isbn, [VARCHAR], VARCHAR)
        self.db.create_function("extract_year", extracted_year, [VARCHAR], BIGINT)
        self.db.create_function("normalize_tag", clean_tag, [VARCHAR], VARCHAR)

    @staticmethod
    def _normalized_prh_dir(path: Path | None) -> Path | None:
        if path is None:
            return None
        path = path.resolve()
        normalized = path / "normalized"
        return normalized if normalized.is_dir() else path

    def load_optional_jsonl(self, table: str, filename: str, empty_sql: str):
        path = self.prh_data_dir / filename if self.prh_data_dir else None
        if path and path.is_file() and path.stat().st_size:
            self.db.execute(f"""
                CREATE OR REPLACE TABLE {table} AS
                SELECT * FROM read_json_auto(
                    '{sql_path(path)}', format = 'newline_delimited',
                    union_by_name = true, maximum_object_size = 16777216
                )
            """)
        else:
            self.db.execute(f"CREATE OR REPLACE TABLE {table} AS {empty_sql}")

    def close(self):
        self.db.close()

    def load(self):
        load_csv(self.db, "raw_author", self.input_dir / "work_creator_csv" / "work_creator_*.csv")
        load_csv(self.db, "raw_author_alternate_name", self.input_dir / "work_creator_csv" / "author_alternate_names.csv")
        load_csv(self.db, "raw_author_link", self.input_dir / "work_creator_csv" / "author_external_links.csv")
        load_csv(self.db, "raw_work", self.input_dir / "quillent_work_csv" / "quillent_work_*.csv")
        load_csv(self.db, "raw_work_author", self.input_dir / "quillent_work_csv" / "work_authors.csv")
        load_csv(self.db, "raw_work_subject", self.input_dir / "quillent_work_csv" / "work_subjects.csv")
        load_csv(self.db, "raw_work_cover", self.input_dir / "quillent_work_csv" / "work_covers.csv")
        load_csv(self.db, "raw_edition", self.input_dir / "work_editions_csv" / "work_editions_*.csv")
        load_csv(self.db, "raw_edition_work", self.input_dir / "work_editions_csv" / "edition_works.csv")
        load_csv(self.db, "raw_edition_author", self.input_dir / "work_editions_csv" / "edition_authors.csv")
        load_csv(self.db, "raw_edition_identifier", self.input_dir / "work_editions_csv" / "edition_identifiers.csv")
        load_csv(self.db, "raw_edition_publisher", self.input_dir / "work_editions_csv" / "edition_publishers.csv")
        load_csv(self.db, "raw_edition_cover", self.input_dir / "work_editions_csv" / "edition_covers.csv")
        load_csv(self.db, "raw_edition_language", self.input_dir / "work_editions_csv" / "edition_languages.csv")

        self.db.execute("""
            CREATE OR REPLACE TABLE source_author AS
            SELECT uuid AS source_key, creator_name, personal_name,
                   birth_date, death_date, ol_id,
                   normalize_words(creator_name) AS normalized_name,
                   'openlibrary'::varchar AS source_provider
            FROM raw_author WHERE coalesce(uuid, '') <> '';

            CREATE OR REPLACE TABLE source_work AS
            SELECT try_cast(id AS bigint) AS source_id, uuid AS source_key,
                   title, sub_title, description, first_publication_date,
                   try_cast(publication_date_epoch AS bigint) AS publication_date_epoch,
                   isbn_ten, isbn_thirteen, language_code,
                   try_cast(num_of_pages AS integer) AS num_of_pages,
                   ol_id, try_cast(cover_id AS bigint) AS cover_id,
                   featured_covers, series, position_in_series, reading_id,
                   prh_id, try_cast(goodreads_resolved AS boolean) AS goodreads_resolved,
                   try_cast(google_resolved AS boolean) AS google_resolved,
                   normalize_words(title) AS normalized_title,
                   extract_year(first_publication_date) AS publication_year,
                   'openlibrary'::varchar AS source_provider
            FROM raw_work WHERE coalesce(uuid, '') <> '';

            CREATE OR REPLACE TABLE source_work_author AS
            SELECT work_external_id AS work_key,
                   author_external_id AS author_key
            FROM raw_work_author
            WHERE coalesce(work_external_id, '') <> ''
              AND coalesce(author_external_id, '') <> '';

            CREATE OR REPLACE TABLE source_edition_work AS
            SELECT edition_external_id AS edition_key,
                   work_external_id AS work_key,
                   try_cast(position AS integer) AS position
            FROM raw_edition_work;

            CREATE OR REPLACE TABLE source_edition_identifier AS
            SELECT edition_external_id AS edition_key,
                   lower(identifier_type) AS identifier_type,
                   identifier AS source_identifier,
                   normalize_isbn(identifier) AS normalized_identifier,
                   try_cast(position AS integer) AS position
            FROM raw_edition_identifier;

            CREATE OR REPLACE TABLE source_work_subject AS
            SELECT work_external_id AS work_key, subject,
                   'openlibrary'::varchar AS provider,
                   'subject'::varchar AS tag_source
            FROM raw_work_subject;

            CREATE OR REPLACE TABLE source_edition_author AS
            SELECT edition_external_id AS edition_key,
                   author_external_id AS author_key
            FROM raw_edition_author;
        """)
        self.load_prh()

    def load_prh(self):
        self.load_optional_jsonl("raw_prh_author", "authors.jsonl", """
            SELECT NULL::bigint prh_author_id, NULL::varchar display,
                   NULL::varchar prh_url
            WHERE false
        """)
        self.load_optional_jsonl("raw_prh_author_profile", "author_profiles.jsonl", """
            SELECT NULL::bigint prh_author_id, NULL::varchar biography_html,
                   NULL::varchar photo_url, NULL::varchar photo_credit,
                   NULL::varchar photo_date, NULL::varchar prh_url,
                   NULL::bigint reported_work_count, NULL::json related_links
            WHERE false
        """)
        self.load_optional_jsonl("raw_prh_work", "works.jsonl", """
            SELECT NULL::bigint prh_work_id, NULL::varchar title,
                   NULL::varchar subtitle, NULL::varchar prh_display_title,
                   NULL::varchar first_onsale, NULL::varchar AS "language",
                   NULL::varchar prh_url, NULL::varchar about_the_book_html,
                   NULL::varchar keynote_html, NULL::varchar positioning_html,
                   NULL::json awards, NULL::varchar frontlistiest_isbn,
                   NULL::json isbn_counts WHERE false
        """)
        self.load_optional_jsonl("raw_prh_edition", "editions.jsonl", """
            SELECT NULL::bigint prh_work_id, NULL::varchar isbn,
                   NULL::varchar isbn10, NULL::varchar title,
                   NULL::varchar subtitle, NULL::varchar publication_date,
                   NULL::bigint pages, NULL::varchar trim_size,
                   NULL::varchar format_family, NULL::varchar format_code,
                   NULL::varchar format_name, NULL::varchar AS "version",
                   NULL::varchar AS "language", NULL::varchar imprint_code,
                   NULL::varchar imprint_name, NULL::varchar asin,
                   NULL::varchar cover_url, NULL::varchar prh_url,
                   NULL::varchar series_code, NULL::varchar series_name,
                   NULL::varchar series_position, NULL::varchar[] subjects,
                   NULL::varchar custom_subject_category,
                   NULL::varchar sales_restriction, NULL::json raw_flags
            WHERE false
        """)
        self.load_optional_jsonl("raw_prh_work_contributor", "work_contributors.jsonl", """
            SELECT NULL::bigint prh_work_id, NULL::bigint prh_author_id,
                   NULL::varchar display, NULL::varchar role_code,
                   NULL::varchar role_description, NULL::boolean primary_flag,
                   NULL::varchar[] observed_isbns WHERE false
        """)
        self.load_optional_jsonl("raw_prh_edition_contributor", "edition_contributors.jsonl", """
            SELECT NULL::bigint prh_work_id, NULL::varchar isbn,
                   NULL::bigint prh_author_id, NULL::varchar display,
                   NULL::varchar role_code, NULL::varchar role_description,
                   NULL::boolean primary_flag, NULL::integer ordinal WHERE false
        """)
        self.load_optional_jsonl("raw_prh_series", "series.jsonl", """
            SELECT NULL::varchar prh_series_code, NULL::varchar AS "name",
                   NULL::varchar description_html, NULL::bigint series_count,
                   NULL::varchar series_date, NULL::boolean is_numbered,
                   NULL::boolean is_kids, NULL::varchar prh_url WHERE false
        """)
        self.load_optional_jsonl("raw_prh_series_hint", "series_hints.jsonl", """
            SELECT NULL::bigint prh_work_id, NULL::varchar prh_series_code,
                   NULL::varchar series_name, NULL::varchar AS "position",
                   NULL::varchar description_html, NULL::varchar prh_url
            WHERE false
        """)
        self.load_optional_jsonl("raw_prh_work_series", "work_series.jsonl", """
            SELECT NULL::varchar prh_series_code, NULL::bigint prh_work_id,
                   NULL::varchar AS "position", NULL::varchar title,
                   NULL::varchar first_onsale WHERE false
        """)
        self.load_optional_jsonl("raw_prh_keyword", "keywords.jsonl", """
            SELECT NULL::bigint prh_work_id, NULL::varchar isbn,
                   NULL::varchar[] candidates WHERE false
        """)
        if self.prh_data_dir is None:
            return
        for required in ("authors.jsonl", "works.jsonl", "editions.jsonl",
                         "work_contributors.jsonl"):
            if not (self.prh_data_dir / required).is_file():
                raise FileNotFoundError(
                    f"Missing required normalized PRH file: {self.prh_data_dir / required}"
                )
        self.integrate_prh_sources()

    def integrate_prh_sources(self):
        self.db.execute("""
            INSERT INTO source_author
            SELECT DISTINCT 'prh:author:' || prh_author_id, display, display,
                   NULL, NULL, NULL, normalize_words(display), 'prh'
            FROM raw_prh_author
            WHERE prh_author_id IS NOT NULL AND coalesce(display, '') <> '';

            INSERT INTO source_author
            SELECT DISTINCT 'prh:author:' || contributor.prh_author_id,
                   contributor.display, contributor.display, NULL, NULL, NULL,
                   normalize_words(contributor.display), 'prh'
            FROM raw_prh_work_contributor contributor
            WHERE contributor.prh_author_id IS NOT NULL
              AND coalesce(contributor.display, '') <> ''
              AND NOT EXISTS (
                  SELECT 1 FROM source_author author
                  WHERE author.source_key = 'prh:author:' || contributor.prh_author_id
              );

            INSERT INTO source_work
            SELECT DISTINCT prh_work_id, 'prh:work:' || prh_work_id,
                   title, subtitle, about_the_book_html, first_onsale::varchar,
                   date_diff('day', DATE '1970-01-01', try_cast(first_onsale AS date)),
                   NULL, NULL, language, NULL, NULL, NULL, NULL,
                   NULL, NULL, NULL, prh_work_id::varchar, false, false,
                   normalize_words(title), extract_year(first_onsale::varchar), 'prh'
            FROM raw_prh_work
            WHERE prh_work_id IS NOT NULL AND coalesce(title, '') <> '';

            INSERT INTO source_edition_work
            SELECT DISTINCT 'prh:edition:' || isbn,
                   'prh:work:' || prh_work_id, 1
            FROM raw_prh_edition
            WHERE prh_work_id IS NOT NULL AND normalize_isbn(isbn) <> '';

            INSERT INTO source_edition_identifier
            SELECT DISTINCT 'prh:edition:' || isbn, 'isbn13', isbn,
                   normalize_isbn(isbn), 1
            FROM raw_prh_edition WHERE normalize_isbn(isbn) <> '';

            INSERT INTO source_edition_identifier
            SELECT DISTINCT 'prh:edition:' || isbn, 'isbn10', isbn10,
                   normalize_isbn(isbn10), 1
            FROM raw_prh_edition
            WHERE normalize_isbn(isbn) <> '' AND normalize_isbn(isbn10) <> '';

            INSERT INTO source_work_author
            SELECT DISTINCT 'prh:work:' || prh_work_id,
                   'prh:author:' || prh_author_id
            FROM raw_prh_work_contributor
            WHERE prh_author_id IS NOT NULL AND (
                upper(coalesce(role_code, '')) IN ('A01', 'AUTHOR')
                OR normalize_words(role_description) IN ('author', 'written by')
            );

            INSERT INTO source_edition_author
            SELECT DISTINCT 'prh:edition:' || isbn,
                   'prh:author:' || prh_author_id
            FROM raw_prh_edition_contributor
            WHERE prh_author_id IS NOT NULL AND normalize_isbn(isbn) <> '' AND (
                upper(coalesce(role_code, '')) IN ('A01', 'AUTHOR')
                OR normalize_words(role_description) IN ('author', 'written by')
            );

            INSERT INTO source_work_subject
            SELECT DISTINCT 'prh:work:' || edition.prh_work_id, subject,
                   'prh', 'subject'
            FROM raw_prh_edition edition, unnest(edition.subjects) tags(subject)
            WHERE coalesce(subject, '') <> '';

            INSERT INTO source_work_subject
            SELECT DISTINCT 'prh:work:' || keyword.prh_work_id, candidate,
                   'prh', 'keyword'
            FROM raw_prh_keyword keyword, unnest(keyword.candidates) tags(candidate)
            WHERE coalesce(candidate, '') <> '';

            INSERT INTO source_work_subject
            SELECT DISTINCT 'prh:work:' || edition.prh_work_id,
                   edition.custom_subject_category::varchar,
                   'prh', 'custom_subject'
            FROM raw_prh_edition edition
            WHERE coalesce(edition.custom_subject_category::varchar, '') <> '';

            INSERT INTO raw_edition BY NAME
            SELECT DISTINCT 'prh:edition:' || isbn AS uuid, '0' AS work_id,
                   isbn10 AS isbn_ten, isbn AS isbn_thirteen,
                   publication_date::varchar AS publication_date,
                   extract_year(publication_date::varchar)::varchar AS publication_year,
                   NULL::varchar AS ol_id, 'prh:work:' || prh_work_id AS work_ol_id,
                   pages::varchar AS number_of_pages, NULL::varchar AS lccn,
                   NULL::varchar AS oclc_number, imprint_name AS publisher,
                   series_name AS series, NULL::varchar AS goodreads_id,
                   NULL::varchar AS google_id, asin AS asin
            FROM raw_prh_edition WHERE normalize_isbn(isbn) <> '';
        """)

    def build_work_identity(self):
        self.db.execute("""
            CREATE OR REPLACE TABLE work_merge_edge AS
            WITH work_isbn_raw AS (
                SELECT DISTINCT ew.work_key, identifier_type,
                       normalized_identifier
                FROM source_edition_identifier identifier
                JOIN source_edition_work ew USING (edition_key)
                WHERE identifier_type IN ('isbn10', 'isbn13')
                  AND normalized_identifier <> ''
            ), work_isbn AS (
                SELECT *, count(DISTINCT work_key) OVER (
                    PARTITION BY normalized_identifier
                ) AS matching_work_count
                FROM work_isbn_raw
            ), prh_ol_target AS (
                SELECT DISTINCT prh.work_key AS prh_work_key,
                       ol.work_key AS ol_work_key
                FROM work_isbn_raw prh
                JOIN work_isbn_raw ol USING (normalized_identifier)
                WHERE starts_with(prh.work_key, 'prh:work:')
                  AND NOT starts_with(ol.work_key, 'prh:work:')
            ), prh_target_count AS (
                SELECT target.prh_work_key,
                       count(DISTINCT target.ol_work_key) AS target_count,
                       count(DISTINCT ol.normalized_title) AS target_title_count,
                       min(prh.normalized_title) = min(ol.normalized_title)
                         AS titles_agree
                FROM prh_ol_target target
                JOIN source_work prh ON prh.source_key = target.prh_work_key
                JOIN source_work ol ON ol.source_key = target.ol_work_key
                GROUP BY target.prh_work_key
            )
            SELECT least(a.work_key, b.work_key) AS node_a,
                   greatest(a.work_key, b.work_key) AS node_b,
                   'shared_valid_isbn' AS match_rule,
                   0.99::double AS confidence,
                   json_object('identifier_type', a.identifier_type,
                               'identifier', a.normalized_identifier) AS evidence
            FROM work_isbn a
            JOIN work_isbn b
              ON b.normalized_identifier = a.normalized_identifier
             AND b.work_key > a.work_key
            LEFT JOIN prh_target_count a_target
              ON a_target.prh_work_key = a.work_key
            LEFT JOIN prh_target_count b_target
              ON b_target.prh_work_key = b.work_key
            WHERE a.matching_work_count <= 5
              AND (
                  starts_with(a.work_key, 'prh:work:')
                    = starts_with(b.work_key, 'prh:work:')
                  OR coalesce(a_target.target_count, b_target.target_count) = 1
                  OR (coalesce(a_target.target_title_count,
                               b_target.target_title_count) = 1
                      AND coalesce(a_target.titles_agree,
                                   b_target.titles_agree))
              );

            CREATE OR REPLACE TABLE prh_work_merge_conflict AS
            WITH work_isbn AS (
                SELECT DISTINCT ew.work_key, identifier.normalized_identifier
                FROM source_edition_identifier identifier
                JOIN source_edition_work ew USING (edition_key)
                WHERE identifier.identifier_type IN ('isbn10', 'isbn13')
                  AND identifier.normalized_identifier <> ''
            ), target AS (
                SELECT DISTINCT prh.work_key AS prh_work_key,
                       ol.work_key AS ol_work_key
                FROM work_isbn prh JOIN work_isbn ol USING (normalized_identifier)
                WHERE starts_with(prh.work_key, 'prh:work:')
                  AND NOT starts_with(ol.work_key, 'prh:work:')
            ), ambiguous AS (
                SELECT target.prh_work_key, count(*) AS target_count,
                       count(DISTINCT ol.normalized_title) AS target_title_count,
                       min(prh.normalized_title) = min(ol.normalized_title)
                         AS titles_agree
                FROM target
                JOIN source_work prh ON prh.source_key = target.prh_work_key
                JOIN source_work ol ON ol.source_key = target.ol_work_key
                GROUP BY target.prh_work_key
                HAVING count(*) > 1
                   AND (count(DISTINCT ol.normalized_title) > 1
                        OR min(prh.normalized_title) <> min(ol.normalized_title))
            )
            SELECT target.prh_work_key AS source_work_a,
                   target.ol_work_key AS source_work_b,
                   'prh_isbns_match_multiple_ol_works' AS match_rule,
                   0.20::double AS confidence,
                   json_object('openlibrary_target_count', ambiguous.target_count,
                               'note', 'kept separate pending review') AS evidence
            FROM target JOIN ambiguous USING (prh_work_key);
        """)
        connected_components(
            self.db, "SELECT source_key AS node FROM source_work",
            "work_merge_edge", "work_source_map"
        )

    def build_author_identity(self):
        self.db.execute("""
            CREATE OR REPLACE TABLE author_merge_edge AS
            WITH shared_link AS (
                SELECT least(a.author_external_id, b.author_external_id) AS node_a,
                       greatest(a.author_external_id, b.author_external_id) AS node_b,
                       normalize_url(a.url) AS link
                FROM raw_author_link a
                JOIN raw_author_link b
                  ON normalize_url(a.url) = normalize_url(b.url)
                 AND a.author_external_id < b.author_external_id
                JOIN source_author aa ON aa.source_key = a.author_external_id
                JOIN source_author bb ON bb.source_key = b.author_external_id
                WHERE normalize_url(a.url) <> ''
                  AND (
                      lower(a.link_type) = 'wikipedia'
                      OR (lower(a.link_type) = 'website'
                          AND aa.normalized_name = bb.normalized_name)
                  )
            ), shared_work AS (
                SELECT least(a.author_key, b.author_key) AS node_a,
                       greatest(a.author_key, b.author_key) AS node_b,
                       count(DISTINCT a_work.canonical_source_key) AS shared_work_count
                FROM source_work_author a
                JOIN source_work_author b
                  ON a.author_key < b.author_key
                JOIN source_author aa ON aa.source_key = a.author_key
                JOIN source_author bb ON bb.source_key = b.author_key
                JOIN work_source_map a_work ON a_work.node = a.work_key
                JOIN work_source_map b_work ON b_work.node = b.work_key
                                           AND b_work.canonical_source_key
                                               = a_work.canonical_source_key
                WHERE aa.normalized_name <> ''
                  AND aa.normalized_name = bb.normalized_name
                GROUP BY 1, 2
            )
            SELECT node_a, node_b, 'shared_external_link' AS match_rule,
                   0.995::double AS confidence,
                   json_object('normalized_url', min(link)) AS evidence
            FROM shared_link GROUP BY node_a, node_b
            UNION ALL
            SELECT shared.node_a, shared.node_b,
                   'same_name_shared_canonical_work' AS match_rule,
                   CASE WHEN shared_work_count >= 2 THEN 0.98 ELSE 0.96 END,
                   json_object('shared_work_count', shared_work_count) AS evidence
            FROM shared_work shared;

            CREATE OR REPLACE TABLE author_merge_candidate AS
            SELECT normalized_name,
                   count(*)::bigint AS source_author_count,
                   to_json((list(source_key ORDER BY source_key))[1:100]) AS sample_source_keys,
                   'same_normalized_name_only' AS match_rule,
                   0.50::double AS confidence,
                   json_object('note', 'name alone is not merge evidence') AS evidence
            FROM source_author
            WHERE normalized_name <> ''
            GROUP BY normalized_name HAVING count(*) > 1;
        """)
        connected_components(
            self.db, "SELECT source_key AS node FROM source_author",
            "author_merge_edge", "author_source_map"
        )

    def add_title_author_work_merges(self):
        self.db.execute("""
            CREATE OR REPLACE TEMP TABLE work_author_signature AS
            SELECT relation.work_key,
                   string_agg(DISTINCT author.canonical_source_key, ','
                              ORDER BY author.canonical_source_key) AS signature
            FROM source_work_author relation
            JOIN author_source_map author ON author.node = relation.author_key
            GROUP BY relation.work_key;

            INSERT INTO work_merge_edge
            SELECT least(a.source_key, b.source_key),
                   greatest(a.source_key, b.source_key),
                   'exact_title_author_and_year', 0.94::double,
                   json_object('normalized_title', a.normalized_title,
                               'publication_year', a.publication_year,
                               'author_signature', aa.signature)
            FROM source_work a
            JOIN source_work b
              ON b.normalized_title = a.normalized_title
             AND b.source_key > a.source_key
             AND b.publication_year = a.publication_year
            JOIN work_author_signature aa ON aa.work_key = a.source_key
            JOIN work_author_signature bb ON bb.work_key = b.source_key
                                           AND bb.signature = aa.signature
            WHERE a.normalized_title <> ''
              AND a.publication_year IS NOT NULL
              AND aa.signature <> ''
              AND NOT EXISTS (
                  SELECT 1 FROM work_merge_edge edge
                  WHERE edge.node_a = a.source_key AND edge.node_b = b.source_key
              );

            CREATE OR REPLACE TABLE work_merge_candidate AS
            SELECT least(a.source_key, b.source_key) AS source_work_a,
                   greatest(a.source_key, b.source_key) AS source_work_b,
                   'exact_title_and_author_without_year' AS match_rule,
                   0.70::double AS confidence,
                   json_object('normalized_title', a.normalized_title,
                               'author_signature', aa.signature) AS evidence
            FROM source_work a
            JOIN source_work b
              ON b.normalized_title = a.normalized_title
             AND b.source_key > a.source_key
            JOIN work_author_signature aa ON aa.work_key = a.source_key
            JOIN work_author_signature bb ON bb.work_key = b.source_key
                                           AND bb.signature = aa.signature
            WHERE a.normalized_title <> '' AND aa.signature <> ''
              AND (a.publication_year IS NULL OR b.publication_year IS NULL
                   OR a.publication_year <> b.publication_year)
              AND NOT EXISTS (
                  SELECT 1 FROM work_merge_edge edge
                  WHERE edge.node_a = a.source_key AND edge.node_b = b.source_key
              );

            INSERT INTO work_merge_candidate
            SELECT source_work_a, source_work_b, match_rule, confidence, evidence
            FROM prh_work_merge_conflict;
        """)
        connected_components(
            self.db, "SELECT source_key AS node FROM source_work",
            "work_merge_edge", "work_source_map"
        )

    def converge_work_and_author_identity(self):
        """Resolve the circular dependency between work and author identity.

        A newly merged work can provide evidence that two same-name authors are
        identical. Merging those authors can in turn make two title/year work
        signatures identical. Repeat the two evidence passes until neither
        edge set grows.
        """
        previous_counts = None
        for _ in range(20):
            self.build_author_identity()
            self.add_title_author_work_merges()
            counts = (
                self.db.execute("SELECT count(*) FROM work_merge_edge").fetchone()[0],
                self.db.execute("SELECT count(*) FROM author_merge_edge").fetchone()[0],
            )
            if counts == previous_counts:
                return
            previous_counts = counts
        raise RuntimeError("Work/author identity did not converge after 20 passes")

    def build_canonical_tables(self):
        self.db.execute("""
            CREATE OR REPLACE TABLE canonical_author AS
            WITH ranked AS (
                SELECT mapping.canonical_source_key,
                       source.*,
                       row_number() OVER (
                           PARTITION BY mapping.canonical_source_key
                           ORDER BY ((creator_name IS NOT NULL)::int
                                   + (personal_name IS NOT NULL)::int
                                   + (birth_date IS NOT NULL)::int
                                   + (death_date IS NOT NULL)::int) DESC,
                                    source.source_key
                       ) AS preference
                FROM source_author source
                JOIN author_source_map mapping ON mapping.node = source.source_key
            ), chosen AS (
                SELECT *, dense_rank() OVER (ORDER BY canonical_source_key) AS id
                FROM ranked WHERE preference = 1
            )
            SELECT id::bigint AS id, canonical_source_key AS uuid,
                   creator_name, personal_name, birth_date, death_date,
                   CASE WHEN starts_with(canonical_source_key, '/')
                        THEN regexp_extract(canonical_source_key, '([^/]+)$', 1) END AS ol_id
            FROM chosen;

            CREATE OR REPLACE TABLE author_external_identifier AS
            SELECT canonical.id AS author_id,
                   CASE WHEN starts_with(mapping.node, 'prh:author:')
                        THEN 'prh' ELSE 'openlibrary' END AS provider,
                   CASE WHEN starts_with(mapping.node, 'prh:author:')
                        THEN replace(mapping.node, 'prh:author:', '')
                        ELSE mapping.node END AS external_id,
                   mapping.node = mapping.canonical_source_key AS is_canonical
            FROM author_source_map mapping
            JOIN canonical_author canonical
              ON canonical.uuid = mapping.canonical_source_key;

            CREATE OR REPLACE TABLE canonical_author_alternate_name AS
            SELECT canonical.id AS author_id, alternate.alternate_name,
                   min(try_cast(alternate.position AS integer)) AS position
            FROM raw_author_alternate_name alternate
            JOIN author_source_map mapping
              ON mapping.node = alternate.author_external_id
            JOIN canonical_author canonical
              ON canonical.uuid = mapping.canonical_source_key
            WHERE coalesce(alternate.alternate_name, '') <> ''
            GROUP BY canonical.id, alternate.alternate_name;

            CREATE OR REPLACE TABLE canonical_author_link AS
            SELECT canonical.id AS author_id, lower(link.link_type) AS link_type,
                   link.url
            FROM raw_author_link link
            JOIN author_source_map mapping
              ON mapping.node = link.author_external_id
            JOIN canonical_author canonical
              ON canonical.uuid = mapping.canonical_source_key
            WHERE normalize_url(link.url) <> ''
            GROUP BY canonical.id, lower(link.link_type), link.url;

            CREATE OR REPLACE TABLE canonical_work_base AS
            WITH ranked AS (
                SELECT mapping.canonical_source_key, source.*,
                       row_number() OVER (
                         PARTITION BY mapping.canonical_source_key
                         ORDER BY ((title IS NOT NULL)::int
                                 + (description IS NOT NULL)::int
                                 + (cover_id IS NOT NULL)::int
                                 + (publication_year IS NOT NULL)::int) DESC,
                                  source.source_key
                       ) AS preference
                FROM source_work source
                JOIN work_source_map mapping ON mapping.node = source.source_key
            ), aggregate_date AS (
                SELECT mapping.canonical_source_key,
                       min(source.publication_date_epoch) AS earliest_epoch,
                       arg_min(source.first_publication_date,
                               source.publication_date_epoch)
                           FILTER (WHERE source.publication_date_epoch IS NOT NULL)
                           AS earliest_date
                FROM source_work source
                JOIN work_source_map mapping ON mapping.node = source.source_key
                GROUP BY mapping.canonical_source_key
            ), chosen AS (
                SELECT *, dense_rank() OVER (ORDER BY canonical_source_key) AS id
                FROM ranked WHERE preference = 1
            )
            SELECT id::bigint AS id, canonical_source_key AS uuid, title,
                   sub_title, description,
                   coalesce(aggregate_date.earliest_date, chosen.first_publication_date)
                       AS first_publication_date,
                   coalesce(aggregate_date.earliest_epoch, chosen.publication_date_epoch)
                       AS publication_date_epoch,
                   nullif(isbn_ten, '') AS isbn_ten,
                   nullif(isbn_thirteen, '') AS isbn_thirteen,
                   nullif(language_code, '') AS language_code,
                   num_of_pages,
                   CASE WHEN starts_with(canonical_source_key, '/')
                        THEN regexp_extract(canonical_source_key, '([^/]+)$', 1) END AS ol_id,
                   cover_id, featured_covers,
                   nullif(series, '') AS series,
                   nullif(position_in_series, '') AS position_in_series,
                   nullif(reading_id, '') AS reading_id,
                   nullif(prh_id, '') AS prh_id,
                   coalesce(goodreads_resolved, false) AS goodreads_resolved,
                   coalesce(google_resolved, false) AS google_resolved
            FROM chosen JOIN aggregate_date USING (canonical_source_key);

            CREATE OR REPLACE TABLE work_external_identifier AS
            SELECT canonical.id AS work_id,
                   CASE WHEN starts_with(mapping.node, 'prh:work:')
                        THEN 'prh' ELSE 'openlibrary' END AS provider,
                   CASE WHEN starts_with(mapping.node, 'prh:work:')
                        THEN replace(mapping.node, 'prh:work:', '')
                        ELSE mapping.node END AS external_id,
                   mapping.node = mapping.canonical_source_key AS is_canonical
            FROM work_source_map mapping
            JOIN canonical_work_base canonical
              ON canonical.uuid = mapping.canonical_source_key;

            CREATE OR REPLACE TABLE canonical_work_creator AS
            SELECT DISTINCT work.id AS work_id, author.id AS creator_id
            FROM source_work_author relation
            JOIN work_source_map work_mapping ON work_mapping.node = relation.work_key
            JOIN canonical_work_base work ON work.uuid = work_mapping.canonical_source_key
            JOIN author_source_map author_mapping ON author_mapping.node = relation.author_key
            JOIN canonical_author author ON author.uuid = author_mapping.canonical_source_key;

            CREATE OR REPLACE TABLE canonical_work_cover AS
            SELECT work.id AS work_id, try_cast(cover.cover_id AS bigint) AS cover_id,
                   min(try_cast(cover.position AS integer)) AS position
            FROM raw_work_cover cover
            JOIN work_source_map mapping ON mapping.node = cover.work_external_id
            JOIN canonical_work_base work ON work.uuid = mapping.canonical_source_key
            WHERE try_cast(cover.cover_id AS bigint) > 0
            GROUP BY work.id, try_cast(cover.cover_id AS bigint);
        """)

    def build_editions_and_featured(self):
        self.db.execute("""
            CREATE OR REPLACE TABLE edition_assignment AS
            SELECT edition.uuid AS edition_key, work.id AS work_id,
                   edition.*, extract_year(edition.publication_date) AS parsed_year,
                   row_number() OVER (PARTITION BY edition.uuid ORDER BY relation.position) AS link_rank
            FROM raw_edition edition
            JOIN source_edition_work relation ON relation.edition_key = edition.uuid
            JOIN work_source_map mapping ON mapping.node = relation.work_key
            JOIN canonical_work_base work ON work.uuid = mapping.canonical_source_key;

            CREATE OR REPLACE TABLE edition_merge_edge AS
            WITH edition_isbn AS (
                SELECT DISTINCT assignment.edition_key, assignment.work_id,
                       identifier.identifier_type,
                       identifier.normalized_identifier
                FROM edition_assignment assignment
                JOIN source_edition_identifier identifier
                  ON identifier.edition_key = assignment.edition_key
                WHERE assignment.link_rank = 1
                  AND identifier.identifier_type IN ('isbn10', 'isbn13')
                  AND identifier.normalized_identifier <> ''
            )
            SELECT least(a.edition_key, b.edition_key) AS node_a,
                   greatest(a.edition_key, b.edition_key) AS node_b,
                   'same_work_shared_valid_isbn' AS match_rule,
                   0.995::double AS confidence,
                   json_object('identifier_type', a.identifier_type,
                               'identifier', a.normalized_identifier) AS evidence
            FROM edition_isbn a JOIN edition_isbn b
              ON b.work_id = a.work_id
             AND b.identifier_type = a.identifier_type
             AND b.normalized_identifier = a.normalized_identifier
             AND b.edition_key > a.edition_key;
        """)
        connected_components(
            self.db,
            "SELECT DISTINCT edition_key AS node FROM edition_assignment WHERE link_rank = 1",
            "edition_merge_edge", "edition_source_map"
        )
        self.db.execute("""
            CREATE OR REPLACE TABLE canonical_edition AS
            WITH ranked AS (
                SELECT mapping.canonical_source_key, assignment.*,
                       EXISTS(SELECT 1 FROM source_edition_identifier identifier
                              WHERE identifier.edition_key = assignment.edition_key
                                AND identifier.identifier_type IN ('isbn10','isbn13')
                                AND identifier.normalized_identifier <> '') AS has_isbn,
                       row_number() OVER (
                         PARTITION BY mapping.canonical_source_key
                         ORDER BY ((isbn_thirteen IS NOT NULL)::int
                                 + (isbn_ten IS NOT NULL)::int
                                 + (publication_date IS NOT NULL)::int
                                 + (publisher IS NOT NULL)::int) DESC,
                                  assignment.edition_key
                       ) AS preference
                FROM edition_assignment assignment
                JOIN edition_source_map mapping ON mapping.node = assignment.edition_key
                WHERE assignment.link_rank = 1
            ), chosen AS (
                SELECT *, dense_rank() OVER (ORDER BY canonical_source_key) AS id
                FROM ranked WHERE preference = 1
            )
            SELECT id::bigint AS id, work_id, canonical_source_key AS uuid,
                   nullif(isbn_ten, '') AS isbn_ten,
                   nullif(isbn_thirteen, '') AS isbn_thirteen,
                   publication_date, parsed_year AS publication_year,
                   CASE WHEN starts_with(canonical_source_key, '/')
                        THEN regexp_extract(canonical_source_key, '([^/]+)$', 1) END AS ol_id,
                   number_of_pages, lccn, oclc_number, publisher, series,
                   goodreads_id, google_id, asin, has_isbn
            FROM chosen;

            CREATE OR REPLACE TABLE featured_edition_choice AS
            SELECT work_id, id AS edition_id
            FROM (
                SELECT edition.*,
                       row_number() OVER (
                         PARTITION BY work_id
                         ORDER BY has_isbn DESC,
                                  (publication_year IS NOT NULL) DESC,
                                  publication_year DESC NULLS LAST, id
                       ) AS preference
                FROM canonical_edition edition
            ) ranked WHERE preference = 1;

            CREATE OR REPLACE TABLE canonical_work AS
            SELECT work.*, featured.edition_id AS featured_edition_fk
            FROM canonical_work_base work
            LEFT JOIN featured_edition_choice featured ON featured.work_id = work.id;

            CREATE OR REPLACE TABLE edition_external_identifier AS
            SELECT canonical.id AS edition_id,
                   CASE WHEN starts_with(mapping.node, 'prh:edition:')
                        THEN 'prh' ELSE 'openlibrary' END AS provider,
                   CASE WHEN starts_with(mapping.node, 'prh:edition:')
                        THEN replace(mapping.node, 'prh:edition:', '')
                        ELSE mapping.node END AS external_id,
                   mapping.node = mapping.canonical_source_key AS is_canonical
            FROM edition_source_map mapping
            JOIN canonical_edition canonical
              ON canonical.uuid = mapping.canonical_source_key;

            CREATE OR REPLACE TABLE canonical_edition_identifier AS
            SELECT canonical.id AS edition_id, identifier.identifier_type,
                   identifier.source_identifier AS identifier,
                   nullif(identifier.normalized_identifier, '') AS normalized_identifier,
                   min(identifier.position) AS position
            FROM source_edition_identifier identifier
            JOIN edition_source_map mapping ON mapping.node = identifier.edition_key
            JOIN canonical_edition canonical
              ON canonical.uuid = mapping.canonical_source_key
            WHERE coalesce(identifier.source_identifier, '') <> ''
            GROUP BY canonical.id, identifier.identifier_type,
                     identifier.source_identifier, identifier.normalized_identifier;

            CREATE OR REPLACE TABLE canonical_edition_publisher AS
            SELECT canonical.id AS edition_id, publisher.publisher,
                   min(try_cast(publisher.position AS integer)) AS position
            FROM raw_edition_publisher publisher
            JOIN edition_source_map mapping
              ON mapping.node = publisher.edition_external_id
            JOIN canonical_edition canonical
              ON canonical.uuid = mapping.canonical_source_key
            WHERE coalesce(publisher.publisher, '') <> ''
            GROUP BY canonical.id, publisher.publisher;

            CREATE OR REPLACE TABLE canonical_edition_cover AS
            SELECT canonical.id AS edition_id,
                   try_cast(cover.cover_id AS bigint) AS cover_id,
                   min(try_cast(cover.position AS integer)) AS position
            FROM raw_edition_cover cover
            JOIN edition_source_map mapping
              ON mapping.node = cover.edition_external_id
            JOIN canonical_edition canonical
              ON canonical.uuid = mapping.canonical_source_key
            WHERE try_cast(cover.cover_id AS bigint) > 0
            GROUP BY canonical.id, try_cast(cover.cover_id AS bigint);

            CREATE OR REPLACE TABLE canonical_edition_language AS
            SELECT canonical.id AS edition_id, language.language_code,
                   min(try_cast(language.position AS integer)) AS position
            FROM raw_edition_language language
            JOIN edition_source_map mapping
              ON mapping.node = language.edition_external_id
            JOIN canonical_edition canonical
              ON canonical.uuid = mapping.canonical_source_key
            WHERE coalesce(language.language_code, '') <> ''
            GROUP BY canonical.id, language.language_code;

            CREATE OR REPLACE TABLE canonical_edition_creator AS
            SELECT DISTINCT edition.id AS edition_id, author.id AS creator_id
            FROM source_edition_author relation
            JOIN edition_source_map edition_mapping
              ON edition_mapping.node = relation.edition_key
            JOIN canonical_edition edition
              ON edition.uuid = edition_mapping.canonical_source_key
            JOIN author_source_map author_mapping
              ON author_mapping.node = relation.author_key
            JOIN canonical_author author
              ON author.uuid = author_mapping.canonical_source_key;
        """)

    def build_tags_and_profiles(self):
        self.db.execute("""
            CREATE OR REPLACE TABLE normalized_work_subject AS
            SELECT DISTINCT work.id AS work_id,
                   normalize_tag(subject.subject) AS tag_name,
                   subject.provider, subject.tag_source
            FROM source_work_subject subject
            JOIN work_source_map mapping ON mapping.node = subject.work_key
            JOIN canonical_work_base work ON work.uuid = mapping.canonical_source_key
            WHERE normalize_tag(subject.subject) <> '';

            CREATE OR REPLACE TABLE canonical_tag AS
            WITH prevalence AS (
                SELECT tag_name, count(DISTINCT work_id)::bigint AS prevalence
                FROM normalized_work_subject GROUP BY tag_name
            ), totals AS (
                SELECT count(*)::double AS total_works FROM canonical_work
            )
            SELECT row_number() OVER (ORDER BY prevalence DESC, tag_name)::bigint AS id,
                   tag_name, prevalence,
                   ln(1 + total_works / (prevalence + 1)) AS weight
            FROM prevalence CROSS JOIN totals;

            CREATE OR REPLACE TABLE canonical_work_tag AS
            SELECT DISTINCT subject.work_id, tag.id AS tag_id
            FROM normalized_work_subject subject
            JOIN canonical_tag tag USING (tag_name);

            CREATE OR REPLACE TABLE canonical_work_tag_source AS
            SELECT DISTINCT subject.work_id, tag.id AS tag_id,
                   subject.provider, subject.tag_source
            FROM normalized_work_subject subject
            JOIN canonical_tag tag USING (tag_name);

            CREATE OR REPLACE TABLE author_catalog_size AS
            SELECT creator.creator_id AS author_id,
                   count(DISTINCT creator.work_id)::bigint AS catalog_size
            FROM canonical_work_creator creator
            JOIN canonical_work_tag tag ON tag.work_id = creator.work_id
            GROUP BY creator.creator_id;

            CREATE OR REPLACE TABLE author_tag_profile AS
            WITH counts AS (
                SELECT creator.creator_id AS author_id, tag.tag_id,
                       count(DISTINCT creator.work_id)::bigint AS work_count
                FROM canonical_work_creator creator
                JOIN canonical_work_tag tag ON tag.work_id = creator.work_id
                GROUP BY creator.creator_id, tag.tag_id
            ), totals AS (
                SELECT count(DISTINCT work_id)::double AS total_tagged_works
                FROM canonical_work_tag
            )
            SELECT count.author_id, count.tag_id, count.work_count,
                   count.work_count::double / catalog.catalog_size AS catalog_share,
                   (count.work_count::double / catalog.catalog_size)
                     * ln(1 + totals.total_tagged_works / (tag.prevalence + 1))
                       AS profile_weight,
                   current_timestamp AS updated_at
            FROM counts count
            JOIN author_catalog_size catalog USING (author_id)
            JOIN canonical_tag tag ON tag.id = count.tag_id
            CROSS JOIN totals;

            CREATE OR REPLACE TABLE author_profile_state AS
            WITH profile_hash AS (
                SELECT profile.author_id,
                       md5(string_agg(profile.tag_id || ':' || round(profile.profile_weight, 8),
                                      ',' ORDER BY profile.tag_id)) AS profile_hash
                FROM author_tag_profile profile GROUP BY profile.author_id
            )
            SELECT author.id AS author_id,
                   coalesce(catalog.catalog_size, 0) AS tagged_work_count,
                   coalesce(profile.profile_hash, md5('')) AS profile_hash,
                   coalesce(profile.profile_hash, md5('')) AS similarity_profile_hash,
                   current_timestamp AS profile_generated_at,
                   current_timestamp AS similarity_generated_at,
                   'author-similarity-v1' AS algorithm_version
            FROM canonical_author author
            LEFT JOIN author_catalog_size catalog ON catalog.author_id = author.id
            LEFT JOIN profile_hash profile ON profile.author_id = author.id;
        """)

    def build_prh_metadata(self):
        """Attach PRH-only enrichment after canonical IDs have been assigned."""
        self.db.execute("""
            CREATE OR REPLACE TABLE canonical_prh_author_profile AS
            SELECT DISTINCT author.id AS author_id,
                   profile.prh_author_id, profile.biography_html,
                   profile.photo_url, profile.photo_credit, profile.photo_date,
                   profile.prh_url, profile.reported_work_count,
                   profile.related_links::json AS related_links
            FROM raw_prh_author_profile profile
            JOIN author_source_map mapping
              ON mapping.node = 'prh:author:' || profile.prh_author_id
            JOIN canonical_author author
              ON author.uuid = mapping.canonical_source_key;

            CREATE OR REPLACE TABLE canonical_prh_work_metadata AS
            SELECT DISTINCT work.id AS work_id, source.prh_work_id,
                   source.prh_display_title, source.prh_url,
                   source.keynote_html, source.positioning_html,
                   source.awards::json AS awards, source.frontlistiest_isbn,
                   source.isbn_counts::json AS isbn_counts
            FROM raw_prh_work source
            JOIN work_source_map mapping
              ON mapping.node = 'prh:work:' || source.prh_work_id
            JOIN canonical_work_base work
              ON work.uuid = mapping.canonical_source_key;

            CREATE OR REPLACE TABLE canonical_prh_edition_metadata AS
            SELECT DISTINCT edition.id AS edition_id, source.prh_work_id,
                   source.isbn, source.trim_size, source.format_family,
                   source.format_code, source.format_name, source.version,
                   source.imprint_code, source.imprint_name, source.asin,
                   source.cover_url, source.prh_url, source.series_code,
                   source.series_name, source.series_position,
                   source.custom_subject_category, source.sales_restriction,
                   source.raw_flags::json AS raw_flags
            FROM raw_prh_edition source
            JOIN edition_source_map mapping
              ON mapping.node = 'prh:edition:' || source.isbn
            JOIN canonical_edition edition
              ON edition.uuid = mapping.canonical_source_key;

            CREATE OR REPLACE TABLE canonical_work_contributor AS
            SELECT DISTINCT work.id AS work_id, author.id AS creator_id,
                   contributor.role_code, contributor.role_description,
                   contributor.display, contributor.primary_flag,
                   contributor.observed_isbns::json AS observed_isbns,
                   'prh'::varchar AS provider
            FROM raw_prh_work_contributor contributor
            JOIN work_source_map work_mapping
              ON work_mapping.node = 'prh:work:' || contributor.prh_work_id
            JOIN canonical_work_base work
              ON work.uuid = work_mapping.canonical_source_key
            JOIN author_source_map author_mapping
              ON author_mapping.node = 'prh:author:' || contributor.prh_author_id
            JOIN canonical_author author
              ON author.uuid = author_mapping.canonical_source_key;

            CREATE OR REPLACE TABLE canonical_work_cover_url AS
            SELECT DISTINCT work.id AS work_id, edition.cover_url AS url,
                   'prh'::varchar AS provider
            FROM raw_prh_edition edition
            JOIN work_source_map mapping
              ON mapping.node = 'prh:work:' || edition.prh_work_id
            JOIN canonical_work_base work
              ON work.uuid = mapping.canonical_source_key
            WHERE coalesce(edition.cover_url, '') <> '';

            CREATE OR REPLACE TABLE canonical_series AS
            WITH source AS (
                SELECT prh_series_code, name, description_html, series_count,
                       series_date, is_numbered, is_kids, prh_url, 0 AS preference
                FROM raw_prh_series
                UNION ALL
                SELECT prh_series_code, series_name, description_html, NULL,
                       NULL, NULL, NULL, prh_url, 1
                FROM raw_prh_series_hint
            ), ranked AS (
                SELECT *, row_number() OVER (
                    PARTITION BY prh_series_code ORDER BY preference,
                    (name IS NULL), name
                ) AS choice
                FROM source WHERE coalesce(prh_series_code, '') <> ''
            )
            SELECT row_number() OVER (ORDER BY prh_series_code)::bigint AS id,
                   'prh:series:' || prh_series_code AS uuid,
                   prh_series_code, name, description_html, series_count,
                   series_date, is_numbered, is_kids, prh_url
            FROM ranked WHERE choice = 1;

            CREATE OR REPLACE TABLE series_external_identifier AS
            SELECT id AS series_id, 'prh'::varchar AS provider,
                   prh_series_code AS external_id, true AS is_canonical
            FROM canonical_series;

            CREATE OR REPLACE TABLE canonical_work_series AS
            WITH memberships AS (
                SELECT prh_series_code, prh_work_id, position, 0 AS preference
                FROM raw_prh_work_series
                UNION ALL
                SELECT prh_series_code, prh_work_id, position, 1
                FROM raw_prh_series_hint
            ), ranked AS (
                SELECT *, row_number() OVER (
                    PARTITION BY prh_series_code, prh_work_id
                    ORDER BY preference, position NULLS LAST
                ) AS choice
                FROM memberships
            )
            SELECT DISTINCT work.id AS work_id, series.id AS series_id,
                   membership.position
            FROM ranked membership
            JOIN canonical_series series
              ON series.prh_series_code = membership.prh_series_code
            JOIN work_source_map mapping
              ON mapping.node = 'prh:work:' || membership.prh_work_id
            JOIN canonical_work_base work
              ON work.uuid = mapping.canonical_source_key
            WHERE membership.choice = 1;
        """)

    def build_similar_authors(self):
        minimum = int(self.minimum_shared_tags)
        limit = int(self.similar_limit)
        self.db.execute(f"""
            CREATE OR REPLACE TABLE similar_author AS
            WITH ranked_profile AS (
                SELECT profile.*,
                       row_number() OVER (
                         PARTITION BY author_id ORDER BY profile_weight DESC, tag_id
                       ) AS profile_rank
                FROM author_tag_profile profile
            ), norm AS (
                SELECT author_id, sqrt(sum(profile_weight * profile_weight)) AS value
                FROM ranked_profile GROUP BY author_id
            ), pair AS (
                SELECT a.author_id, b.author_id AS similar_author_id,
                       sum(a.profile_weight * b.profile_weight) AS dot_product,
                       count(*)::integer AS shared_tag_count,
                       to_json((list(struct_pack(
                           tagId := a.tag_id,
                           tagName := tag.tag_name,
                           contribution := a.profile_weight * b.profile_weight
                       ) ORDER BY a.profile_weight * b.profile_weight DESC,
                                  a.tag_id))[1:10]) AS shared_tags
                FROM ranked_profile a
                JOIN ranked_profile b ON b.tag_id = a.tag_id
                                     AND b.author_id <> a.author_id
                JOIN canonical_tag tag ON tag.id = a.tag_id
                WHERE a.profile_rank <= 50 AND b.profile_rank <= 50
                  AND tag.prevalence <= 20000
                GROUP BY a.author_id, b.author_id
                HAVING count(*) >= {minimum}
            ), scored AS (
                SELECT pair.*,
                       pair.dot_product / nullif(a_norm.value * b_norm.value, 0)
                         * sqrt(
                             (1 - exp(-a_size.catalog_size / 3.0))
                           * (1 - exp(-b_size.catalog_size / 3.0))
                         ) AS similarity_score
                FROM pair
                JOIN norm a_norm ON a_norm.author_id = pair.author_id
                JOIN norm b_norm ON b_norm.author_id = pair.similar_author_id
                JOIN author_catalog_size a_size ON a_size.author_id = pair.author_id
                JOIN author_catalog_size b_size ON b_size.author_id = pair.similar_author_id
            ), ranked AS (
                SELECT *, row_number() OVER (
                    PARTITION BY author_id
                    ORDER BY similarity_score DESC, similar_author_id
                ) AS rank
                FROM scored
            )
            SELECT author_id, similar_author_id, similarity_score,
                   shared_tag_count, shared_tags::json AS shared_tags,
                   rank::integer AS rank, current_timestamp AS generated_at
            FROM ranked WHERE rank <= {limit};
        """)

    def export(self):
        exports = {
            "authors.csv": "SELECT * FROM canonical_author ORDER BY id",
            "author_external_identifiers.csv": "SELECT * FROM author_external_identifier ORDER BY author_id, provider, external_id",
            "author_alternate_names.csv": "SELECT * FROM canonical_author_alternate_name ORDER BY author_id, position, alternate_name",
            "author_external_links.csv": "SELECT * FROM canonical_author_link ORDER BY author_id, link_type, url",
            "author_profiles.csv": "SELECT * FROM canonical_prh_author_profile ORDER BY author_id, prh_author_id",
            "author_merge_audit.csv": "SELECT node_a AS source_author_a, node_b AS source_author_b, match_rule, confidence, evidence FROM author_merge_edge ORDER BY node_a, node_b, match_rule",
            "author_merge_candidates.csv": "SELECT * FROM author_merge_candidate ORDER BY normalized_name",
            "works.csv": "SELECT * FROM canonical_work ORDER BY id",
            "work_external_identifiers.csv": "SELECT * FROM work_external_identifier ORDER BY work_id, provider, external_id",
            "work_merge_audit.csv": "SELECT node_a AS source_work_a, node_b AS source_work_b, match_rule, confidence, evidence FROM work_merge_edge ORDER BY node_a, node_b, match_rule",
            "work_merge_candidates.csv": "SELECT * FROM work_merge_candidate ORDER BY source_work_a, source_work_b",
            "work_creators.csv": "SELECT * FROM canonical_work_creator ORDER BY work_id, creator_id",
            "work_covers.csv": "SELECT * FROM canonical_work_cover ORDER BY work_id, position, cover_id",
            "work_cover_urls.csv": "SELECT * FROM canonical_work_cover_url ORDER BY work_id, provider, url",
            "work_contributors.csv": "SELECT * FROM canonical_work_contributor ORDER BY work_id, creator_id, role_code",
            "prh_work_metadata.csv": "SELECT * FROM canonical_prh_work_metadata ORDER BY work_id, prh_work_id",
            "editions.csv": "SELECT * EXCLUDE (has_isbn) FROM canonical_edition ORDER BY id",
            "edition_external_identifiers.csv": "SELECT * FROM edition_external_identifier ORDER BY edition_id, provider, external_id",
            "edition_identifiers.csv": "SELECT * FROM canonical_edition_identifier ORDER BY edition_id, identifier_type, position, identifier",
            "edition_publishers.csv": "SELECT * FROM canonical_edition_publisher ORDER BY edition_id, position, publisher",
            "edition_covers.csv": "SELECT * FROM canonical_edition_cover ORDER BY edition_id, position, cover_id",
            "edition_languages.csv": "SELECT * FROM canonical_edition_language ORDER BY edition_id, position, language_code",
            "edition_creators.csv": "SELECT * FROM canonical_edition_creator ORDER BY edition_id, creator_id",
            "prh_edition_metadata.csv": "SELECT * FROM canonical_prh_edition_metadata ORDER BY edition_id",
            "tags.csv": "SELECT * FROM canonical_tag ORDER BY id",
            "work_tags.csv": "SELECT * FROM canonical_work_tag ORDER BY work_id, tag_id",
            "work_tag_sources.csv": "SELECT * FROM canonical_work_tag_source ORDER BY work_id, tag_id, provider, tag_source",
            "series.csv": "SELECT * FROM canonical_series ORDER BY id",
            "series_external_identifiers.csv": "SELECT * FROM series_external_identifier ORDER BY series_id, provider, external_id",
            "work_series.csv": "SELECT * FROM canonical_work_series ORDER BY work_id, series_id",
            "author_tag_profiles.csv": "SELECT * FROM author_tag_profile ORDER BY author_id, profile_weight DESC, tag_id",
            "author_profile_state.csv": "SELECT * FROM author_profile_state ORDER BY author_id",
            "similar_authors.csv": "SELECT * FROM similar_author ORDER BY author_id, rank",
        }
        for filename, query in exports.items():
            destination = sql_path(self.output_dir / filename)
            self.db.execute(f"COPY ({query}) TO '{destination}' (HEADER, DELIMITER ',')")

        summary = {
            "source_authors": self.db.execute("SELECT count(*) FROM source_author").fetchone()[0],
            "source_works": self.db.execute("SELECT count(*) FROM source_work").fetchone()[0],
            "source_editions_assigned": self.db.execute("SELECT count(*) FROM edition_source_map").fetchone()[0],
            "authors": self.db.execute("SELECT count(*) FROM canonical_author").fetchone()[0],
            "works": self.db.execute("SELECT count(*) FROM canonical_work").fetchone()[0],
            "editions": self.db.execute("SELECT count(*) FROM canonical_edition").fetchone()[0],
            "tags": self.db.execute("SELECT count(*) FROM canonical_tag").fetchone()[0],
            "work_merge_evidence_edges": self.db.execute("SELECT count(*) FROM work_merge_edge").fetchone()[0],
            "author_merge_evidence_edges": self.db.execute("SELECT count(*) FROM author_merge_edge").fetchone()[0],
            "similar_authors": self.db.execute("SELECT count(*) FROM similar_author").fetchone()[0],
        }
        summary["work_merges"] = summary["source_works"] - summary["works"]
        summary["author_merges"] = summary["source_authors"] - summary["authors"]
        summary["edition_merges"] = (
            summary["source_editions_assigned"] - summary["editions"]
        )
        with open(self.output_dir / "build_summary.json", "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, sort_keys=True)
        return summary

    def validate(self):
        checks = {
            "work_aliases_without_work": """
                SELECT count(*) FROM work_external_identifier alias
                LEFT JOIN canonical_work work ON work.id = alias.work_id
                WHERE work.id IS NULL
            """,
            "author_aliases_without_author": """
                SELECT count(*) FROM author_external_identifier alias
                LEFT JOIN canonical_author author ON author.id = alias.author_id
                WHERE author.id IS NULL
            """,
            "edition_aliases_without_edition": """
                SELECT count(*) FROM edition_external_identifier alias
                LEFT JOIN canonical_edition edition ON edition.id = alias.edition_id
                WHERE edition.id IS NULL
            """,
            "missing_work_aliases": """
                SELECT abs(
                    (SELECT count(*) FROM source_work)
                    - (SELECT count(*) FROM work_external_identifier)
                )
            """,
            "missing_author_aliases": """
                SELECT abs(
                    (SELECT count(*) FROM source_author)
                    - (SELECT count(*) FROM author_external_identifier)
                )
            """,
            "missing_edition_aliases": """
                SELECT abs(
                    (SELECT count(*) FROM edition_source_map)
                    - (SELECT count(*) FROM edition_external_identifier)
                )
            """,
            "work_creator_orphans": """
                SELECT count(*) FROM canonical_work_creator relation
                LEFT JOIN canonical_work work ON work.id = relation.work_id
                LEFT JOIN canonical_author author ON author.id = relation.creator_id
                WHERE work.id IS NULL OR author.id IS NULL
            """,
            "work_tag_orphans": """
                SELECT count(*) FROM canonical_work_tag relation
                LEFT JOIN canonical_work work ON work.id = relation.work_id
                LEFT JOIN canonical_tag tag ON tag.id = relation.tag_id
                WHERE work.id IS NULL OR tag.id IS NULL
            """,
            "work_contributor_orphans": """
                SELECT count(*) FROM canonical_work_contributor relation
                LEFT JOIN canonical_work work ON work.id = relation.work_id
                LEFT JOIN canonical_author author ON author.id = relation.creator_id
                WHERE work.id IS NULL OR author.id IS NULL
            """,
            "work_series_orphans": """
                SELECT count(*) FROM canonical_work_series relation
                LEFT JOIN canonical_work work ON work.id = relation.work_id
                LEFT JOIN canonical_series series ON series.id = relation.series_id
                WHERE work.id IS NULL OR series.id IS NULL
            """,
            "edition_creator_orphans": """
                SELECT count(*) FROM canonical_edition_creator relation
                LEFT JOIN canonical_edition edition ON edition.id = relation.edition_id
                LEFT JOIN canonical_author author ON author.id = relation.creator_id
                WHERE edition.id IS NULL OR author.id IS NULL
            """,
            "works_with_editions_missing_featured": """
                SELECT count(*) FROM canonical_work work
                WHERE EXISTS (SELECT 1 FROM canonical_edition edition
                              WHERE edition.work_id = work.id)
                  AND work.featured_edition_fk IS NULL
            """,
            "featured_editions_on_wrong_work": """
                SELECT count(*) FROM canonical_work work
                JOIN canonical_edition edition
                  ON edition.id = work.featured_edition_fk
                WHERE edition.work_id <> work.id
            """,
            "duplicate_work_creators": """
                SELECT count(*) FROM (
                    SELECT work_id, creator_id FROM canonical_work_creator
                    GROUP BY work_id, creator_id HAVING count(*) > 1
                ) duplicate
            """,
            "duplicate_work_tags": """
                SELECT count(*) FROM (
                    SELECT work_id, tag_id FROM canonical_work_tag
                    GROUP BY work_id, tag_id HAVING count(*) > 1
                ) duplicate
            """,
            "invalid_profile_weights": """
                SELECT count(*) FROM author_tag_profile
                WHERE profile_weight < 0 OR catalog_share < 0 OR catalog_share > 1
            """,
            "self_similar_authors": """
                SELECT count(*) FROM similar_author
                WHERE author_id = similar_author_id
            """,
            "duplicate_similarity_ranks": """
                SELECT count(*) FROM (
                    SELECT author_id, rank FROM similar_author
                    GROUP BY author_id, rank HAVING count(*) > 1
                ) duplicate
            """,
        }
        results = {
            name: self.db.execute(query).fetchone()[0]
            for name, query in checks.items()
        }
        with open(self.output_dir / "validation.json", "w", encoding="utf-8") as handle:
            json.dump(results, handle, indent=2, sort_keys=True)
        failures = {name: count for name, count in results.items() if count != 0}
        if failures:
            raise RuntimeError(f"Canonical catalog validation failed: {failures}")
        return results

    def run(self):
        self.load()
        self.build_work_identity()
        self.converge_work_and_author_identity()
        self.build_canonical_tables()
        self.build_editions_and_featured()
        self.build_prh_metadata()
        self.build_tags_and_profiles()
        self.build_similar_authors()
        self.validate()
        return self.export()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--similar-authors-limit", type=int, default=20)
    parser.add_argument("--minimum-shared-tags", type=int, default=2)
    parser.add_argument("--prh-data-dir", type=Path)
    args = parser.parse_args()
    database = args.database or args.output_dir / "catalog.duckdb"
    builder = CatalogBuilder(
        args.input_dir, args.output_dir, database,
        args.similar_authors_limit, args.minimum_shared_tags, args.prh_data_dir,
    )
    try:
        summary = builder.run()
    finally:
        builder.close()
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
