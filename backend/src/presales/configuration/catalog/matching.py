"""Candidate matching for unresolved catalog sources."""

import json

from presales.storage import ProductRecord

MATCH_FIELDS = (
    "model",
    "name",
    "brand",
    "category",
    "specification",
    "short_specification",
    "tender_specification",
    "note",
    "unit",
    "prices",
    "hidden",
)
SOURCE_VARIANCE_FIELDS = {"note", "prices", "hidden"}
MATCH_RANK = {"exact": 0, "source_variance": 1, "conflict": 2}


def match_suggestions(
    source: dict, variants: list[dict], records: dict[str, ProductRecord]
) -> list[dict]:
    candidates = [
        variant
        for variant in variants
        if variant["status"] == "confirmed"
        and variant["product"]["model"] == source["model"]
        and any(source_id in records for source_id in variant["source_ids"])
    ]
    suggestions = [candidate_match(source, variant, records) for variant in candidates]
    return sorted(
        suggestions,
        key=lambda item: (
            MATCH_RANK[item["match_type"]],
            len(item["differences"]),
            item["variant_name"],
        ),
    )


def candidate_match(source: dict, variant: dict, records: dict[str, ProductRecord]) -> dict:
    candidate_sources = [
        records[source_id] for source_id in variant["source_ids"] if source_id in records
    ]
    comparisons = [
        (difference_fields(source, record_view(record)), record) for record in candidate_sources
    ]
    differences, best_source = min(
        comparisons,
        key=lambda item: (match_rank(item[0]), len(item[0]), item[1].sheet),
    )
    return {
        "variant_id": variant["id"],
        "variant_name": variant["name"],
        "product_model": variant["product"]["model"],
        "product_name": variant["product"]["name"],
        "match_type": match_type(differences),
        "differences": list(differences),
        "best_source": source_reference(best_source),
        "source_refs": [source_reference(record) for record in candidate_sources],
    }


def difference_fields(left: dict, right: dict) -> tuple[str, ...]:
    return tuple(
        field
        for field in MATCH_FIELDS
        if canonical(field_value(left, field)) != canonical(field_value(right, field))
    )


def record_view(record: ProductRecord) -> dict:
    return {"model": record.model, "name": record.name, **record.payload}


def field_value(source: dict, field: str):
    if field == "prices":
        return source.get(field, {})
    if field == "hidden":
        return source.get(field, False)
    return source.get(field, "")


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def match_type(differences: tuple[str, ...]) -> str:
    if not differences:
        return "exact"
    if set(differences) <= SOURCE_VARIANCE_FIELDS:
        return "source_variance"
    return "conflict"


def match_rank(differences: tuple[str, ...]) -> int:
    return MATCH_RANK[match_type(differences)]


def source_reference(record: ProductRecord) -> dict:
    return {
        "id": record.id,
        "sheet": record.sheet,
        "row": int(record.payload["row"]),
    }
