from __future__ import annotations

import copy
import re
import time
from dataclasses import dataclass
from typing import Any, Iterator

import requests

from .config import Config


API_ROOT = "https://api.penguinrandomhouse.com/resources/v2/title"


@dataclass
class PrhError(RuntimeError):
    message: str
    status_code: int | None = None
    path: str | None = None
    response_text: str | None = None

    def __str__(self) -> str:
        bits = [self.message]
        if self.status_code is not None:
            bits.append(f"status={self.status_code}")
        if self.path:
            bits.append(f"path={self.path}")
        return " | ".join(bits)


class PrhClient:
    def __init__(self, config: Config, *, timeout_seconds: int | None = None):
        self.config = config
        self.timeout_seconds = timeout_seconds or config.timeout_seconds
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Quillent-PRH-Importer/1.0"})

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{API_ROOT}/domains/{self.config.domain}{path}"

    def _redact_string(self, value: str) -> str:
        if self.config.api_key:
            value = value.replace(self.config.api_key, "[REDACTED]")
        return re.sub(
            r"api_key=[^&\s\"']+",
            "api_key=[REDACTED]",
            value,
            flags=re.IGNORECASE,
        )

    def redact(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self._redact_string(obj)
        if isinstance(obj, list):
            return [self.redact(item) for item in obj]
        if isinstance(obj, dict):
            return {key: self.redact(value) for key, value in obj.items()}
        return obj

    def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        return_empty_lists: bool = True,
        suppress_links: bool = False,
    ) -> dict[str, Any]:
        query: dict[str, Any] = {
            "api_key": self.config.api_key,
        }
        if return_empty_lists:
            query["returnEmptyLists"] = "true"
        if suppress_links:
            query["suppressLinks"] = "true"
        if params:
            query.update(params)

        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                response = self.session.get(
                    self._url(path),
                    params=query,
                    timeout=self.timeout_seconds,
                )

                if response.status_code == 429 or 500 <= response.status_code < 600:
                    if attempt == self.config.max_retries:
                        raise PrhError(
                            "PRH request failed after retries",
                            status_code=response.status_code,
                            path=path,
                            response_text=self._redact_string(response.text[:2000]),
                        )
                    wait = min(60, 2 ** attempt)
                    print(f"  retry {attempt}/{self.config.max_retries}: {response.status_code}; sleeping {wait}s")
                    time.sleep(wait)
                    continue

                if not response.ok:
                    raise PrhError(
                        "PRH request returned an error",
                        status_code=response.status_code,
                        path=path,
                        response_text=self._redact_string(response.text[:2000]),
                    )

                try:
                    payload = response.json()
                except ValueError as exc:
                    raise PrhError(
                        "PRH returned non-JSON content",
                        status_code=response.status_code,
                        path=path,
                        response_text=self._redact_string(response.text[:2000]),
                    ) from exc

                if payload.get("status") not in (None, "ok"):
                    raise PrhError(
                        f"PRH payload status was {payload.get('status')!r}",
                        status_code=response.status_code,
                        path=path,
                        response_text=self._redact_string(str(payload.get("error"))),
                    )

                time.sleep(self.config.request_delay_seconds)
                return self.redact(copy.deepcopy(payload))

            except PrhError:
                raise
            except requests.RequestException as exc:
                last_error = exc
                if attempt == self.config.max_retries:
                    break
                wait = min(60, 2 ** attempt)
                print(f"  network retry {attempt}/{self.config.max_retries}; sleeping {wait}s")
                time.sleep(wait)

        raise PrhError(
            f"Network request failed after retries: {last_error}",
            path=path,
        )

    def paginate(
        self,
        path: str,
        *,
        collection_name: str,
        params: dict[str, Any] | None = None,
        rows: int | None = None,
        suppress_links: bool = True,
    ) -> Iterator[tuple[int, dict[str, Any], list[Any]]]:
        start = 0
        page_size = rows or self.config.rows_per_page

        while True:
            query = dict(params or {})
            query.update({"start": start, "rows": page_size})
            payload = self.get(
                path,
                params=query,
                suppress_links=suppress_links,
            )
            data = payload.get("data")
            if isinstance(data, dict):
                items = data.get(collection_name) or []
            elif isinstance(data, list):
                items = data
            else:
                items = []

            if not isinstance(items, list):
                items = []

            yield start, payload, items

            count = len(items)
            if count == 0:
                break

            start += count
            record_count = payload.get("recordCount")
            if isinstance(record_count, int) and start >= record_count:
                break
            if count < page_size:
                break
