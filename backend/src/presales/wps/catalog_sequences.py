import re
from collections import defaultdict

MAX_SEQUENCE_ROW_GAP = 10


def model_family(model):
    parts = [part for part in re.split(r"[-_/]+", model.upper()) if part]
    return "-".join(parts[:2]) if len(parts) >= 3 else ""


def build_catalog_transitions(variants, catalog_scope=None):
    source_rows = defaultdict(list)
    for variant in variants:
        for source in variant.get("source_details", []):
            if catalog_scope and not _scope_matches(source, catalog_scope):
                continue
            for sequence_key in _variant_sequence_keys(variant):
                key = (source.get("import_id"), source.get("sheet"), sequence_key)
                source_rows[key].append((int(source.get("row") or 0), variant))
    transitions = defaultdict(list)
    for (_, sheet, _), rows in source_rows.items():
        ordered = _unique_source_rows(rows)
        _add_pairs(transitions, ordered, sheet)
        _add_triples(transitions, ordered, sheet)
    return dict(transitions)


def _scope_matches(source, scope):
    return source.get("import_id") == scope.get("import_id") and source.get("sheet") == scope.get(
        "sheet"
    )


def _add_pairs(transitions, ordered, sheet):
    for (previous_row, previous), (following_row, following) in zip(
        ordered, ordered[1:], strict=False
    ):
        if following_row - previous_row > MAX_SEQUENCE_ROW_GAP:
            continue
        if _variant_model(previous) == _variant_model(following):
            continue
        _add_sheet(transitions, (_variant_model(previous), _variant_model(following)), sheet)


def _add_triples(transitions, ordered, sheet):
    for first, second, third in zip(ordered, ordered[1:], ordered[2:], strict=False):
        if not _contiguous_source_triple(first, second, third):
            continue
        key = tuple(_variant_model(item[1]) for item in [first, second, third])
        _add_sheet(transitions, key, sheet)


def _add_sheet(transitions, key, sheet):
    if sheet and sheet not in transitions[key]:
        transitions[key].append(sheet)


def _unique_source_rows(rows):
    result, seen = [], set()
    for row, variant in sorted(rows, key=lambda item: (item[0], item[1]["id"])):
        identity = (row, variant["id"])
        if identity in seen:
            continue
        seen.add(identity)
        result.append((row, variant))
    return result


def _contiguous_source_triple(first, second, third):
    rows = [first[0], second[0], third[0]]
    models = [_variant_model(item[1]) for item in [first, second, third]]
    return (
        rows[1] - rows[0] <= MAX_SEQUENCE_ROW_GAP
        and rows[2] - rows[1] <= MAX_SEQUENCE_ROW_GAP
        and models[0] != models[1]
        and models[1] != models[2]
    )


def _variant_sequence_keys(variant):
    keys = {f"series:{value.casefold().strip()}" for value in variant.get("series", []) if value}
    family = model_family(_variant_model(variant))
    if family:
        keys.add(f"family:{family.casefold()}")
    return keys


def _variant_model(variant):
    return variant["product"].get("model", "").casefold().strip()
