from collections import defaultdict
from decimal import Decimal

from presales.application.hashing import digest

from .definition import source_ids, target_ids


def quantities(items: list[dict]) -> dict:
    totals = defaultdict(lambda: Decimal(0))
    for item in items:
        totals[(item["group_name"], item["product_id"])] += Decimal(item["quantity"])
    return totals


def rule_groups(rule: dict, totals: dict) -> dict:
    grouped = defaultdict(list)
    sources = set(source_ids(rule))
    for (group, product_id), quantity in totals.items():
        if product_id in sources:
            grouped[group].append({"product_id": product_id, "quantity": str(quantity)})
    return grouped


def rule_demand(rule: dict, *, contributions: list[dict], engine) -> dict:
    quantity = sum((Decimal(item["quantity"]) for item in contributions), Decimal(0))
    result = engine.calculate(mode=rule["mode"], quantity=str(quantity), factor=rule["factor"])
    return {
        "rule_id": rule["id"],
        "revision": rule["revision"],
        "name": rule["name"],
        "source": rule["source"],
        "sources": rule.get("sources", [rule["source"]]),
        "contributions": contributions,
        "source_selector": rule.get("source_selector"),
        "attribute_snapshot": rule.get("attribute_snapshot", {}),
        "mode": rule["mode"],
        "relation": rule.get("relation", "quantity"),
        "evidence": rule["evidence"],
        **result,
    }


def combined_demand(matches: list[dict]) -> Decimal:
    # Per-system requirements describe the same shared minimum, not additive units.
    minimum = max(
        (Decimal(m["quantity"]) for m in matches if m["mode"] == "per_group"), default=Decimal(0)
    )
    additive = sum(
        (Decimal(m["quantity"]) for m in matches if m["mode"] != "per_group"), Decimal(0)
    )
    return max(minimum, additive)


def suggestions(*, items: list[dict], rules: list[dict], engine) -> list[dict]:
    totals = quantities(items)
    demands = defaultdict(list)
    for rule in rules:
        if rule.get("relation") == "choice":
            continue
        for group, contributions in rule_groups(rule, totals).items():
            demands[(group, rule["target_product_id"])].append(
                rule_demand(rule, contributions=contributions, engine=engine)
            )
    targets = {rule["target_product_id"]: rule["target"] for rule in rules}
    result = []
    for (group, target_id), matches in sorted(demands.items()):
        required = combined_demand(matches)
        existing = totals.get((group, target_id), Decimal(0))
        result.append(
            {
                "id": digest([group, target_id]),
                "group_name": group,
                "target": targets[target_id],
                "required": str(required),
                "existing": str(existing),
                "missing": str(max(required - existing, Decimal(0))),
                "surplus": str(max(existing - required, Decimal(0))),
                "rules": matches,
                "mandatory": any(m["relation"] == "required" for m in matches),
            }
        )
    return result


def choice_checks(*, items: list[dict], rules: list[dict], engine) -> list[dict]:
    totals = quantities(items)
    checks = []
    for rule in rules:
        if rule.get("relation") != "choice":
            continue
        for group, contributions in rule_groups(rule, totals).items():
            demand = rule_demand(rule, contributions=contributions, engine=engine)
            existing = sum(
                (totals.get((group, p), Decimal(0)) for p in target_ids(rule)), Decimal(0)
            )
            missing = max(Decimal(demand["quantity"]) - existing, Decimal(0))
            checks.append(
                {
                    "id": digest([group, rule["id"]]),
                    "group_name": group,
                    "rule": demand,
                    "targets": rule["targets"],
                    "required": demand["quantity"],
                    "existing": str(existing),
                    "missing": str(missing),
                    "status": "needs_selection" if missing else "quantity_satisfied",
                }
            )
    return checks
