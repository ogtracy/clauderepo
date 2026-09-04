from __future__ import annotations

from .config import Config
from .models import normalize_keywords
from .prh_client import PrhClient, PrhError
from .storage import append_failure, append_jsonl, iter_jsonl, load_values


def run(config: Config | None = None) -> None:
    config = config or Config.from_env()
    config.ensure_directories()
    client = PrhClient(config, timeout_seconds=config.keyword_timeout_seconds)

    works_path = config.normalized_dir / "works.jsonl"
    keywords_path = config.normalized_dir / "keywords.jsonl"
    failures = config.failures_dir / "keywords.jsonl"
    done = load_values(keywords_path, "prh_work_id")

    for index, work in enumerate(iter_jsonl(works_path), start=1):
        work_id = work.get("prh_work_id")
        isbn = work.get("frontlistiest_isbn")
        if work_id is None or work_id in done:
            continue
        if not isbn:
            append_jsonl(keywords_path, {
                "prh_work_id": work_id,
                "isbn": None,
                "available": False,
                "reason": "no frontlistiest ISBN",
                "raw_keywords": [],
                "candidates": [],
            })
            done.add(work_id)
            continue

        isbn = str(isbn)
        try:
            payload = client.get(f"/titles/{isbn}/keywords", suppress_links=True)
            append_jsonl(config.raw_dir / "title_keywords.jsonl", {
                "prh_work_id": work_id,
                "isbn": isbn,
                "response": payload,
            })
            append_jsonl(keywords_path, normalize_keywords(work_id, isbn, payload))
            done.add(work_id)
        except PrhError as exc:
            append_failure(failures, stage="keywords", item={"work_id": work_id, "isbn": isbn}, error=exc)
            if exc.status_code in (400, 404):
                append_jsonl(keywords_path, {
                    "prh_work_id": work_id,
                    "isbn": isbn,
                    "available": False,
                    "status_code": exc.status_code,
                    "raw_keywords": [],
                    "candidates": [],
                })
                done.add(work_id)

        if index % 100 == 0:
            print(f"keyword work index={index} completed={len(done)}")

    print(f"Keyword enrichment complete: {len(done)} works")


if __name__ == "__main__":
    run()
