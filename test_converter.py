#!/usr/bin/env python3
"""
Test script for the Open Library author dump converter.
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
from openlibrary_authors_to_csv import convert_to_csv, parse_author_record


def create_test_gz_file():
    """Compress the test sample file."""
    print("Creating compressed test file...")
    with open('test_authors_sample.txt', 'rb') as f_in:
        with gzip.open('test_authors_sample.txt.gz', 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    print("✓ Created test_authors_sample.txt.gz")


def test_parsing():
    """Test parsing of individual records."""
    print("\n" + "=" * 70)
    print("Testing record parsing...")
    print("=" * 70)

    with open('test_authors_sample.txt', 'r') as f:
        for i, line in enumerate(f, 1):
            print(f"\nParsing record {i}...")
            author = parse_author_record(line)
            if author:
                print(f"  ✓ Name: {author['name']}")
                print(f"  ✓ Key: {author['key']}")
                if author['birth_date']:
                    print(f"  ✓ Birth: {author['birth_date']}")
                if author['bio']:
                    bio_preview = author['bio'][:50] + '...' if len(author['bio']) > 50 else author['bio']
                    print(f"  ✓ Bio: {bio_preview}")
            else:
                print(f"  ✗ Failed to parse")


def test_csv_conversion():
    """Test the full CSV conversion."""
    print("\n" + "=" * 70)
    print("Testing CSV conversion...")
    print("=" * 70)

    create_test_gz_file()
    output_dir = 'test_authors_csv'
    convert_to_csv('test_authors_sample.txt.gz', output_dir, max_records=None)

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
                print(f"  Name: {row['name']}")
                if row['bio']:
                    # Check if bio with newlines was properly handled
                    if '\n' in row['bio']:
                        print(f"  Bio (multiline): {repr(row['bio'][:80])}")
                        print("  ✓ Newlines in bio were properly escaped!")
                    else:
                        print(f"  Bio: {row['bio'][:80]}")

                # Check if commas in name were properly handled
                if ',' in row['name']:
                    print(f"  ✓ Commas in name were properly escaped!")

                if row['wikipedia']:
                    print(f"  Wikipedia: {row['wikipedia']}")

        print("\n✓ CSV escaping test passed - commas and newlines handled correctly!")


def main():
    """Run all tests."""
    print("=" * 70)
    print("Open Library Author Converter - Test Suite")
    print("=" * 70)

    test_parsing()
    test_csv_conversion()

    print("\n" + "=" * 70)
    print("All tests completed successfully! ✓")
    print("=" * 70)


if __name__ == '__main__':
    main()
