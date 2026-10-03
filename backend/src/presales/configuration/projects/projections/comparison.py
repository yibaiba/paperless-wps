from copy import deepcopy

from presales.rules.calculation import digest

from ..calculation.evaluate import business_input

BUSINESS_COLLECTIONS = (
    "rooms",
    "systems",
    "requirements",
    "devices",
    "accessory_allocations",
    "included_allocations",
    "supply_allocations",
)


def configuration_diff(before, after):
    changes = []
    for collection in BUSINESS_COLLECTIONS:
        changes.extend(
            collection_diff(collection, before.get(collection, []), after.get(collection, []))
        )
    if before.get("accessory_choices", []) != after.get("accessory_choices", []):
        changes.append(
            dict(
                kind="accessory_choices",
                id="choices",
                before=before.get("accessory_choices"),
                after=after.get("accessory_choices"),
            )
        )
    for key in (
        "knowledge_snapshot_id",
        "definition_snapshot_id",
        "calculation_version",
        "decision_runtime",
        "decision_bundle_id",
        "quotation",
        "room_inputs",
        "project_inputs",
        "generation",
        "manual_edits",
    ):
        if before.get(key) != after.get(key):
            changes.append(dict(kind=key, id=key, before=before.get(key), after=after.get(key)))
    return changes


def collection_diff(kind, before, after):
    old, new = {i["id"]: i for i in before}, {i["id"]: i for i in after}
    return [
        dict(kind=kind, id=identity, before=old.get(identity), after=new.get(identity))
        for identity in sorted(old.keys() | new.keys())
        if old.get(identity) != new.get(identity)
    ]


def preview_cleanup(checked):
    result = deepcopy(checked["configuration"])
    active = {s["id"] for s in checked["suggestions"] if s.get("selected", True)}
    result["accessory_allocations"] = [
        a for a in result["accessory_allocations"] if a["demand_id"] in active
    ]
    result["included_allocations"] = [
        a for a in result.get("included_allocations", []) if a["demand_id"] in active
    ]
    return result


def preview_fingerprint(*, current, proposed, baseline_revision):
    return digest([business_input(current), proposed, baseline_revision])
