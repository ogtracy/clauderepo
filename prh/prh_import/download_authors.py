from __future__ import annotations

from .config import Config
from .models import normalize_author
from .prh_client import PrhClient
from .storage import append_jsonl, load_values, read_state, write_state


def run(config: Config | None = None) -> None:
    config = config or Config.from_env()
    config.ensure_directories()
    client = PrhClient(config)

    out = config.normalized_dir / "authors.jsonl"
    raw = config.raw_dir / "author_pages.jsonl"
    state_path = config.state_dir / "download_authors.json"
    existing_ids = load_values(out, "prh_author_id")
    state = read_state(state_path, {"next_start": 0})
    start = int(state.get("next_start", 0))

    print(f"Starting authors at offset {start}; already stored={len(existing_ids)}")

    while True:
        payload = client.get(
            "/authors",
            params={"start": start, "rows": config.rows_per_page},
            suppress_links=True,
        )
        append_jsonl(raw, {"start": start, "response": payload})

        data = payload.get("data")
        authors = data.get("authors", []) if isinstance(data, dict) else []
        authors = authors if isinstance(authors, list) else []
        if not authors:
            break

        added = 0
        for item in authors:
            if not isinstance(item, dict):
                continue
            record = normalize_author(item)
            author_id = record.get("prh_author_id")
            if author_id is None or author_id in existing_ids:
                continue
            append_jsonl(out, record)
            existing_ids.add(author_id)
            added += 1

        start += len(authors)
        state = {
            "next_start": start,
            "record_count": payload.get("recordCount"),
            "stored_count": len(existing_ids),
        }
        write_state(state_path, state)
        print(f"offset={start} added={added} stored={len(existing_ids)} / {payload.get('recordCount')}")

        record_count = payload.get("recordCount")
        if isinstance(record_count, int) and start >= record_count:
            break
        if len(authors) < config.rows_per_page:
            break

    print(f"Authors complete: {len(existing_ids)} records")


if __name__ == "__main__":
    run()
