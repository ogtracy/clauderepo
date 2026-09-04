from __future__ import annotations

from .config import Config
from .models import (
    extract_series_hints,
    iter_product_editions,
    normalize_edition,
    normalize_edition_contributors,
    normalize_work,
    normalize_work_contributors,
)
from .prh_client import PrhClient, PrhError
from .storage import (
    append_failure,
    append_jsonl,
    iter_jsonl,
    load_composite_values,
    load_values,
)


def discover_work_ids(path) -> list[int]:
    values: set[int] = set()
    for record in iter_jsonl(path):
        for value in record.get("work_ids") or []:
            try:
                values.add(int(value))
            except (TypeError, ValueError):
                continue
    return sorted(values)


def run(config: Config | None = None) -> None:
    config = config or Config.from_env()
    config.ensure_directories()
    client = PrhClient(config)

    work_ids = discover_work_ids(config.normalized_dir / "author_works.jsonl")
    works_path = config.normalized_dir / "works.jsonl"
    editions_path = config.normalized_dir / "editions.jsonl"
    contributors_path = config.normalized_dir / "edition_contributors.jsonl"
    work_contributors_path = config.normalized_dir / "work_contributors.jsonl"
    series_hints_path = config.normalized_dir / "series_hints.jsonl"
    failures = config.failures_dir / "works.jsonl"

    work_done = load_values(works_path, "prh_work_id")
    edition_done = load_values(editions_path, "isbn")
    contributor_done = {
        (record.get("isbn"), record.get("prh_author_id"), record.get("role_code") or "")
        for record in iter_jsonl(contributors_path)
        if record.get("isbn") is not None and record.get("prh_author_id") is not None
    }
    work_contributor_done = {
        (record.get("prh_work_id"), record.get("prh_author_id"), record.get("role_code") or "")
        for record in iter_jsonl(work_contributors_path)
        if record.get("prh_work_id") is not None and record.get("prh_author_id") is not None
    }
    series_hint_done = load_composite_values(
        series_hints_path,
        ("prh_work_id", "prh_series_code"),
    )

    print(f"Unique works discovered={len(work_ids)}; already complete={len(work_done)}")

    for index, work_id in enumerate(work_ids, start=1):
        if work_id in work_done:
            continue

        try:
            basic = client.get(f"/works/{work_id}", suppress_links=True)
            product = client.get(f"/works/{work_id}/views/product-display")
            append_jsonl(config.raw_dir / "works_basic.jsonl", {"prh_work_id": work_id, "response": basic})
            append_jsonl(config.raw_dir / "works_product_display.jsonl", {"prh_work_id": work_id, "response": product})

            for format_family, edition in iter_product_editions(product):
                normalized = normalize_edition(work_id, format_family, edition)
                isbn = normalized.get("isbn")
                if isbn and isbn not in edition_done:
                    append_jsonl(editions_path, normalized)
                    edition_done.add(isbn)

                for relation in normalize_edition_contributors(work_id, edition):
                    if relation.get("isbn") is None or relation.get("prh_author_id") is None:
                        continue
                    key = (relation.get("isbn"), relation.get("prh_author_id"), relation.get("role_code") or "")
                    if key in contributor_done:
                        continue
                    append_jsonl(contributors_path, relation)
                    contributor_done.add(key)

            for relation in normalize_work_contributors(work_id, product):
                if relation.get("prh_work_id") is None or relation.get("prh_author_id") is None:
                    continue
                key = (relation.get("prh_work_id"), relation.get("prh_author_id"), relation.get("role_code") or "")
                if key in work_contributor_done:
                    continue
                append_jsonl(work_contributors_path, relation)
                work_contributor_done.add(key)

            for hint in extract_series_hints(work_id, product):
                key = (hint.get("prh_work_id"), hint.get("prh_series_code"))
                if None in key or key in series_hint_done:
                    continue
                append_jsonl(series_hints_path, hint)
                series_hint_done.add(key)

            append_jsonl(works_path, normalize_work(work_id, basic, product))
            work_done.add(work_id)

        except PrhError as exc:
            append_failure(failures, stage="work", item=work_id, error=exc)
            if exc.status_code in (400, 404):
                append_jsonl(works_path, {
                    "prh_work_id": work_id,
                    "available": False,
                    "status_code": exc.status_code,
                    "error": str(exc),
                })
                work_done.add(work_id)

        if index % 100 == 0:
            print(f"work index={index}/{len(work_ids)} completed={len(work_done)} editions={len(edition_done)}")

    print(f"Works complete: {len(work_done)}; editions={len(edition_done)}")


if __name__ == "__main__":
    run()
