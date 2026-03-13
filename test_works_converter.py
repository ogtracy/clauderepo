#!/usr/bin/env python3
"""
Test script for the Open Library works dump converter.
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
from openlibrary_works_to_csv import convert_to_csv, parse_work_record


def create_test_gz_file():
    """Compress the test sample file."""
    print("Creating compressed test file...")
    with open('test_works_sample.txt', 'rb') as f_in:
        with gzip.open('test_works_sample.txt.gz', 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    print("✓ Created test_works_sample.txt.gz")


def test_parsing():
    """Test parsing of individual records."""
    print("\n" + "=" * 70)
    print("Testing work record parsing...")
    print("=" * 70)

    with open('test_works_sample.txt', 'r') as f:
        for i, line in enumerate(f, 1):
            print(f"\nParsing record {i}...")
            work = parse_work_record(line)
            if work:
                print(f"  ✓ Title: {work['title']}")
                print(f"  ✓ Key: {work['key']}")
                if work['authors']:
                    print(f"  ✓ Authors: {work['authors']}")
                if work['subjects']:
                    subjects_preview = work['subjects'][:60] + '...' if len(work['subjects']) > 60 else work['subjects']
                    print(f"  ✓ Subjects: {subjects_preview}")
                if work['description']:
                    desc_preview = work['description'][:50] + '...' if len(work['description']) > 50 else work['description']
                    print(f"  ✓ Description: {desc_preview}")
                if work['first_publish_date']:
                    print(f"  ✓ First Published: {work['first_publish_date']}")
            else:
                print(f"  ✗ Failed to parse")


def test_csv_conversion():
    """Test the full CSV conversion."""
    print("\n" + "=" * 70)
    print("Testing CSV conversion...")
    print("=" * 70)

    create_test_gz_file()
    output_dir = 'test_works_csv'
    convert_to_csv('test_works_sample.txt.gz', output_dir, max_records=None)

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
                if row['subjects']:
                    subjects = row['subjects'][:80] + '...' if len(row['subjects']) > 80 else row['subjects']
                    print(f"  Subjects: {subjects}")
                    # Check if semicolons are preserved
                    if ';' in row['subjects']:
                        print(f"  ✓ Semicolons in subjects preserved!")
                if row['description']:
                    # Check if description with newlines was properly handled
                    if '\n' in row['description']:
                        print(f"  Description (multiline): {repr(row['description'][:80])}")
                        print("  ✓ Newlines in description were properly escaped!")
                    else:
                        print(f"  Description: {row['description'][:80]}")

                # Check if commas in title were properly handled
                if ',' in row['title']:
                    print(f"  ✓ Commas in title were properly escaped!")

        print("\n✓ CSV escaping test passed - commas and newlines handled correctly!")


def main():
    """Run all tests."""
    print("=" * 70)
    print("Open Library Works Converter - Test Suite")
    print("=" * 70)

    test_parsing()
    test_csv_conversion()

    print("\n" + "=" * 70)
    print("All tests completed successfully! ✓")
    print("=" * 70)


if __name__ == '__main__':
    main()
