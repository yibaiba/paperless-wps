"""Disambiguate mixed rule revisions without rewriting historical allocations."""

from collections import defaultdict

from presales.rules.calculation import digest


class DemandIdentities:
    def __init__(self, data, *, rules):
        revisions = defaultdict(set)
        for rule in rules:
            revisions[rule["id"]].add(rule["revision"])
        self.mixed = frozenset(key for key, values in revisions.items() if len(values) > 1)
        self.referenced = frozenset(
            item["demand_id"]
            for collection in ("accessory_allocations", "included_allocations", "accessory_choices")
            for item in data.get(collection, [])
        ) | frozenset(d.get("origin_suggestion") for d in data["devices"])

    def identity(self, rule, scope_id):
        components = [rule["id"], rule.get("calculation_scope"), scope_id]
        qualified = digest([*components, {"rule_revision": rule["revision"]}])
        # Keep a qualified reference stable after the other system is removed.
        # Ambiguous legacy references remain unresolved for explicit reassignment.
        if rule["id"] in self.mixed or qualified in self.referenced:
            return qualified
        return digest(components)
