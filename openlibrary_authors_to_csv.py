#!/usr/bin/env python3
"""
Open Library Author Dump to CSV Converter

Downloads the Open Library author dump and converts it to a valid CSV file.
The author dump is in JSONL format (one JSON object per line) and compressed with gzip.

Data source: https://openlibrary.org/developers/dumps
"""

import csv
import gzip
import json
import os
import sys
import urllib.request
from datetime import datetime
from typing import Dict, Any, Optional


# URLs for Open Library data dumps
AUTHOR_DUMP_URL = "https://openlibrary.org/data/ol_dump_authors_latest.txt.gz"
DOWNLOAD_FILENAME = "ol_dump_authors_latest.txt.gz"
OUTPUT_CSV = "authors.csv"


def download_file(url: str, filename: str, max_size_mb: Optional[int] = None) -> str:
    """
    Download a file from a URL with progress indication.

    Args:
        url: URL to download from
        filename: Local filename to save to
        max_size_mb: Maximum size in MB to download (for testing). None = download all.

    Returns:
        Path to the downloaded file
    """
    print(f"Downloading from: {url}")
    print(f"Saving to: {filename}")

    try:
        with urllib.request.urlopen(url) as response:
            total_size = int(response.headers.get('content-length', 0))

            if max_size_mb:
                max_bytes = max_size_mb * 1024 * 1024
                print(f"Limiting download to {max_size_mb} MB for testing")
                total_size = min(total_size, max_bytes)

            downloaded = 0
            chunk_size = 8192

            with open(filename, 'wb') as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break

                    f.write(chunk)
                    downloaded += len(chunk)

                    # Show progress
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        mb_downloaded = downloaded / (1024 * 1024)
                        mb_total = total_size / (1024 * 1024)
                        print(f"\rProgress: {percent:.1f}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)", end='')
                    else:
                        mb_downloaded = downloaded / (1024 * 1024)
                        print(f"\rDownloaded: {mb_downloaded:.1f} MB", end='')

                    # Stop if we've reached the max size for testing
                    if max_size_mb and downloaded >= max_bytes:
                        print(f"\nReached {max_size_mb} MB limit")
                        break

            print(f"\nDownload complete: {filename}")
            return filename

    except urllib.error.URLError as e:
        print(f"\nError downloading file: {e}")
        sys.exit(1)


def parse_author_record(line: str) -> Optional[Dict[str, Any]]:
    """
    Parse a line from the author dump.

    The format is tab-separated with 5 columns:
    type, key, revision, last_modified, json_data

    Args:
        line: A line from the dump file

    Returns:
        Parsed author data as a dictionary, or None if parsing fails
    """
    try:
        parts = line.strip().split('\t')
        if len(parts) < 5:
            return None

        record_type = parts[0]
        key = parts[1]
        revision = parts[2]
        last_modified = parts[3]
        json_data = parts[4]

        # Parse the JSON data
        author_data = json.loads(json_data)

        # Extract common fields
        result = {
            'key': key,
            'type': record_type,
            'revision': revision,
            'last_modified': last_modified,
            'name': author_data.get('name', ''),
            'personal_name': author_data.get('personal_name', ''),
            'birth_date': author_data.get('birth_date', ''),
            'death_date': author_data.get('death_date', ''),
            'bio': '',
            'wikipedia': '',
            'website': '',
        }

        # Handle bio (can be a string or dict)
        bio = author_data.get('bio')
        if isinstance(bio, dict):
            result['bio'] = bio.get('value', '')
        elif isinstance(bio, str):
            result['bio'] = bio

        # Handle links/alternate names
        links = author_data.get('links', [])
        for link in links:
            if isinstance(link, dict):
                url = link.get('url', '')
                if 'wikipedia.org' in url:
                    result['wikipedia'] = url
                    break

        # Get website/homepage
        if 'website' in author_data:
            result['website'] = author_data.get('website', '')

        # Handle alternate names
        alternate_names = author_data.get('alternate_names', [])
        if alternate_names:
            result['alternate_names'] = ', '.join(alternate_names)
        else:
            result['alternate_names'] = ''

        return result

    except (json.JSONDecodeError, IndexError, KeyError) as e:
        # Skip invalid records
        return None


