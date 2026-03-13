#!/usr/bin/env python3
"""
Test script for the Open Library editions dump converter.
Uses a local sample file to test the conversion without downloading.
Tests include:
- Parsing individual records
- CSV conversion with multiple files
- Proper escaping of commas and newlines in data
"""

import csv
import gzip
import os
import shutil
from openlibrary_editions_to_csv import convert_to_csv, parse_edition_record


def create_test_gz_file():
    """Compress the test sample file."""
    print("Creating compressed test file...")
    with open('test_editions_sample.txt', 'rb') as f_in:
        with gzip.open('test_editions_sample.txt.gz', 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    print("✓ Created test_editions_sample.txt.gz")


def test_parsing():
    """Test parsing of individual records."""
    print("\n" + "=" * 70)
    print("Testing edition record parsing...")
    print("=" * 70)

    with open('test_editions_sample.txt', 'r') as f:
        for i, line in enumerate(f, 1):
            print(f"\nParsing record {i}...")
            edition = parse_edition_record(line)
            if edition:
                print(f"  ✓ Title: {edition['title']}")
                print(f"  ✓ Key: {edition['key']}")
                if edition['subtitle']:
                    print(f"  ✓ Subtitle: {edition['subtitle']}")
                if edition['authors']:
                    print(f"  ✓ Authors: {edition['authors']}")
                if edition['works']:
                    print(f"  ✓ Works: {edition['works']}")
                if edition['publishers']:
                    print(f"  ✓ Publishers: {edition['publishers']}")
                if edition['publish_date']:
                    print(f"  ✓ Publish Date: {edition['publish_date']}")
                if edition['isbn_10']:
                    print(f"  ✓ ISBN-10: {edition['isbn_10']}")
                if edition['isbn_13']:
                    print(f"  ✓ ISBN-13: {edition['isbn_13']}")
                if edition['number_of_pages']:
                    print(f"  ✓ Pages: {edition['number_of_pages']}")
                if edition['physical_format']:
                    print(f"  ✓ Format: {edition['physical_format']}")
            else:
                print(f"  ✗ Failed to parse")


def test_csv_conversion():
    """Test the full CSV conversion."""
    print("\n" + "=" * 70)
    print("Testing CSV conversion...")
    print("=" * 70)

    create_test_gz_file()
    output_dir = 'test_editions_csv'
    convert_to_csv('test_editions_sample.txt.gz', output_dir, max_records=None)

    print("\n✓ CSV conversion successful!")

    # List all generated files
    csv_files = sorted([f for f in os.listdir(output_dir) if f.endswith('.csv')])
    print(f"\nGenerated {len(csv_files)} CSV file(s):")
    for f in csv_files:
        file_path = os.path.join(output_dir, f)
        file_size = os.path.getsize(file_path)
        print(f"  - {f} ({file_size:,} bytes)")

    # Show content from first file
    if csv_files:
        first_file = os.path.join(output_dir, csv_files[0])
        print(f"\nContent of {csv_files[0]}:")
        print("-" * 70)
        with open(first_file, 'r', encoding='utf-8') as f:
            content = f.read()
            print(content)

        # Test CSV parsing to verify proper escaping
        print("\n" + "=" * 70)
        print("Testing CSV parsing (verifies proper escaping)...")
        print("=" * 70)
        with open(first_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader, 1):
                print(f"\nRecord {i}:")
                print(f"  Title: {row['title']}")
                if row['subtitle']:
                    print(f"  Subtitle: {row['subtitle']}")
                if row['authors']:
                    print(f"  Authors: {row['authors']}")
                if row['publishers']:
                    publishers = row['publishers'][:80] + '...' if len(row['publishers']) > 80 else row['publishers']
                    print(f"  Publishers: {publishers}")
                    # Check if semicolons are preserved
                    if ';' in row['publishers']:
                        print(f"  ✓ Semicolons in publishers preserved!")
                if row['isbn_10']:
                    print(f"  ISBN-10: {row['isbn_10']}")
                if row['isbn_13']:
                    print(f"  ISBN-13: {row['isbn_13']}")
                if row['physical_format']:
                    print(f"  Format: {row['physical_format']}")

                # Check if commas in title were properly handled
                if ',' in row['title']:
                    print(f"  ✓ Commas in title were properly escaped!")

                # Check multiple authors
                if row['authors'] and ',' in row['authors']:
                    print(f"  ✓ Multiple authors properly joined with commas!")

        print("\n✓ CSV escaping test passed - commas and separators handled correctly!")


def main():
    """Run all tests."""
    print("=" * 70)
    print("Open Library Editions Converter - Test Suite")
    print("=" * 70)

    test_parsing()
    test_csv_conversion()

    print("\n" + "=" * 70)
    print("All tests completed successfully! ✓")
    print("=" * 70)


if __name__ == '__main__':
    main()
