#!/usr/bin/env python3
"""
Open Library Editions Dump to CSV Converter

Downloads the Open Library editions dump and converts it to valid CSV files.
The editions dump is in JSONL format (one JSON object per line) and compressed with gzip.

An "edition" represents a specific published version of a work (e.g., hardcover, paperback, etc.).

Data source: https://openlibrary.org/developers/dumps
"""

import csv
import gzip
import json
import os
import sys
import urllib.request
from datetime import datetime
from typing import Dict, Any, Optional, List


# URLs for Open Library data dumps
EDITIONS_DUMP_URL = "https://openlibrary.org/data/ol_dump_editions_latest.txt.gz"
DOWNLOAD_FILENAME = "ol_dump_editions_latest.txt.gz"
OUTPUT_DIR = "editions_csv"
MAX_LINES_PER_FILE = 10000


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


def parse_edition_record(line: str) -> Optional[Dict[str, Any]]:
    """
    Parse a line from the editions dump.

    The format is tab-separated with 5 columns:
    type, key, revision, last_modified, json_data

    Args:
        line: A line from the dump file

    Returns:
        Parsed edition data as a dictionary, or None if parsing fails
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
        edition_data = json.loads(json_data)

        # Extract common fields
        result = {
            'key': key,
            'type': record_type,
            'revision': revision,
            'last_modified': last_modified,
            'title': edition_data.get('title', ''),
            'subtitle': edition_data.get('subtitle', ''),
            'authors': '',
            'works': '',
            'publishers': '',
            'publish_date': edition_data.get('publish_date', ''),
            'publish_places': '',
            'isbn_10': '',
            'isbn_13': '',
            'lccn': '',
            'oclc_numbers': '',
            'number_of_pages': '',
            'pagination': edition_data.get('pagination', ''),
            'physical_format': edition_data.get('physical_format', ''),
            'covers': '',
            'languages': '',
        }

        # Handle authors (list of author keys)
        authors = edition_data.get('authors', [])
        if authors:
            author_keys = []
            for author in authors:
                if isinstance(author, dict):
                    author_key = author.get('key', '')
                    if author_key:
                        author_keys.append(author_key)
            result['authors'] = ', '.join(filter(None, author_keys))

        # Handle works (list of work keys)
        works = edition_data.get('works', [])
        if works:
            work_keys = []
            for work in works:
                if isinstance(work, dict):
                    work_key = work.get('key', '')
                    if work_key:
                        work_keys.append(work_key)
            result['works'] = ', '.join(filter(None, work_keys))

        # Handle publishers (list of strings)
        publishers = edition_data.get('publishers', [])
        if publishers and isinstance(publishers, list):
            result['publishers'] = '; '.join(publishers[:5])  # Limit to first 5

        # Handle publish_places
        publish_places = edition_data.get('publish_places', [])
        if publish_places and isinstance(publish_places, list):
            result['publish_places'] = '; '.join(publish_places[:5])

        # Handle ISBN-10
        isbn_10 = edition_data.get('isbn_10', [])
        if isbn_10 and isinstance(isbn_10, list):
            result['isbn_10'] = ', '.join(isbn_10[:3])  # Limit to first 3

        # Handle ISBN-13
        isbn_13 = edition_data.get('isbn_13', [])
        if isbn_13 and isinstance(isbn_13, list):
            result['isbn_13'] = ', '.join(isbn_13[:3])

        # Handle LCCN (Library of Congress Control Number)
        lccn = edition_data.get('lccn', [])
        if lccn:
            if isinstance(lccn, list):
                result['lccn'] = ', '.join(lccn[:2])
            elif isinstance(lccn, str):
                result['lccn'] = lccn

        # Handle OCLC numbers
        oclc = edition_data.get('oclc_numbers', [])
        if oclc and isinstance(oclc, list):
            result['oclc_numbers'] = ', '.join(oclc[:3])

        # Handle number of pages
        if 'number_of_pages' in edition_data:
            num_pages = edition_data.get('number_of_pages')
            if num_pages is not None:
                result['number_of_pages'] = str(num_pages)

        # Handle covers (list of cover IDs)
        covers = edition_data.get('covers', [])
        if covers and isinstance(covers, list):
            # Filter out -1 (placeholder for missing covers)
            valid_covers = [str(c) for c in covers if c != -1]
            if valid_covers:
                result['covers'] = ', '.join(valid_covers[:3])  # Limit to first 3

        # Handle languages
        languages = edition_data.get('languages', [])
        if languages:
            lang_codes = []
            for lang in languages:
                if isinstance(lang, dict):
                    lang_key = lang.get('key', '')
                    # Extract language code from key like "/languages/eng"
                    if lang_key:
                        lang_code = lang_key.split('/')[-1]
                        lang_codes.append(lang_code)
            result['languages'] = ', '.join(filter(None, lang_codes))

        return result

    except (json.JSONDecodeError, IndexError, KeyError) as e:
        # Skip invalid records
        return None


def convert_to_csv(input_file: str, output_dir: str, max_records: Optional[int] = None):
    """
    Convert the gzipped editions dump to CSV format, splitting into multiple files.

    Args:
        input_file: Path to the gzipped dump file
        output_dir: Directory to save CSV files
        max_records: Maximum number of records to process (for testing). None = process all.
    """
    print(f"\nConverting {input_file} to CSV files in {output_dir}/")

    # Create output directory if it doesn't exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}/")

    if max_records:
        print(f"Processing maximum {max_records} records for testing")

    # CSV fields
    fieldnames = [
        'key',
        'type',
        'revision',
        'last_modified',
        'title',
        'subtitle',
        'authors',
        'works',
        'publishers',
        'publish_date',
        'publish_places',
        'isbn_10',
        'isbn_13',
        'lccn',
        'oclc_numbers',
        'number_of_pages',
        'pagination',
        'physical_format',
        'covers',
        'languages',
    ]

    processed = 0
    written = 0
    skipped = 0
    file_number = 1
    current_file_lines = 0
    writer = None
    f_out = None

    try:
        with gzip.open(input_file, 'rt', encoding='utf-8') as f_in:
            for line in f_in:
                processed += 1

                # Parse the record
                edition = parse_edition_record(line)

                if edition:
                    # Create a new file if needed
                    if writer is None or current_file_lines >= MAX_LINES_PER_FILE:
                        # Close previous file if open
                        if f_out is not None:
                            f_out.close()
                            print(f"\n  ✓ Completed: {output_filename} ({current_file_lines:,} records)")

                        # Open new file
                        output_filename = os.path.join(output_dir, f"editions_{file_number:04d}.csv")
                        f_out = open(output_filename, 'w', newline='', encoding='utf-8')
                        # Use QUOTE_NONNUMERIC to ensure commas and newlines in data are properly escaped
                        writer = csv.DictWriter(f_out, fieldnames=fieldnames,
                                              quoting=csv.QUOTE_NONNUMERIC)
                        writer.writeheader()
                        current_file_lines = 0
                        file_number += 1
                        print(f"\nCreating: {output_filename}")

                    writer.writerow(edition)
                    written += 1
                    current_file_lines += 1
                else:
                    skipped += 1

                # Show progress
                if processed % 10000 == 0:
                    print(f"\rProcessed: {processed:,} | Written: {written:,} | Skipped: {skipped:,} | Files: {file_number - 1}", end='')

                # Stop if we've reached the max records for testing
                if max_records and written >= max_records:
                    print(f"\nReached {max_records} record limit")
                    break

        # Close the last file
        if f_out is not None:
            f_out.close()
            print(f"\n  ✓ Completed: {output_filename} ({current_file_lines:,} records)")

        print(f"\n\nConversion complete!")
        print(f"Total processed: {processed:,}")
        print(f"Records written: {written:,}")
        print(f"Records skipped: {skipped:,}")
        print(f"Number of CSV files created: {file_number - 1}")
        print(f"Output directory: {output_dir}/")

        # Show total directory size
        total_size = sum(os.path.getsize(os.path.join(output_dir, f))
                        for f in os.listdir(output_dir) if f.endswith('.csv'))
        print(f"Total size: {total_size / (1024 * 1024):.2f} MB")

    except Exception as e:
        if f_out is not None:
            f_out.close()
        print(f"\nError during conversion: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """Main entry point."""
    print("=" * 70)
    print("Open Library Editions Dump to CSV Converter")
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
        print("This will download and process the entire editions dump (~25 GB compressed)")
        print("WARNING: This is a very large file and will take significant time!")
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
        download_file(EDITIONS_DUMP_URL, DOWNLOAD_FILENAME, max_download_mb)
    else:
        print(f"Using existing file: {DOWNLOAD_FILENAME}")
        print("(Delete this file to re-download)")

    # Convert to CSV
    convert_to_csv(DOWNLOAD_FILENAME, OUTPUT_DIR, max_records)

    print(f"\n✓ Success! CSV files created in directory: {OUTPUT_DIR}/")
    print(f"   Each file contains up to {MAX_LINES_PER_FILE:,} records")

    # Show a sample of the data from the first file
    first_file = None
    if os.path.exists(OUTPUT_DIR):
        csv_files = sorted([f for f in os.listdir(OUTPUT_DIR) if f.endswith('.csv')])
        if csv_files:
            first_file = os.path.join(OUTPUT_DIR, csv_files[0])

    if first_file:
        print(f"\nFirst 3 rows from {csv_files[0]}:")
        print("-" * 70)
        with open(first_file, 'r', encoding='utf-8') as f:
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
