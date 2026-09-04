from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .config import Config
from .storage import iter_jsonl


DDL = """
CREATE SCHEMA IF NOT EXISTS prh_stage;

CREATE TABLE IF NOT EXISTS prh_stage.authors (
    prh_author_id bigint PRIMARY KEY,
    payload jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS prh_stage.author_profiles (
    prh_author_id bigint PRIMARY KEY,
    payload jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS prh_stage.author_works (
    prh_author_id bigint PRIMARY KEY,
    payload jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS prh_stage.works (
    prh_work_id bigint PRIMARY KEY,
    payload jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS prh_stage.editions (
    isbn text PRIMARY KEY,
    prh_work_id bigint,
    payload jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS prh_stage.edition_contributors (
    isbn text NOT NULL,
    prh_author_id bigint NOT NULL,
    role_code text NOT NULL DEFAULT '',
    payload jsonb NOT NULL,
    PRIMARY KEY (isbn, prh_author_id, role_code)
);
CREATE TABLE IF NOT EXISTS prh_stage.work_contributors (
    prh_work_id bigint NOT NULL,
    prh_author_id bigint NOT NULL,
    role_code text NOT NULL DEFAULT '',
    payload jsonb NOT NULL,
    PRIMARY KEY (prh_work_id, prh_author_id, role_code)
);
CREATE TABLE IF NOT EXISTS prh_stage.series (
    prh_series_code text PRIMARY KEY,
    payload jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS prh_stage.work_series (
    prh_work_id bigint NOT NULL,
    prh_series_code text NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (prh_work_id, prh_series_code)
);
CREATE TABLE IF NOT EXISTS prh_stage.keywords (
    prh_work_id bigint PRIMARY KEY,
    isbn text,
    payload jsonb NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prh_stage_editions_work
    ON prh_stage.editions(prh_work_id);
CREATE INDEX IF NOT EXISTS idx_prh_stage_edition_contributors_author
    ON prh_stage.edition_contributors(prh_author_id);
CREATE INDEX IF NOT EXISTS idx_prh_stage_work_contributors_author
    ON prh_stage.work_contributors(prh_author_id);
CREATE INDEX IF NOT EXISTS idx_prh_stage_work_series_series
    ON prh_stage.work_series(prh_series_code);
"""


def chunks(iterable: Iterable[dict[str, Any]], size: int = 1000):
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def run(config: Config | None = None) -> None:
    config = config or Config.from_env(require_api_key=False)
    config.ensure_directories()
    if not config.database_url:
        raise RuntimeError("DATABASE_URL environment variable is not set")

    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError as exc:
        raise RuntimeError("Install PostgreSQL support with: pip install 'psycopg[binary]'") from exc

    specs = [
        ("authors.jsonl", "prh_stage.authors", ("prh_author_id",), ("prh_author_id",)),
        ("author_profiles.jsonl", "prh_stage.author_profiles", ("prh_author_id",), ("prh_author_id",)),
        ("author_works.jsonl", "prh_stage.author_works", ("prh_author_id",), ("prh_author_id",)),
        ("works.jsonl", "prh_stage.works", ("prh_work_id",), ("prh_work_id",)),
        ("editions.jsonl", "prh_stage.editions", ("isbn", "prh_work_id"), ("isbn",)),
        ("edition_contributors.jsonl", "prh_stage.edition_contributors", ("isbn", "prh_author_id", "role_code"), ("isbn", "prh_author_id", "role_code")),
        ("work_contributors.jsonl", "prh_stage.work_contributors", ("prh_work_id", "prh_author_id", "role_code"), ("prh_work_id", "prh_author_id", "role_code")),
        ("series.jsonl", "prh_stage.series", ("prh_series_code",), ("prh_series_code",)),
        ("work_series.jsonl", "prh_stage.work_series", ("prh_work_id", "prh_series_code"), ("prh_work_id", "prh_series_code")),
        ("keywords.jsonl", "prh_stage.keywords", ("prh_work_id", "isbn"), ("prh_work_id",)),
    ]

    with psycopg.connect(config.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()

        for filename, table, columns, conflict_cols in specs:
            path = config.normalized_dir / filename
            if not path.exists():
                print(f"skip {filename}: not present")
                continue

            insert_cols = list(columns) + ["payload"]
            placeholders = ", ".join(["%s"] * len(insert_cols))
            col_sql = ", ".join(insert_cols)
            conflict_sql = ", ".join(conflict_cols)
            updates = [f"{col}=EXCLUDED.{col}" for col in columns if col not in conflict_cols]
            updates.append("payload=EXCLUDED.payload")
            sql = (
                f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders}) "
                f"ON CONFLICT ({conflict_sql}) DO UPDATE SET {', '.join(updates)}"
            )

            count = 0
            for batch in chunks(iter_jsonl(path)):
                rows = []
                for record in batch:
                    values = []
                    for col in columns:
                        value = record.get(col)
                        if col == "role_code" and value is None:
                            value = ""
                        values.append(value)
                    values.append(Jsonb(record))
                    rows.append(tuple(values))
                with conn.cursor() as cur:
                    cur.executemany(sql, rows)
                conn.commit()
                count += len(rows)
            print(f"staged {count} rows from {filename}")

    print("PostgreSQL staging import complete. Production-table mapping remains a separate step.")


if __name__ == "__main__":
    run()
