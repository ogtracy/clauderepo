# Open Library Author Dump to CSV Converter

A Python script that downloads the Open Library author dump and converts it to a valid CSV file.

## Overview

Open Library provides monthly data dumps of their entire catalog, including books, authors, works, and more. This script specifically handles the **author dump**, which contains information about millions of authors.

## Data Source

- **Official Documentation**: [Open Library Data Dumps](https://openlibrary.org/developers/dumps)
- **Author Dump URL**: `https://openlibrary.org/data/ol_dump_authors_latest.txt.gz`
- **Archive of Past Dumps**: [Internet Archive - Open Library Exports](https://archive.org/details/ol_exports)

## Features

- Downloads the latest author dump (~1.5 GB compressed)
- Parses the tab-separated JSONL format
- Extracts key author information into CSV columns
- Handles various data formats (bio as string/dict, links, etc.)
- Shows progress during download and conversion
- Test mode for working with sample data

## CSV Output Fields

The script extracts the following fields:

| Field | Description |
|-------|-------------|
| `key` | Author's unique Open Library key (e.g., `/authors/OL1A`) |
| `type` | Record type (always `/type/author`) |
| `revision` | Revision number of the record |
| `last_modified` | Timestamp of last modification |
| `name` | Author's name |
| `personal_name` | Formal name (e.g., "Smith, John") |
| `birth_date` | Birth year or date |
| `death_date` | Death year or date |
| `bio` | Author biography |
| `alternate_names` | Comma-separated list of alternate names |
| `wikipedia` | Wikipedia URL (if available) |
| `website` | Author's website (if available) |

## Usage

### Test Mode (Recommended First Run)

Test with a small sample (10 MB download, 1000 records):

```bash
python3 openlibrary_authors_to_csv.py --test
```

### Full Download

Download and convert the entire author dump:

```bash
python3 openlibrary_authors_to_csv.py
```

**Note**: The full dump is ~1.5 GB compressed and contains millions of records. The conversion process may take significant time and disk space.

## Running the Test Suite

To verify the script works correctly with sample data:

```bash
python3 test_converter.py
```

This will:
1. Parse sample author records
2. Convert them to CSV
3. Display the results

## Example Output

```csv
key,type,revision,last_modified,name,personal_name,birth_date,death_date,bio,alternate_names,wikipedia,website
/authors/OL1A,/type/author,1,2008-04-01T03:28:50.625462,John Smith,"Smith, John",1950,2020,American author known for science fiction novels.,"J. Smith, Jonathan Smith",https://en.wikipedia.org/wiki/John_Smith_(author),
/authors/OL2A,/type/author,2,2009-05-15T10:22:33.123456,Jane Doe,,1965,,British mystery writer,,,https://janedoe.com
```

## File Format Details

The Open Library author dump uses the following format:
- **Compression**: gzip (.gz)
- **Format**: Tab-separated values with JSON data
- **Columns**: `type`, `key`, `revision`, `last_modified`, `json_data`
- **Encoding**: UTF-8

Each line contains tab-separated fields, with the last field being a JSON object containing the author's detailed information.

## Requirements

- Python 3.6+
- Standard library only (no external dependencies)

## Files

- `openlibrary_authors_to_csv.py` - Main conversion script
- `test_converter.py` - Test suite
- `test_authors_sample.txt` - Sample data for testing
- `authors.csv` - Output CSV file (created after running the script)

## Troubleshooting

### Download Fails with 403 Error

If the download fails, you can:
1. Manually download the file from [https://openlibrary.org/data/ol_dump_authors_latest.txt.gz](https://openlibrary.org/data/ol_dump_authors_latest.txt.gz)
2. Place it in the same directory as the script
3. Run the script again (it will skip the download and use the existing file)

### Memory Issues

For very large files, the script processes line-by-line to minimize memory usage. However, if you encounter issues:
- Use test mode (`--test`) to work with smaller datasets
- Process the dump on a machine with adequate RAM
- Consider splitting the output into multiple smaller CSV files

## License

This script is provided as-is for working with Open Library data. The Open Library data itself is available under the CC0 license.

## References

- [Open Library](https://openlibrary.org/)
- [Open Library Developer Documentation](https://openlibrary.org/developers)
- [Open Library API](https://openlibrary.org/developers/api)
