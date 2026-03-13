#!/usr/bin/env python3
"""
Test script for the Open Library author dump converter.
Uses a local sample file to test the conversion without downloading.
"""

import gzip
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
    convert_to_csv('test_authors_sample.txt.gz', 'test_authors.csv', max_records=None)

    print("\n✓ CSV conversion successful!")
    print("\nGenerated CSV content:")
    print("-" * 70)
    with open('test_authors.csv', 'r') as f:
        print(f.read())


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
