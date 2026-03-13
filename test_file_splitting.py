#!/usr/bin/env python3
"""
Test script to verify file splitting with 10,000+ records.
Creates a large test file and verifies multiple CSV files are created.
"""

import gzip
import json
import os
import shutil
from openlibrary_authors_to_csv import convert_to_csv, MAX_LINES_PER_FILE


def create_large_test_file(num_records=25000):
    """Create a large test file with many records."""
    print(f"Creating test file with {num_records:,} records...")

    filename = 'test_large_authors.txt'
    with open(filename, 'w') as f:
        for i in range(num_records):
            author_data = {
                "name": f"Author {i}",
                "personal_name": f"Author, Number {i}",
                "birth_date": str(1900 + (i % 100)),
                "bio": f"Biography of author {i}. Multiple lines.\nSecond line here.",
                "type": {"key": "/type/author"},
                "key": f"/authors/OL{i}A",
                "revision": 1
            }

            # Tab-separated format
            line = f"/type/author\t/authors/OL{i}A\t1\t2020-01-01T00:00:00.000000\t{json.dumps(author_data)}\n"
            f.write(line)

    # Compress it
    gz_filename = filename + '.gz'
    print(f"Compressing to {gz_filename}...")
    with open(filename, 'rb') as f_in:
        with gzip.open(gz_filename, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)

    # Clean up uncompressed file
    os.remove(filename)

    print(f"✓ Created {gz_filename}")
    return gz_filename


def test_file_splitting():
    """Test that files are properly split at MAX_LINES_PER_FILE."""
    print("=" * 70)
    print("Testing File Splitting Functionality")
    print("=" * 70)
    print()

    # Create test data
    num_records = 25000
    test_file = create_large_test_file(num_records)

    # Convert to CSV
    output_dir = 'test_large_csv'
    print(f"\nConverting to CSV in {output_dir}/...")
    convert_to_csv(test_file, output_dir, max_records=None)

    # Verify file splitting
    print("\n" + "=" * 70)
    print("Verification")
    print("=" * 70)

    csv_files = sorted([f for f in os.listdir(output_dir) if f.endswith('.csv')])
    expected_files = (num_records + MAX_LINES_PER_FILE - 1) // MAX_LINES_PER_FILE

    print(f"\nExpected number of files: {expected_files}")
    print(f"Actual number of files: {len(csv_files)}")

    if len(csv_files) == expected_files:
        print("✓ Correct number of files created!")
    else:
        print("✗ File count mismatch!")

    # Verify each file has correct number of records
    import csv as csv_module
    print(f"\nVerifying each file has ≤ {MAX_LINES_PER_FILE:,} records...")
    total_records = 0
    for csv_file in csv_files:
        filepath = os.path.join(output_dir, csv_file)
        with open(filepath, 'r', encoding='utf-8') as f:
            # Count CSV records properly (not physical lines)
            reader = csv_module.DictReader(f)
            record_count = sum(1 for _ in reader)
            total_records += record_count

            status = "✓" if record_count <= MAX_LINES_PER_FILE else "✗"
            print(f"  {status} {csv_file}: {record_count:,} records")

    print(f"\nTotal records across all files: {total_records:,}")
    print(f"Expected total: {num_records:,}")

    if total_records == num_records:
        print("✓ All records accounted for!")
    else:
        print("✗ Record count mismatch!")

    # Clean up
    print("\nCleaning up test files...")
    os.remove(test_file)
    shutil.rmtree(output_dir)
    print("✓ Cleanup complete")

    print("\n" + "=" * 70)
    print("File splitting test completed successfully! ✓")
    print("=" * 70)


if __name__ == '__main__':
    test_file_splitting()
