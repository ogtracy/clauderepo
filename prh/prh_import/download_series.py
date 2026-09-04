from __future__ import annotations

from .config import Config
from .models import normalize_series, normalize_series_works
from .prh_client import PrhClient, PrhError
from .storage import (
    append_failure,
    append_jsonl,
    iter_jsonl,
    load_composite_values,
    load_values,
)


def discover_series_codes(config: Config) -> list[str]:
    values: set[str] = set()

    for record in iter_jsonl(config.normalized_dir / "series_hints.jsonl"):
        code = record.get("prh_series_code")
        if code:
            values.add(str(code))

    for profile in iter_jsonl(config.normalized_dir / "author_profiles.jsonl"):
        for series in profile.get("series_hints") or []:
            if not isinstance(series, dict):
                continue
            code = series.get("code") or series.get("seriesCode")
            if code:
                values.add(str(code))

    return sorted(values)


def run(config: Config | None = None) -> None:
    config = config or Config.from_env()
    config.ensure_directories()
    client = PrhClient(config)

    codes = discover_series_codes(config)
    series_path = config.normalized_dir / "series.jsonl"
    work_series_path = config.normalized_dir / "work_series.jsonl"
    failures = config.failures_dir / "series.jsonl"

    done = load_values(series_path, "prh_series_code")
    relation_done = load_composite_values(work_series_path, ("prh_work_id", "prh_series_code"))

    print(f"Series discovered={len(codes)}; already complete={len(done)}")

    for index, code in enumerate(codes, start=1):
        if code in done:
            continue
        try:
            series_payload = client.get(f"/series/{code}", suppress_links=True)
            append_jsonl(config.raw_dir / "series.jsonl", {"prh_series_code": code, "response": series_payload})

            all_relations = []
            for start, page, items in client.paginate(
                f"/series/{code}/works",
                collection_name="works",
                rows=config.rows_per_page,
                suppress_links=True,
            ):
                append_jsonl(config.raw_dir / "series_works.jsonl", {
                    "prh_series_code": code,
                    "start": start,
                    "response": page,
                })
                all_relations.extend(normalize_series_works(code, page))

            for relation in all_relations:
                key = (relation.get("prh_work_id"), relation.get("prh_series_code"))
                if None in key or key in relation_done:
                    continue
                append_jsonl(work_series_path, relation)
                relation_done.add(key)

            append_jsonl(series_path, normalize_series(code, series_payload))
            done.add(code)

        except PrhError as exc:
            append_failure(failures, stage="series", item=code, error=exc)
            if exc.status_code in (400, 404):
                append_jsonl(series_path, {
                    "prh_series_code": code,
                    "available": False,
                    "status_code": exc.status_code,
                    "error": str(exc),
                })
                done.add(code)

        if index % 50 == 0:
            print(f"series index={index}/{len(codes)} completed={len(done)}")

    print(f"Series complete: {len(done)}")


if __name__ == "__main__":
    run()
