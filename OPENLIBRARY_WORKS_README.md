# Open Library Works Dump to CSV Converter

A Python script that downloads the Open Library works dump and converts it to valid CSV files.

## Overview

Open Library provides monthly data dumps of their entire catalog. This script specifically handles the **works dump**, which contains information about millions of works (the abstract concept of a book, distinct from specific editions).

A "work" represents the idea of a book - for example, "Pride and Prejudice" is a work that has been published in many different editions over the years.

## Data Source

- **Official Documentation**: [Open Library Data Dumps](https://openlibrary.org/developers/dumps)
- **Works Dump URL**: `https://openlibrary.org/data/ol_dump_works_latest.txt.gz`
- **Archive of Past Dumps**: [Internet Archive - Open Library Exports](https://archive.org/details/ol_exports)
- **Schema Documentation**: [Open Library Schema](https://openlibrary.org/about/schema)

## Features

- Downloads the latest works dump (~3.5 GB compressed)
- Parses the tab-separated JSONL format
- Extracts key work information into CSV columns
- **Splits output into multiple files** (10,000 records per file)
- **Proper CSV escaping** for commas and newlines in data
- Handles various data formats (description as string/dict, lists, etc.)
- Shows progress during download and conversion
- Test mode for working with sample data
- Memory-efficient line-by-line processing

## CSV Output Fields

The script extracts the following fields:

| Field | Description |
|-------|-------------|
| `key` | Work's unique Open Library key (e.g., `/works/OL1W`) |
| `type` | Record type (always `/type/work`) |
| `revision` | Revision number of the record |
| `last_modified` | Timestamp of last modification |
| `title` | Work title |
| `subtitle` | Work subtitle (if available) |
| `authors` | Comma-separated list of author keys |
| `subjects` | Semicolon-separated list of subjects (up to 20) |
| `subject_places` | Semicolon-separated list of places (up to 10) |
| `subject_times` | Semicolon-separated list of time periods (up to 10) |
| `description` | Work description/summary |
| `first_publish_date` | Year of first publication |
| `covers` | Comma-separated list of cover IDs (up to 5) |
| `number_of_editions` | Number of editions for this work |

## Usage

### Test Mode (Recommended First Run)

Test with a small sample (10 MB download, 1000 records):

```bash
python3 openlibrary_works_to_csv.py --test
```

### Full Download

Download and convert the entire works dump:

```bash
python3 openlibrary_works_to_csv.py
```

**Note**: The full dump is ~3.5 GB compressed and contains millions of records. The conversion process may take significant time and disk space.

### Output Structure

The script creates a directory named `works_csv/` containing multiple CSV files:

```
works_csv/
├── works_0001.csv  (10,000 records)
├── works_0002.csv  (10,000 records)
├── works_0003.csv  (10,000 records)
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
python3 test_works_converter.py
```

This will:
1. Parse sample work records
2. Convert them to CSV
3. Display the results
4. Verify CSV escaping for commas and newlines

## Data Integrity & CSV Escaping

The script uses Python's `csv.QUOTE_NONNUMERIC` quoting mode to ensure data integrity:

- **Commas in titles**: Properly quoted (e.g., `"Murder Mystery, Vol. 1"`)
- **Newlines in descriptions**: Preserved and escaped correctly
- **Semicolons in subjects**: Preserved (used as separator instead of commas)
- **Special characters**: Handled without corruption

Example of properly escaped data:

```csv
"/works/OL2W","/type/work","2","2009-05-15T10:22:33.123456","Murder Mystery, Vol. 1","","/authors/OL2A, /authors/OL3A","Mystery; Crime; Detective fiction","London; England","Victorian era; 19th century","A gripping detective novel set in Victorian London.","2005","","15"
```

The title with a comma is properly quoted, and semicolons separate subjects to avoid confusion.

## Example Output

```csv
key,type,revision,last_modified,title,subtitle,authors,subjects,subject_places,subject_times,description,first_publish_date,covers,number_of_editions
"/works/OL1W","/type/work","1","2008-04-01T03:28:50.625462","The Great Adventure","A Journey Through Time","/authors/OL1A","Fiction; Adventure; Time Travel; Science Fiction","","","An epic tale of a scientist who discovers time travel.","1998","123456, 789012",""
"/works/OL3W","/type/work","1","2010-06-20T14:15:00.789012","Cooking Basics","","/authors/OL4A","Cooking; Recipes; Food","","","Essential cooking techniques for beginners.","2010","334455","3"
```

## File Format Details

The Open Library works dump uses the following format:
- **Compression**: gzip (.gz)
- **Format**: Tab-separated values with JSON data
- **Columns**: `type`, `key`, `revision`, `last_modified`, `json_data`
- **Encoding**: UTF-8

Each line contains tab-separated fields, with the last field being a JSON object containing the work's detailed information.

## Requirements

- Python 3.6+
- Standard library only (no external dependencies)

## Files

- `openlibrary_works_to_csv.py` - Main conversion script
- `test_works_converter.py` - Test suite for basic functionality and CSV escaping
- `test_works_sample.txt` - Sample data for testing
- `works_csv/` - Output directory containing CSV files (created after running the script)

## Relationship to Authors and Editions

- **Works** represent the abstract idea of a book (this script)
- **Authors** represent the people who created works (see `openlibrary_authors_to_csv.py`)
- **Editions** represent specific published versions of works

The `authors` field in works contains author keys that can be cross-referenced with the authors CSV files.

## Troubleshooting

### Download Fails with 403 Error

If the download fails, you can:
1. Manually download the file from [https://openlibrary.org/data/ol_dump_works_latest.txt.gz](https://openlibrary.org/data/ol_dump_works_latest.txt.gz)
2. Place it in the same directory as the script
3. Run the script again (it will skip the download and use the existing file)

### Memory Issues

For very large files, the script processes line-by-line to minimize memory usage. However, if you encounter issues:
- Use test mode (`--test`) to work with smaller datasets
- Process the dump on a machine with adequate RAM
- Consider splitting the output into smaller batches

## License

This script is provided as-is for working with Open Library data. The Open Library data itself is available under the CC0 license.

## References

- [Open Library](https://openlibrary.org/)
- [Open Library Developer Documentation](https://openlibrary.org/developers)
- [Open Library API](https://openlibrary.org/developers/api)
- [Open Library Data Dumps](https://openlibrary.org/developers/dumps)
- [Open Library Schema](https://openlibrary.org/about/schema)
