## Open Library Editions Dump to CSV Converter

A Python script that downloads the Open Library editions dump and converts it to valid CSV files.

## Overview

Open Library provides monthly data dumps of their entire catalog. This script specifically handles the **editions dump**, which contains information about tens of millions of specific published versions of books.

An "edition" represents a specific published version of a work - for example, the 2020 paperback edition of "Pride and Prejudice" published by Penguin Classics is distinct from the 1995 hardcover edition by Oxford University Press.

## Data Source

- **Official Documentation**: [Open Library Data Dumps](https://openlibrary.org/developers/dumps)
- **Editions Dump URL**: `https://openlibrary.org/data/ol_dump_editions_latest.txt.gz`
- **Archive of Past Dumps**: [Internet Archive - Open Library Exports](https://archive.org/details/ol_exports)
- **Schema Documentation**: [Open Library Schema](https://openlibrary.org/about/schema)

## Features

- Downloads the latest editions dump (~25 GB compressed)
- Parses the tab-separated JSONL format
- Extracts key edition information into CSV columns
- **Splits output into multiple files** (10,000 records per file)
- **Proper CSV escaping** for commas and newlines in data
- Handles various data formats (arrays, nested objects, etc.)
- Shows progress during download and conversion
- Test mode for working with sample data
- Memory-efficient line-by-line processing

## CSV Output Fields

The script extracts the following fields:

| Field | Description |
|-------|-------------|
| `key` | Edition's unique Open Library key (e.g., `/books/OL1M`) |
| `type` | Record type (always `/type/edition`) |
| `revision` | Revision number of the record |
| `last_modified` | Timestamp of last modification |
| `title` | Edition title |
| `subtitle` | Edition subtitle (if available) |
| `authors` | Comma-separated list of author keys |
| `works` | Comma-separated list of work keys |
| `publishers` | Semicolon-separated list of publishers (up to 5) |
| `publish_date` | Publication date |
| `publish_places` | Semicolon-separated list of publication places (up to 5) |
| `isbn_10` | Comma-separated list of ISBN-10 identifiers (up to 3) |
| `isbn_13` | Comma-separated list of ISBN-13 identifiers (up to 3) |
| `lccn` | Library of Congress Control Number |
| `oclc_numbers` | OCLC numbers (up to 3) |
| `number_of_pages` | Number of pages |
| `pagination` | Pagination details (e.g., "xii, 320 p.") |
| `physical_format` | Format (Hardcover, Paperback, etc.) |
| `covers` | Comma-separated list of cover IDs (up to 3) |
| `languages` | Comma-separated language codes |

## Usage

### Test Mode (Recommended First Run)

Test with a small sample (10 MB download, 1000 records):

```bash
python3 openlibrary_editions_to_csv.py --test
```

### Full Download

Download and convert the entire editions dump:

```bash
python3 openlibrary_editions_to_csv.py
```

**WARNING**: The full dump is ~25 GB compressed and contains tens of millions of records. The conversion process may take many hours and require substantial disk space.

### Output Structure

The script creates a directory named `editions_csv/` containing multiple CSV files:

```
editions_csv/
├── editions_0001.csv  (10,000 records)
├── editions_0002.csv  (10,000 records)
├── editions_0003.csv  (10,000 records)
└── ...
```

Each file contains a maximum of 10,000 records with the header row. This makes the output more manageable for:
- Importing into spreadsheet applications
- Processing in batches
- Version control and diffing
- Parallel processing

## Running the Test Suite

To verify the script works correctly with sample data:

```bash
python3 test_editions_converter.py
```

This will:
1. Parse sample edition records
2. Convert them to CSV
3. Display the results
4. Verify CSV escaping for commas and separators

## Data Integrity & CSV Escaping

The script uses Python's `csv.QUOTE_NONNUMERIC` quoting mode to ensure data integrity:

- **Commas in titles**: Properly quoted (e.g., `"Murder Mystery, Vol. 1"`)
- **Semicolons in publishers**: Preserved (used as separator)
- **Multiple authors**: Joined with commas in proper CSV field
- **ISBNs**: Comma-separated within a single field
- **Special characters**: Handled without corruption

Example of properly escaped data:

```csv
"/books/OL2M","/type/edition","2","2009-05-15T10:22:33.123456","Murder Mystery, Vol. 1","","/authors/OL2A, /authors/OL3A","/works/OL2W","Mystery Press","March 2005","London","9876543210","","2005012345","12345678","320","xii, 320 p.","Paperback","789012, 345678","eng"
```

The title with commas is properly quoted, multiple authors are comma-separated, and multiple covers are comma-separated.

## Example Output

```csv
key,type,title,subtitle,authors,works,publishers,publish_date,isbn_10,isbn_13,number_of_pages,physical_format
"/books/OL1M","/type/edition","The Great Adventure: Special Edition","Collector's Edition with Notes","/authors/OL1A","/works/OL1W","Acme Publishing; Global Books Inc.","1998","1234567890","978-1234567890","450","Hardcover"
"/books/OL3M","/type/edition","Cooking Basics","2nd Edition","/authors/OL4A","/works/OL3W","Food & Wine Publishing","2010","","978-1111222233","200","Trade Paperback"
```

## File Format Details

The Open Library editions dump uses the following format:
- **Compression**: gzip (.gz)
- **Format**: Tab-separated values with JSON data
- **Columns**: `type`, `key`, `revision`, `last_modified`, `json_data`
- **Encoding**: UTF-8

Each line contains tab-separated fields, with the last field being a JSON object containing the edition's detailed information.

## Requirements

- Python 3.6+
- Standard library only (no external dependencies)

## Files

- `openlibrary_editions_to_csv.py` - Main conversion script
- `test_editions_converter.py` - Test suite for basic functionality and CSV escaping
- `test_editions_sample.txt` - Sample data for testing
- `editions_csv/` - Output directory containing CSV files (created after running the script)

## Relationship to Works and Authors

- **Editions** represent specific published versions (this script)
- **Works** represent the abstract idea of a book (see `openlibrary_works_to_csv.py`)
- **Authors** represent the people who created works (see `openlibrary_authors_to_csv.py`)

The `works` field in editions contains work keys that can be cross-referenced with the works CSV files. Similarly, the `authors` field contains author keys for cross-referencing.

## Identifiers Explained

- **ISBN-10**: 10-digit International Standard Book Number (older format)
- **ISBN-13**: 13-digit International Standard Book Number (current format)
- **LCCN**: Library of Congress Control Number
- **OCLC**: Online Computer Library Center numbers

These identifiers are crucial for cataloging and can be used to look up additional information about editions.

## Troubleshooting

### Download Fails with 403 Error

If the download fails, you can:
1. Manually download the file from [https://openlibrary.org/data/ol_dump_editions_latest.txt.gz](https://openlibrary.org/data/ol_dump_editions_latest.txt.gz)
2. Place it in the same directory as the script
3. Run the script again (it will skip the download and use the existing file)

### Memory Issues

For very large files, the script processes line-by-line to minimize memory usage. However, if you encounter issues:
- Use test mode (`--test`) to work with smaller datasets
- Process the dump on a machine with adequate RAM (16GB+ recommended for full dump)
- Consider splitting the output into smaller batches

### Disk Space

The full editions dump is very large. Ensure you have:
- ~25 GB for the compressed dump
- ~100+ GB for the extracted CSV files (millions of records)
- Total: 125+ GB free disk space recommended

## License

This script is provided as-is for working with Open Library data. The Open Library data itself is available under the CC0 license.

## References

- [Open Library](https://openlibrary.org/)
- [Open Library Developer Documentation](https://openlibrary.org/developers)
- [Open Library API](https://openlibrary.org/developers/api)
- [Open Library Data Dumps](https://openlibrary.org/developers/dumps)
- [Open Library Schema](https://openlibrary.org/about/schema)
