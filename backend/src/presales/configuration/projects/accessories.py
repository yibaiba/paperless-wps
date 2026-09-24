from decimal import Decimal

from presales.rules.calculation import digest

from ..knowledge.evaluator import context_for, evaluate_rules, scope_matches


def accessory_suggestions(data, *, variants, catalog_variants, engine):
    if data.get("calculation_version", 1) >= 2:
        from .accessory_demands import calculate_accessory_demands

        return calculate_accessory_demands(
            data, variants=variants, catalog_variants=catalog_variants, engine=engine
        )
    return legacy_accessory_suggestions(data, variants=variants, engine=engine)


def legacy_accessory_suggestions(data, *, variants, engine):
    suggestions = []
    for device in data["devices"]:
        variant = variants[device["id"]]
        applicable = [
            k
            for k in data["knowledge_snapshot"]
            if k["kind"] == "accessory"
            and k["status"] == "confirmed"
            and scope_matches(variant, k["selector"])
        ]
        contexts = [
            context_for(variant, r["environment"])
            for r in data["requirements"]
            if r["device_id"] == device["id"]
        ] or [context_for(variant, [])]
        for rule in (k for k in applicable if k["effect"] == "allow"):
            denials = [
                k
                for k in applicable
                if k["effect"] == "deny"
                and set(k["target_variant_ids"]) & set(rule["target_variant_ids"])
            ]
            results = [evaluate_rules([rule, *denials], context) for context in contexts]
            status = (
                "conflict"
                if any(r["status"] == "conflict" for r in results)
                else "unknown"
                if any(r["status"] == "unknown" for r in results)
                else "pass"
            )
            key = digest([device["id"], rule["id"]])
            suggestion = dict(
                id=key,
                parent_id=device["id"],
                rule=rule,
                status=status,
                evidence=[e for r in results for e in r["evidence"]],
            )
            if status == "pass":
                suggestion.update(quantities(device, rule=rule, data=data, engine=engine))
            suggestions.append(suggestion)
    return suggestions


def quantities(device, *, rule, data, engine):
    calculated = engine.calculate(
        mode=rule["mode"], quantity=device["quantity"], factor=rule["factor"]
    )
    key = digest([device["id"], rule["id"]])
    existing = sum(
        (
            Decimal(d["quantity"])
            for d in data["devices"]
            if d.get("origin_suggestion") == key and d["variant_id"] in rule["target_variant_ids"]
        ),
        Decimal(0),
    )
    required = Decimal(calculated["quantity"])
    return dict(
        required=str(required),
        existing=str(existing),
        missing=str(max(required - existing, Decimal(0))),
        calculation={k: calculated[k] for k in ("engine", "expression", "input")},
    )
