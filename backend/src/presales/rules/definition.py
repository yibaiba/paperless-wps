def source_ids(rule: dict) -> list[str]:
    if "resolved_source_ids" in rule:
        return rule["resolved_source_ids"]
    primary = rule.get("source_product_id")
    return ([primary] if primary else []) + rule.get("additional_source_ids", [])


def target_ids(rule: dict) -> list[str]:
    return [rule["target_product_id"], *rule.get("alternative_target_ids", [])]


def with_defaults(rule: dict) -> dict:
    # Existing saved revisions predate multi-source rules; keep their original semantics.
    return {
        "additional_source_ids": [],
        "alternative_target_ids": [],
        "relation": "quantity",
        "source_selector": None,
        **rule,
    }