def convert_to_csv(input_file: str, output_file: str, max_records: Optional[int] = None):
    """
    Convert the gzipped author dump to CSV format.

    Args:
        input_file: Path to the gzipped dump file
        output_file: Path to the output CSV file
        max_records: Maximum number of records to process (for testing). None = process all.
    """
    print(f"\nConverting {input_file} to {output_file}")

    if max_records:
        print(f"Processing maximum {max_records} records for testing")

    # CSV fields
    fieldnames = [
        'key',
        'type',
        'revision',
        'last_modified',
        'name',
        'personal_name',
        'birth_date',
        'death_date',
        'bio',
        'alternate_names',
        'wikipedia',
        'website',
    ]

    processed = 0
    written = 0
    skipped = 0

    try:
        with gzip.open(input_file, 'rt', encoding='utf-8') as f_in:
            with open(output_file, 'w', newline='', encoding='utf-8') as f_out:
                writer = csv.DictWriter(f_out, fieldnames=fieldnames)
                writer.writeheader()

                for line in f_in:
                    processed += 1

                    # Parse the record
                    author = parse_author_record(line)

                    if author:
                        writer.writerow(author)
                        written += 1
                    else:
                        skipped += 1

                    # Show progress
                    if processed % 10000 == 0:
                        print(f"\rProcessed: {processed:,} | Written: {written:,} | Skipped: {skipped:,}", end='')

                    # Stop if we've reached the max records for testing
                    if max_records and written >= max_records:
                        print(f"\nReached {max_records} record limit")
                        break

        print(f"\n\nConversion complete!")
        print(f"Total processed: {processed:,}")
        print(f"Records written: {written:,}")
        print(f"Records skipped: {skipped:,}")
        print(f"Output file: {output_file}")

        # Show file size
        file_size = os.path.getsize(output_file) / (1024 * 1024)
        print(f"Output size: {file_size:.2f} MB")

    except Exception as e:
        print(f"\nError during conversion: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    print("=" * 70)
    print("Open Library Author Dump to CSV Converter")
    print("=" * 70)
    print()

    # Check if we're in test mode
    test_mode = '--test' in sys.argv

    if test_mode:
        print("Running in TEST MODE")
        print("- Download limited to 10 MB")
        print("- Processing limited to 1000 records")
        print()
        max_download_mb = 10
        max_records = 1000
    else:
        print("Running in FULL MODE")
        print("This will download and process the entire author dump (~1.5 GB compressed)")
        print("Add --test flag to run in test mode with limited data")
        print()
        response = input("Continue with full download? (y/n): ")
        if response.lower() != 'y':
            print("Aborted.")
            sys.exit(0)
        max_download_mb = None
        max_records = None

    # Download the dump file if it doesn't exist
    if not os.path.exists(DOWNLOAD_FILENAME):
        download_file(AUTHOR_DUMP_URL, DOWNLOAD_FILENAME, max_download_mb)
    else:
        print(f"Using existing file: {DOWNLOAD_FILENAME}")
        print("(Delete this file to re-download)")

    # Convert to CSV
    convert_to_csv(DOWNLOAD_FILENAME, OUTPUT_CSV, max_records)

    print(f"\n✓ Success! CSV file created: {OUTPUT_CSV}")

    # Show a sample of the data
    print("\nFirst 3 rows of the CSV:")
    print("-" * 70)
    with open(OUTPUT_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= 3:
                break
            print(f"\nRecord {i+1}:")
            for key, value in row.items():
                if value:  # Only show non-empty fields
                    # Truncate long values
                    display_value = value[:100] + '...' if len(value) > 100 else value
                    print(f"  {key}: {display_value}")


if __name__ == '__main__':
    main()
