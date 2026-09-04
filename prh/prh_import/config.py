from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    api_key: str
    domain: str
    data_dir: Path
    rows_per_page: int
    request_delay_seconds: float
    timeout_seconds: int
    keyword_timeout_seconds: int
    max_retries: int
    database_url: str | None

    @classmethod
    def from_env(cls, *, require_api_key: bool = True) -> "Config":
        api_key = os.environ.get("PRH_API_KEY", "")
        if require_api_key and not api_key:
            raise RuntimeError("PRH_API_KEY environment variable is not set")

        return cls(
            api_key=api_key,
            domain=os.environ.get("PRH_DOMAIN", "PRH.US"),
            data_dir=Path(os.environ.get("PRH_DATA_DIR", "prh_data")),
            rows_per_page=int(os.environ.get("PRH_ROWS_PER_PAGE", "1000")),
            request_delay_seconds=float(os.environ.get("PRH_REQUEST_DELAY", "0.25")),
            timeout_seconds=int(os.environ.get("PRH_TIMEOUT", "60")),
            keyword_timeout_seconds=int(os.environ.get("PRH_KEYWORD_TIMEOUT", "180")),
            max_retries=int(os.environ.get("PRH_MAX_RETRIES", "5")),
            database_url=os.environ.get("DATABASE_URL"),
        )

    @property
    def normalized_dir(self) -> Path:
        return self.data_dir / "normalized"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def state_dir(self) -> Path:
        return self.data_dir / "state"

    @property
    def failures_dir(self) -> Path:
        return self.data_dir / "failures"

    def ensure_directories(self) -> None:
        for path in (
            self.data_dir,
            self.normalized_dir,
            self.raw_dir,
            self.state_dir,
            self.failures_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
