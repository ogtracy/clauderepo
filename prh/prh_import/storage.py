from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Iterator


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid JSONL in {path} at line {line_number}: {exc}") from exc
            if isinstance(value, dict):
                yield value


def load_values(path: Path, key: str) -> set[Any]:
    values: set[Any] = set()
    for record in iter_jsonl(path):
        value = record.get(key)
        if value is not None:
            values.add(value)
    return values


def load_composite_values(path: Path, keys: Iterable[str]) -> set[tuple[Any, ...]]:
    keys = tuple(keys)
    values: set[tuple[Any, ...]] = set()
    for record in iter_jsonl(path):
        composite = tuple(record.get(key) for key in keys)
        if all(value is not None for value in composite):
            values.add(composite)
    return values


def read_state(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return dict(default or {})
    with path.open("r", encoding="utf-8") as fh:
        value = json.load(fh)
    return value if isinstance(value, dict) else dict(default or {})


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    temp.replace(path)


def append_failure(path: Path, *, stage: str, item: Any, error: Exception) -> None:
    record = {
        "stage": stage,
        "item": item,
        "error_type": type(error).__name__,
        "error": str(error),
    }
    status_code = getattr(error, "status_code", None)
    if status_code is not None:
        record["status_code"] = status_code
    response_text = getattr(error, "response_text", None)
    if response_text:
        record["response_text"] = response_text
    append_jsonl(path, record)
