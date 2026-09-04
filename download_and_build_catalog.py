#!/usr/bin/env python3
"""Download Open Library dumps and build the final canonical CSV bundle."""

import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from openlibrary_authors_to_csv import AUTHOR_DUMP_URL
from openlibrary_editions_to_csv import EDITIONS_DUMP_URL
from openlibrary_works_to_csv import WORKS_DUMP_URL


DUMPS = (
    ("authors", AUTHOR_DUMP_URL, "ol_dump_authors_latest.txt.gz"),
    ("works", WORKS_DUMP_URL, "ol_dump_works_latest.txt.gz"),
    ("editions", EDITIONS_DUMP_URL, "ol_dump_editions_latest.txt.gz"),
)


def gibibytes(byte_count: int) -> float:
    return byte_count / (1024 ** 3)


def require_free_space(path: Path, minimum_gb: float):
    path.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(path).free
    required = int(minimum_gb * (1024 ** 3))
    if free < required:
        raise RuntimeError(
            f"Only {gibibytes(free):.1f} GiB is free at {path}; "
            f"at least {minimum_gb:.1f} GiB was requested"
        )
    print(f"Disk preflight: {gibibytes(free):.1f} GiB free")


def remote_metadata(url: str, timeout: int):
    request = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        length = response.headers.get("Content-Length")
        return {
            "length": int(length) if length else None,
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
            "url": url,
        }


def same_remote_version(saved: dict, current: dict) -> bool:
    for key in ("etag", "last_modified", "length"):
        if saved.get(key) is not None and current.get(key) is not None:
            if saved[key] != current[key]:
                return False
    return True


def validate_gzip(path: Path):
    with path.open("rb") as handle:
        if handle.read(2) != b"\x1f\x8b":
            raise RuntimeError(f"Downloaded file is not gzip data: {path}")
    # Read through EOF so gzip verifies its trailer CRC and uncompressed size.
    with gzip.open(path, "rb") as handle:
        while handle.read(8 * 1024 * 1024):
            pass


def download_once(url: str, destination: Path, timeout: int):
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    metadata_path = destination.with_name(destination.name + ".part.json")
    verified_path = destination.with_name(destination.name + ".verified.json")
    current = remote_metadata(url, timeout)

    if destination.exists():
        expected = current["length"]
        if expected is None or destination.stat().st_size == expected:
            verified = None
            if verified_path.exists():
                verified = json.loads(verified_path.read_text(encoding="utf-8"))
            if not verified or verified.get("size") != destination.stat().st_size:
                print(f"Verifying gzip CRC: {destination.name}")
                validate_gzip(destination)
                verified_path.write_text(
                    json.dumps(
                        {"size": destination.stat().st_size, **current},
                        indent=2,
                        sort_keys=True,
                    ) + "\n",
                    encoding="utf-8",
                )
            print(f"Already downloaded: {destination}")
            return
        raise RuntimeError(
            f"Existing completed file has the wrong size: {destination}. "
            "Move it aside before retrying."
        )

    existing = partial.stat().st_size if partial.exists() else 0
    if existing and metadata_path.exists():
        saved = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not same_remote_version(saved, current):
            raise RuntimeError(
                f"Remote dump changed while {partial} was incomplete. "
                "Move the partial file aside and start this dump again."
            )
    metadata_path.write_text(
        json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    headers = {"User-Agent": "BookProphet-catalog-import/1.0"}
    if existing:
        headers["Range"] = f"bytes={existing}-"
        validator = current.get("etag") or current.get("last_modified")
        if validator:
            headers["If-Range"] = validator
    request = urllib.request.Request(url, headers=headers)

    started = time.monotonic()
    last_report = started
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = getattr(response, "status", response.getcode())
        if existing and status != 206:
            print("Server did not honor Range; restarting this download")
            existing = 0
        mode = "ab" if existing else "wb"
        downloaded = existing
        with partial.open(mode) as target:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                target.write(chunk)
                downloaded += len(chunk)
                now = time.monotonic()
                if now - last_report >= 10:
                    total = current["length"]
                    if total:
                        percent = downloaded * 100 / total
                        print(
                            f"  {destination.name}: {gibibytes(downloaded):.2f}/"
                            f"{gibibytes(total):.2f} GiB ({percent:.1f}%)",
                            flush=True,
                        )
                    else:
                        print(
                            f"  {destination.name}: {gibibytes(downloaded):.2f} GiB",
                            flush=True,
                        )
                    last_report = now

    expected = current["length"]
    if expected is not None and partial.stat().st_size != expected:
        raise RuntimeError(
            f"Incomplete download for {destination.name}: got "
            f"{partial.stat().st_size} bytes, expected {expected}"
        )
    print(f"Verifying gzip CRC: {destination.name}")
    validate_gzip(partial)
    partial.replace(destination)
    metadata_path.unlink(missing_ok=True)
    verified_path.write_text(
        json.dumps(
            {"size": destination.stat().st_size, **current},
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    elapsed = max(time.monotonic() - started, 0.001)
    print(
        f"Downloaded {destination.name}: {gibibytes(destination.stat().st_size):.2f} "
        f"GiB in {elapsed / 60:.1f} minutes"
    )


def download_with_retries(url: str, destination: Path, timeout: int, retries: int):
    for attempt in range(1, retries + 1):
        try:
            download_once(url, destination, timeout)
            return
        except (OSError, RuntimeError, urllib.error.URLError) as error:
            if attempt == retries:
                raise
            delay = min(300, 5 * (2 ** (attempt - 1)))
            print(
                f"Download attempt {attempt}/{retries} failed for "
                f"{destination.name}: {error}. Retrying in {delay}s.",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--minimum-free-gb", type=float, default=250.0)
    parser.add_argument("--download-retries", type=int, default=8)
    parser.add_argument("--network-timeout", type=int, default=120)
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--similar-authors-limit", type=int, default=20)
    parser.add_argument("--minimum-shared-tags", type=int, default=2)
    args = parser.parse_args()
    if args.minimum_free_gb < 0 or args.download_retries < 1:
        parser.error("disk minimum must be nonnegative and retries must be positive")

    workspace = args.workspace.resolve()
    require_free_space(workspace, args.minimum_free_gb)
    downloads = workspace / "downloads"
    dump_paths = {}
    for name, url, filename in DUMPS:
        destination = downloads / filename
        print(f"\n=== Downloading {name} ===")
        download_with_retries(
            url, destination, args.network_timeout, args.download_retries
        )
        dump_paths[name] = destination

    if args.download_only:
        print(f"\nAll dumps are available in {downloads}")
        return

    pipeline = Path(__file__).with_name("run_catalog_pipeline.py")
    command = [
        sys.executable, str(pipeline),
        "--authors", str(dump_paths["authors"]),
        "--works", str(dump_paths["works"]),
        "--editions", str(dump_paths["editions"]),
        "--output-dir", str(workspace / "build"),
        "--similar-authors-limit", str(args.similar_authors_limit),
        "--minimum-shared-tags", str(args.minimum_shared_tags),
    ]
    print("\n=== Building canonical catalog ===")
    subprocess.run(command, check=True)
    print(f"\nFinal canonical CSVs: {workspace / 'build' / 'canonical'}")


if __name__ == "__main__":
    main()
