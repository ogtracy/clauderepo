from __future__ import annotations

from .config import Config
from .models import normalize_author_profile
from .prh_client import PrhClient, PrhError
from .storage import append_failure, append_jsonl, iter_jsonl, load_values


def _tombstone(author_id: int, error: PrhError) -> dict:
    return {
        "prh_author_id": author_id,
        "available": False,
        "status_code": error.status_code,
        "error": str(error),
    }


def run(config: Config | None = None) -> None:
    config = config or Config.from_env()
    config.ensure_directories()
    client = PrhClient(config)

    authors_path = config.normalized_dir / "authors.jsonl"
    profiles_path = config.normalized_dir / "author_profiles.jsonl"
    works_path = config.normalized_dir / "author_works.jsonl"
    failures = config.failures_dir / "author_profiles.jsonl"

    profile_done = load_values(profiles_path, "prh_author_id")
    works_done = load_values(works_path, "prh_author_id")

    for index, author in enumerate(iter_jsonl(authors_path), start=1):
        author_id = author.get("prh_author_id")
        if author_id is None:
            continue

        if author_id not in profile_done:
            try:
                payload = client.get(f"/authors/{author_id}/views/author-display")
                append_jsonl(config.raw_dir / "author_display.jsonl", {"prh_author_id": author_id, "response": payload})
                append_jsonl(profiles_path, normalize_author_profile(author_id, payload))
            except PrhError as exc:
                append_failure(failures, stage="author-display", item=author_id, error=exc)
                if exc.status_code in (400, 404):
                    append_jsonl(profiles_path, _tombstone(author_id, exc))
            profile_done.add(author_id)

        if author_id not in works_done:
            try:
                work_ids = []
                record_count = None
                for start, payload, items in client.paginate(
                    f"/authors/{author_id}/works",
                    collection_name="works",
                    rows=config.rows_per_page,
                    suppress_links=True,
                ):
                    append_jsonl(config.raw_dir / "author_works.jsonl", {
                        "prh_author_id": author_id,
                        "start": start,
                        "response": payload,
                    })
                    if record_count is None:
                        record_count = payload.get("recordCount")
                    for item in items:
                        work_id = item.get("workId") if isinstance(item, dict) else None
                        if work_id is not None:
                            work_ids.append(work_id)

                append_jsonl(works_path, {
                    "prh_author_id": author_id,
                    "available": True,
                    "work_ids": list(dict.fromkeys(work_ids)),
                    "record_count": record_count,
                })
            except PrhError as exc:
                append_failure(failures, stage="author-works", item=author_id, error=exc)
                if exc.status_code in (400, 404):
                    append_jsonl(works_path, _tombstone(author_id, exc) | {"work_ids": []})
            works_done.add(author_id)

        if index % 100 == 0:
            print(f"processed authors={index} profiles={len(profile_done)} work-lists={len(works_done)}")

    print(f"Author profiles complete: profiles={len(profile_done)} work-lists={len(works_done)}")


if __name__ == "__main__":
    run()
