import argparse
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from sample_connected_catalog import build_sample, raw_record, reference_keys


class ConnectedSampleTest(unittest.TestCase):
    def test_sample_relationships_only_reference_selected_works(self):
        repository = Path(__file__).parent
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "sample"
            args = argparse.Namespace(
                authors=repository / "test_authors_sample.txt",
                works=repository / "test_works_sample.txt",
                editions=repository / "test_editions_sample.txt",
                work_count=3,
                max_editions_per_work=25,
                selection="first",
                seed=1,
                output_dir=output,
            )
            manifest = build_sample(args)

            with gzip.open(output / "works.txt.gz", "rt", encoding="utf-8") as handle:
                work_keys = {raw_record(line)[0] for line in handle}
            with gzip.open(output / "editions.txt.gz", "rt", encoding="utf-8") as handle:
                edition_work_keys = {
                    key
                    for line in handle
                    for key in reference_keys(raw_record(line)[1].get("works", []))
                }

            self.assertEqual(manifest["works_written"], 3)
            self.assertTrue(edition_work_keys)
            self.assertTrue(edition_work_keys.issubset(work_keys))
            self.assertTrue((output / "sample_manifest.json").is_file())
            self.assertEqual(
                json.loads((output / "sample_manifest.json").read_text())["works_written"],
                3,
            )


if __name__ == "__main__":
    unittest.main()
