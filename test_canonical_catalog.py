import csv
import json
import os
import tempfile
import unittest
from pathlib import Path

from canonical_catalog import CatalogBuilder, normalized_isbn
from openlibrary_authors_to_csv import parse_author_record
from openlibrary_editions_to_csv import parse_edition_record
from openlibrary_works_to_csv import parse_work_record
from run_small_catalog_pipeline import parse_subset
from transform_authors_to_work_creator import transform_files as transform_authors
from transform_editions_to_work_editions import transform_files as transform_editions
from transform_works_to_quillent_work import transform_files as transform_works


def dump_line(record_type, key, data):
    return "\t".join(
        [record_type, key, "1", "2026-01-01T00:00:00", json.dumps(data)]
    )


def write_dump(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


class CanonicalCatalogTest(unittest.TestCase):
    def test_isbn_validation(self):
        self.assertEqual(normalized_isbn("978-0-306-40615-7"), "9780306406157")
        self.assertEqual(normalized_isbn("0-306-40615-2"), "9780306406157")
        self.assertEqual(normalized_isbn("978-0-306-40615-8"), "")

    def test_duplicate_work_and_author_merge_is_auditable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authors_dump = root / "authors.txt"
            works_dump = root / "works.txt"
            editions_dump = root / "editions.txt"
            write_dump(authors_dump, [
                dump_line("/type/author", "/authors/OLA", {
                    "name": "Jane Example", "birth_date": "1970",
                    "links": [{"url": "https://en.wikipedia.org/wiki/Jane_Example"}],
                }),
                dump_line("/type/author", "/authors/OLB", {
                    "name": "Jane Example", "birth_date": "1970",
                    "links": [{"url": "https://en.wikipedia.org/wiki/Jane_Example/"}],
                }),
                dump_line("/type/author", "/authors/OLC", {
                    "name": "Other Writer",
                }),
                dump_line("/type/author", "/authors/OLD", {
                    "name": "Jane Example", "birth_date": "1988",
                }),
            ])
            write_dump(works_dump, [
                dump_line("/type/work", "/works/OLW1", {
                    "title": "The Same Book", "first_publish_date": "2000",
                    "authors": [{"author": {"key": "/authors/OLA"}}],
                    "subjects": ["Fantasy", "Magic, myth; and legend"],
                }),
                dump_line("/type/work", "/works/OLW2", {
                    "title": "The Same Book", "first_publish_date": "2000",
                    "authors": [{"author": {"key": "/authors/OLB"}}],
                    "subjects": ["Fantasy", "Magic, myth; and legend"],
                }),
                dump_line("/type/work", "/works/OLW3", {
                    "title": "A Different Book", "first_publish_date": "2010",
                    "authors": [{"author": {"key": "/authors/OLC"}}],
                    "subjects": ["Fantasy", "Adventure"],
                }),
            ])
            write_dump(editions_dump, [
                dump_line("/type/edition", "/books/OLE1", {
                    "title": "The Same Book", "publish_date": "2000",
                    "works": [{"key": "/works/OLW1"}],
                    "authors": [{"key": "/authors/OLA"}],
                    "isbn_13": ["978-0-306-40615-7"],
                }),
                dump_line("/type/edition", "/books/OLE2", {
                    "title": "The Same Book", "publish_date": "2001",
                    "works": [{"key": "/works/OLW2"}],
                    "authors": [{"key": "/authors/OLB"}],
                    "isbn_13": ["9780306406157"],
                }),
                dump_line("/type/edition", "/books/OLE3", {
                    "title": "A Different Book", "publish_date": "2010",
                    "works": [{"key": "/works/OLW3"}],
                    "authors": [{"key": "/authors/OLC"}],
                    "isbn_13": ["9783161484100"],
                }),
            ])

            parsed = root / "parsed"
            transformed = root / "transformed"
            output = root / "canonical"
            parse_subset(authors_dump, parsed / "authors_csv/authors_0001.csv", parse_author_record, 10)
            parse_subset(works_dump, parsed / "works_csv/works_0001.csv", parse_work_record, 10)
            parse_subset(editions_dump, parsed / "editions_csv/editions_0001.csv", parse_edition_record, 10)
            transform_authors(str(parsed / "authors_csv"), str(transformed / "work_creator_csv"))
            transform_works(str(parsed / "works_csv"), str(transformed / "quillent_work_csv"))
            transform_editions(
                str(parsed / "editions_csv"),
                str(transformed / "work_editions_csv"),
                work_mapping=None,
            )

            prh = root / "prh_data/normalized"
            write_jsonl(prh / "authors.jsonl", [{
                "prh_author_id": 42, "display": "Jane Example",
                "first": "Jane", "last": "Example", "company_key": None,
                "client_source_id": None, "prh_url": "/authors/jane-example",
            }])
            write_jsonl(prh / "works.jsonl", [{
                "prh_work_id": 900, "available": True,
                "title": "The Same Book", "subtitle": None,
                "prh_display_title": "The Same Book", "first_onsale": "2000-01-01",
                "current_onsale": "2000-01-01", "language": "eng",
                "prh_url": "/books/the-same-book", "about_the_book_html": "About",
                "keynote_html": None, "positioning_html": None, "awards": {},
                "frontlistiest_isbn": "9780306406157", "isbn_counts": {"total": 1},
            }])
            write_jsonl(prh / "editions.jsonl", [{
                "prh_work_id": 900, "isbn": "9780306406157", "isbn10": "0306406152",
                "title": "The Same Book", "subtitle": None,
                "author_display": "Jane Example", "publication_date": "2000-01-01",
                "pages": 250, "trim_size": "6 x 9", "format_family": "Hardcover",
                "format_code": "HC", "format_name": "Hardcover", "version": None,
                "language": "eng", "imprint_code": "EX", "imprint_name": "Example",
                "asin": None, "cover_url": "https://example.test/cover.jpg",
                "prh_url": "/books/the-same-book", "series_code": "SER1",
                "series_name": "Example Series", "series_position": "1",
                "subjects": ["Epic Fantasy"], "custom_subject_category": None,
                "sales_restriction": None, "raw_flags": [],
            }])
            contributor = {
                "prh_work_id": 900, "prh_author_id": 42,
                "display": "Jane Example", "role_code": "A01",
                "role_description": "Author", "primary_flag": True,
                "observed_isbns": ["9780306406157"],
            }
            write_jsonl(prh / "work_contributors.jsonl", [contributor])
            write_jsonl(prh / "edition_contributors.jsonl", [{
                **contributor, "isbn": "9780306406157", "ordinal": 1,
            }])
            write_jsonl(prh / "series.jsonl", [{
                "prh_series_code": "SER1", "available": True,
                "name": "Example Series", "description_html": None,
                "series_count": 1, "series_date": None, "is_numbered": True,
                "is_kids": False, "prh_url": "/series/example",
            }])
            write_jsonl(prh / "work_series.jsonl", [{
                "prh_series_code": "SER1", "prh_work_id": 900,
                "position": "1", "title": "The Same Book",
                "first_onsale": "2000-01-01",
            }])
            write_jsonl(prh / "keywords.jsonl", [{
                "prh_work_id": 900, "isbn": "9780306406157",
                "available": True, "raw_keywords": ["dragons"],
                "candidates": ["dragons"],
            }])

            builder = CatalogBuilder(
                transformed, output, output / "catalog.duckdb",
                minimum_shared_tags=1,
                prh_data_dir=prh,
            )
            try:
                summary = builder.run()
            finally:
                builder.close()

            def rows(filename):
                with open(output / filename, encoding="utf-8", newline="") as handle:
                    return list(csv.DictReader(handle))

            works = rows("works.csv")
            authors = rows("authors.csv")
            work_aliases = rows("work_external_identifiers.csv")
            author_aliases = rows("author_external_identifiers.csv")
            edition_aliases = rows("edition_external_identifiers.csv")
            edition_identifiers = rows("edition_identifiers.csv")
            work_audit = rows("work_merge_audit.csv")
            author_audit = rows("author_merge_audit.csv")
            author_candidates = rows("author_merge_candidates.csv")
            tags = rows("tags.csv")
            profiles = rows("author_tag_profiles.csv")
            states = rows("author_profile_state.csv")
            similar = rows("similar_authors.csv")
            work_tag_sources = rows("work_tag_sources.csv")
            work_contributors = rows("work_contributors.csv")
            series = rows("series.csv")
            validation = json.loads(
                (output / "validation.json").read_text(encoding="utf-8")
            )

        self.assertEqual(summary["works"], 2)
        self.assertEqual(summary["authors"], 3)
        self.assertEqual(summary["editions"], 2)
        self.assertTrue(all(row["featured_edition_fk"] for row in works))
        self.assertEqual(len(work_aliases), 4)
        self.assertEqual(len(author_aliases), 5)
        self.assertEqual(len(edition_aliases), 4)
        self.assertEqual(len(edition_identifiers), 4)
        self.assertIn("prh", {row["provider"] for row in work_aliases})
        self.assertIn("prh", {row["provider"] for row in author_aliases})
        self.assertIn("shared_valid_isbn", {row["match_rule"] for row in work_audit})
        self.assertIn("shared_external_link", {row["match_rule"] for row in author_audit})
        self.assertTrue(any(
            "/authors/OLD" in json.loads(row["sample_source_keys"])
            for row in author_candidates
        ))
        self.assertIn("magic, myth; and legend", {row["tag_name"] for row in tags})
        self.assertIn("prh", {row["provider"] for row in work_tag_sources})
        self.assertEqual(work_contributors[0]["role_description"], "Author")
        self.assertEqual(series[0]["name"], "Example Series")
        self.assertTrue(profiles)
        self.assertEqual(len(states), 3)
        self.assertTrue(similar)
        self.assertTrue(all(json.loads(row["shared_tags"]) for row in similar))
        self.assertTrue(all(value == 0 for value in validation.values()))


if __name__ == "__main__":
    unittest.main()
