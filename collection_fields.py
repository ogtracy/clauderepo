"""Helpers for lossless collection-valued CSV fields.

Open Library stores many properties as arrays.  The parsing stage serializes
those arrays as JSON inside a CSV cell so punctuation in a value is never
mistaken for a relationship delimiter.
"""

import json
from typing import Any, List


def parse_json_list(value: str) -> List[Any]:
    """Return a JSON-array CSV field as a list, rejecting legacy packed text."""
    if value is None or not value.strip():
        return []
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("collection field must contain a JSON array")
    return parsed


def string_values(value: str) -> List[str]:
    """Return non-empty strings from a JSON-array CSV field."""
    return [item for item in parse_json_list(value) if isinstance(item, str) and item]
