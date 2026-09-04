from __future__ import annotations

from datetime import date
from typing import Any, Iterable


def data_list(payload: dict[str, Any] | None, name: str) -> list[dict[str, Any]]:
    if not payload:
        return []
    data = payload.get("data")
    if isinstance(data, dict):
        value = data.get(name)
    elif isinstance(data, list):
        value = data
    else:
        value = []
    return [item for item in (value or []) if isinstance(item, dict)]


def first_item(payload: dict[str, Any] | None, name: str) -> dict[str, Any]:
    items = data_list(payload, name)
    return items[0] if items else {}


def normalize_author(item: dict[str, Any]) -> dict[str, Any]:
    company = item.get("company") or {}
    return {
        "prh_author_id": item.get("authorId"),
        "display": item.get("display"),
        "first": item.get("first"),
        "last": item.get("last"),
        "company_key": company.get("key") if isinstance(company, dict) else None,
        "client_source_id": item.get("clientSourceId"),
        "prh_url": item.get("seoFriendlyUrl"),
    }


def normalize_author_profile(author_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return {
        "prh_author_id": author_id,
        "available": True,
        "display": data.get("display"),
        "biography_html": data.get("spotlight"),
        "has_author_photo": data.get("hasAuthorPhoto"),
        "photo_url": (
            f"https://images.penguinrandomhouse.com/author/{author_id}"
            if data.get("hasAuthorPhoto")
            else None
        ),
        "photo_credit": data.get("photoCredit"),
        "photo_date": data.get("photoDate"),
        "prh_url": data.get("seoFriendlyUrl"),
        "company": data.get("company"),
        "client_source_id": data.get("clientSourceId"),
        "series_hints": data.get("series") or [],
        "related_links": data.get("relatedLinks") or [],
        "reported_work_count": data.get("workCount"),
    }


def normalize_author_work_list(author_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    works = data_list(payload, "works")
    work_ids = []
    for item in works:
        work_id = item.get("workId")
        if work_id is not None:
            work_ids.append(work_id)
    return {
        "prh_author_id": author_id,
        "available": True,
        "work_ids": list(dict.fromkeys(work_ids)),
        "record_count": payload.get("recordCount"),
    }


def parse_date(value: Any) -> str | None:
    if isinstance(value, str):
        return value[:10] if len(value) >= 10 else value
    if isinstance(value, dict):
        raw = value.get("date")
        if isinstance(raw, str):
            return raw[:10]
    return None


def iter_product_editions(product_payload: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    data = product_payload.get("data") if isinstance(product_payload.get("data"), dict) else {}
    formats = data.get("formats") or {}
    if not isinstance(formats, dict):
        return
    for format_family, editions in formats.items():
        if not isinstance(editions, dict):
            continue
        for isbn_key, edition in editions.items():
            if isinstance(edition, dict):
                yield str(format_family), edition


def choose_canonical_edition(product_payload: dict[str, Any]) -> dict[str, Any] | None:
    editions = [edition for _, edition in iter_product_editions(product_payload)]
    if not editions:
        return None

    def key(edition: dict[str, Any]) -> tuple[str, int]:
        on_sale = parse_date(edition.get("onSaleDate")) or "9999-12-31"
        version = str(edition.get("version") or "")
        penalty = 1 if "tie-in" in version.lower() else 0
        return on_sale, penalty

    return min(editions, key=key)


def normalize_work(work_id: int, basic_payload: dict[str, Any], product_payload: dict[str, Any]) -> dict[str, Any]:
    basic = first_item(basic_payload, "works")
    product = product_payload.get("data") if isinstance(product_payload.get("data"), dict) else {}
    canonical = choose_canonical_edition(product_payload) or {}
    front = product.get("frontlistiestTitle") if isinstance(product.get("frontlistiestTitle"), dict) else {}

    canonical_title = canonical.get("title") or basic.get("title") or product.get("title")
    canonical_subtitle = canonical.get("subtitle")

    return {
        "prh_work_id": work_id,
        "available": True,
        "title": canonical_title,
        "subtitle": canonical_subtitle,
        "prh_display_title": basic.get("title") or product.get("title"),
        "first_onsale": basic.get("firstOnsale"),
        "current_onsale": basic.get("onsale"),
        "language": basic.get("language"),
        "prh_url": basic.get("seoFriendlyUrl") or product.get("seoFriendlyUrl"),
        "about_the_book_html": canonical.get("aboutTheBook"),
        "keynote_html": canonical.get("keynote"),
        "positioning_html": canonical.get("positioning"),
        "awards": product.get("bookAwards") or {},
        "frontlistiest_isbn": front.get("isbn") or front.get("isbnStr"),
        "isbn_counts": product.get("isbnCounts") or basic.get("isbnCounts"),
    }


def normalize_edition(work_id: int, format_family: str, edition: dict[str, Any]) -> dict[str, Any]:
    isbn = edition.get("isbn") or edition.get("isbnStr")
    isbn_str = str(isbn) if isbn is not None else None
    imprint = edition.get("imprint") or {}
    series = edition.get("series") or {}
    format_value = edition.get("format")
    if isinstance(format_value, dict):
        format_name = format_value.get("description") or format_value.get("name")
        format_code = format_value.get("code")
    else:
        format_name = format_value
        format_code = None

    return {
        "prh_work_id": work_id,
        "isbn": isbn_str,
        "isbn10": edition.get("isbn10") or edition.get("asin"),
        "title": edition.get("title"),
        "subtitle": edition.get("subtitle"),
        "author_display": edition.get("author"),
        "publication_date": parse_date(edition.get("onSaleDate")),
        "pages": edition.get("totalPages"),
        "trim_size": edition.get("trimSize"),
        "format_family": format_family,
        "format_code": format_code,
        "format_name": format_name,
        "version": edition.get("version"),
        "language": edition.get("language"),
        "imprint_code": imprint.get("code") if isinstance(imprint, dict) else None,
        "imprint_name": (imprint.get("name") or imprint.get("description")) if isinstance(imprint, dict) else None,
        "asin": edition.get("asin"),
        "cover_url": (
            f"https://images.penguinrandomhouse.com/cover/{isbn_str}"
            if isbn_str and edition.get("hasCoverImage")
            else None
        ),
        "prh_url": edition.get("seoFriendlyUrl"),
        "series_code": series.get("code") if isinstance(series, dict) else None,
        "series_name": series.get("title") if isinstance(series, dict) else None,
        "series_position": (
            series.get("seriesEditVolNo") if isinstance(series, dict) else None
        ),
        "subjects": edition.get("categories") or [],
        "custom_subject_category": edition.get("customSubjectCategory"),
        "sales_restriction": edition.get("salesRestriction"),
        "raw_flags": edition.get("flags") or [],
    }


def normalize_edition_contributors(work_id: int, edition: dict[str, Any]) -> list[dict[str, Any]]:
    isbn = edition.get("isbn") or edition.get("isbnStr")
    if isbn is None:
        return []
    contributors = edition.get("contributors") or {}
    if isinstance(contributors, list):
        values = contributors
    elif isinstance(contributors, dict):
        values = list(contributors.values())
    else:
        values = []

    output: list[dict[str, Any]] = []
    for ordinal, contributor in enumerate(values, start=1):
        if not isinstance(contributor, dict):
            continue
        output.append({
            "prh_work_id": work_id,
            "isbn": str(isbn),
            "prh_author_id": contributor.get("id") or contributor.get("authorId"),
            "display": contributor.get("display"),
            "role_code": contributor.get("roleCode") or contributor.get("contribRoleCode"),
            "role_description": contributor.get("roleName") or contributor.get("contribRoleDesc"),
            "primary_flag": contributor.get("primaryFlag"),
            "ordinal": ordinal,
        })
    return output


def extract_series_hints(work_id: int, product_payload: dict[str, Any]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, Any]] = set()
    output: list[dict[str, Any]] = []
    for _, edition in iter_product_editions(product_payload):
        series = edition.get("series") or {}
        if not isinstance(series, dict):
            continue
        code = series.get("code")
        if not code:
            continue
        position = series.get("seriesEditVolNo")
        key = (code, position)
        if key in seen:
            continue
        seen.add(key)
        output.append({
            "prh_work_id": work_id,
            "prh_series_code": code,
            "series_name": series.get("title"),
            "position": position,
            "description_html": series.get("description"),
            "prh_url": series.get("seoFriendlyUrl"),
        })
    return output


def normalize_series(series_code: str, payload: dict[str, Any]) -> dict[str, Any]:
    series = first_item(payload, "series")
    return {
        "prh_series_code": series_code,
        "available": True,
        "name": series.get("seriesName"),
        "description_html": series.get("description"),
        "series_count": series.get("seriesCount"),
        "series_date": series.get("seriesDate"),
        "is_numbered": series.get("isNumbered"),
        "is_kids": series.get("isKids"),
        "prh_url": series.get("seoFriendlyUrl"),
    }


def normalize_series_works(series_code: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    output = []
    for work in data_list(payload, "works"):
        work_id = work.get("workId")
        if work_id is None:
            continue
        output.append({
            "prh_series_code": series_code,
            "prh_work_id": work_id,
            "position": work.get("seriesNumber"),
            "title": work.get("title"),
            "first_onsale": work.get("firstOnsale"),
        })
    return output


def normalize_keywords(work_id: int, isbn: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    raw_values = data.get("keywords") or []
    candidates: list[str] = []
    for value in raw_values:
        if not isinstance(value, str):
            continue
        for token in value.split(";"):
            token = token.strip()
            if token and token not in candidates:
                candidates.append(token)
    return {
        "prh_work_id": work_id,
        "isbn": isbn,
        "available": True,
        "raw_keywords": raw_values,
        "candidates": candidates,
    }


def normalize_work_contributors(work_id: int, product_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Aggregate contributor/role observations across all editions in a Work."""
    aggregated: dict[tuple[Any, Any], dict[str, Any]] = {}

    for _, edition in iter_product_editions(product_payload):
        isbn = edition.get("isbn") or edition.get("isbnStr")
        for relation in normalize_edition_contributors(work_id, edition):
            author_id = relation.get("prh_author_id")
            role_code = relation.get("role_code")
            if author_id is None:
                continue
            key = (author_id, role_code or "")
            current = aggregated.get(key)
            if current is None:
                current = {
                    "prh_work_id": work_id,
                    "prh_author_id": author_id,
                    "display": relation.get("display"),
                    "role_code": role_code,
                    "role_description": relation.get("role_description"),
                    "primary_flag": relation.get("primary_flag"),
                    "observed_isbns": [],
                }
                aggregated[key] = current
            elif relation.get("primary_flag") is True:
                current["primary_flag"] = True

            if isbn is not None:
                isbn_str = str(isbn)
                if isbn_str not in current["observed_isbns"]:
                    current["observed_isbns"].append(isbn_str)

    return list(aggregated.values())
