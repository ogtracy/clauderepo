import gzip
import tempfile
import unittest
from pathlib import Path

from download_and_build_catalog import same_remote_version, validate_gzip


class DownloadAndBuildTest(unittest.TestCase):
    def test_remote_version_detects_changed_etag_or_length(self):
        original = {"etag": "one", "last_modified": "date", "length": 100}
        self.assertTrue(same_remote_version(original, dict(original)))
        self.assertFalse(same_remote_version(original, {**original, "etag": "two"}))
        self.assertFalse(same_remote_version(original, {**original, "length": 101}))

    def test_gzip_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            valid = Path(temporary) / "valid.gz"
            invalid = Path(temporary) / "invalid.gz"
            with gzip.open(valid, "wb") as handle:
                handle.write(b"catalog")
            invalid.write_bytes(b"not gzip")
            validate_gzip(valid)
            with self.assertRaises(RuntimeError):
                validate_gzip(invalid)


if __name__ == "__main__":
    unittest.main()
