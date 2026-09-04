import csv
import json
import os
import tempfile
import unittest

from openlibrary_editions_to_csv import parse_edition_record
from openlibrary_authors_to_csv import parse_author_record
from openlibrary_works_to_csv import parse_work_record
from process_tags import clean_tag
from audit_tags import audit_tags
from transform_editions_to_work_editions import transform_files as transform_editions
from transform_authors_to_work_creator import transform_files as transform_authors
from transform_works_to_quillent_work import transform_files as transform_works


def dump_line(record_type, key, data):
    return "\t".join(
        [record_type, key, "1", "2026-01-01T00:00:00", json.dumps(data)]
    )


def write_dict_csv(path, row):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)


class LosslessCollectionTest(unittest.TestCase):
    def test_author_alternate_names_remain_distinct(self):
        author = parse_author_record(dump_line(
            "/type/author",
            "/authors/OL1A",
            {
                "name": "Example Author",
                "alternate_names": ["Author, Example", "Example; A."],
                "links": [{"title": "Wikipedia", "url": "https://example.test/wiki"}],
            },
        ))
        self.assertEqual(
            json.loads(author["alternate_names"]),
            ["Author, Example", "Example; A."],
        )

        with tempfile.TemporaryDirectory() as root:
            input_dir = os.path.join(root, "in")
            output_dir = os.path.join(root, "out")
            os.makedirs(input_dir)
            write_dict_csv(os.path.join(input_dir, "authors_0001.csv"), author)
            transform_authors(input_dir, output_dir)
            with open(os.path.join(output_dir, "author_alternate_names.csv"),
                      encoding="utf-8", newline="") as handle:
                names = list(csv.DictReader(handle))

        self.assertEqual(
            [row["alternate_name"] for row in names],
            ["Author, Example", "Example; A."],
        )

    def test_work_subject_punctuation_is_not_a_delimiter(self):
        subject = "History, criticism; theory / practice: an introduction"
        work = parse_work_record(dump_line(
            "/type/work",
            "/works/OL1W",
            {
                "title": "Example",
                "authors": [{"author": {"key": "/authors/OL1A"}}],
                "subjects": [subject, "Fantasy"],
                "covers": [10, -1, 20],
            },
        ))

        self.assertEqual(json.loads(work["subjects"]), [subject, "Fantasy"])
        self.assertEqual(json.loads(work["authors"]), ["/authors/OL1A"])
        self.assertEqual(json.loads(work["covers"]), [10, 20])
        self.assertEqual(
            clean_tag(subject),
            "history, criticism; theory / practice: an introduction",
        )

    def test_work_transform_emits_one_row_per_relationship(self):
        work = parse_work_record(dump_line(
            "/type/work",
            "/works/OL1W",
            {
                "title": "Example",
                "authors": [
                    {"author": {"key": "/authors/OL1A"}},
                    {"author": {"key": "/authors/OL2A"}},
                ],
                "subjects": ["A, B", "C; D"],
                "covers": [10, 20],
            },
        ))

        with tempfile.TemporaryDirectory() as root:
            input_dir = os.path.join(root, "in")
            output_dir = os.path.join(root, "out")
            os.makedirs(input_dir)
            write_dict_csv(os.path.join(input_dir, "works_0001.csv"), work)
            transform_works(input_dir, output_dir)

            with open(os.path.join(output_dir, "work_subjects.csv"),
                      encoding="utf-8", newline="") as handle:
                subjects = list(csv.DictReader(handle))
            with open(os.path.join(output_dir, "work_authors.csv"),
                      encoding="utf-8", newline="") as handle:
                authors = list(csv.DictReader(handle))

        self.assertEqual([row["subject"] for row in subjects], ["A, B", "C; D"])
        self.assertEqual(
            [row["author_external_id"] for row in authors],
            ["/authors/OL1A", "/authors/OL2A"],
        )

    def test_tag_audit_keeps_one_punctuated_subject_as_one_tag(self):
        with tempfile.TemporaryDirectory() as root:
            input_file = os.path.join(root, "work_subjects.csv")
            output_file = os.path.join(root, "tag_audit.csv")
            with open(input_file, "w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=[
                    "work_id", "work_external_id", "subject",
                ])
                writer.writeheader()
                writer.writerow({
                    "work_id": 1,
                    "work_external_id": "/works/OL1W",
                    "subject": "History, criticism; theory / practice",
                })
            counts = audit_tags(input_file, output_file)
            with open(output_file, encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(counts["rows"], 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["normalized_tag"],
            "history, criticism; theory / practice",
        )

    def test_edition_transform_preserves_all_identifiers_and_links(self):
        edition = parse_edition_record(dump_line(
            "/type/edition",
            "/books/OL1M",
            {
                "title": "Example",
                "works": [{"key": "/works/OL1W"}, {"key": "/works/OL2W"}],
                "authors": [{"key": "/authors/OL1A"}],
                "isbn_10": ["123456789X", "1111111111"],
                "isbn_13": ["9781234567897"],
                "publishers": ["Alpha; Beta", "Gamma, Inc."],
                "covers": [30, 40],
                "languages": [{"key": "/languages/eng"}],
            },
        ))

        with tempfile.TemporaryDirectory() as root:
            input_dir = os.path.join(root, "in")
            output_dir = os.path.join(root, "out")
            os.makedirs(input_dir)
            write_dict_csv(os.path.join(input_dir, "editions_0001.csv"), edition)
            transform_editions(
                input_dir, output_dir, {"OL1W": 1, "OL2W": 2}
            )

            def rows(filename):
                with open(os.path.join(output_dir, filename),
                          encoding="utf-8", newline="") as handle:
                    return list(csv.DictReader(handle))

            works = rows("edition_works.csv")
            identifiers = rows("edition_identifiers.csv")
            publishers = rows("edition_publishers.csv")

        self.assertEqual(
            [row["work_external_id"] for row in works],
            ["/works/OL1W", "/works/OL2W"],
        )
        self.assertEqual(len(identifiers), 3)
        self.assertEqual(
            [row["publisher"] for row in publishers],
            ["Alpha; Beta", "Gamma, Inc."],
        )


if __name__ == "__main__":
    unittest.main()
