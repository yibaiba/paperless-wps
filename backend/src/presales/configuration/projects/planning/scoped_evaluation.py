"""Run the existing checker on the dependency closure, retaining the full local overlay."""

from copy import deepcopy

from ..schemas import Configuration
from ..services.definition_snapshot import project_knowledge, resolve_definitions


class ScopedEvaluation:
    def __init__(self, scope):
        self.scope = scope

    def partition(self, data, *, session):
        full = data.model_dump(mode="json") if isinstance(data, Configuration) else deepcopy(data)
        definitions, _ = resolve_definitions(session, full)
        rules = project_knowledge(full, definitions)
        identities = self.scope.closure(full, rules)
        selected = dict(full)
        selected["systems"] = [s for s in full["systems"] if s["id"] in identities["system"]]
        selected["requirements"] = [
            r for r in full["requirements"] if r["system_id"] in identities["system"]
        ]
        selected["devices"] = [d for d in full["devices"] if d["id"] in identities["device"]]
        for key in ("accessory_allocations", "included_allocations", "supply_allocations"):
            selected[key] = [a for a in full[key] if a["device_id"] in identities["device"]]
        selected["accessory_choices"] = [
            c for c in full["accessory_choices"] if c["demand_id"] in identities["demand"]
        ]
        selected["quotation"] = scoped_quote(full.get("quotation"), identities["device"])
        # Drawings are retained verbatim in the full overlay, not rebuilt for an incomplete view.
        selected["drawing_xml"] = ""
        return EvaluationPartition(full, Configuration.model_validate(selected), identities)


def scoped_quote(quote, devices):
    if quote is None:
        return None
    return dict(
        quote,
        prices=[p for p in quote["prices"] if p["device_id"] in devices],
        sections={k: v for k, v in quote["sections"].items() if k in devices},
        descriptions={k: v for k, v in quote["descriptions"].items() if k in devices},
    )


class EvaluationPartition:
    def __init__(self, full, selected, identities):
        self.full, self.selected, self.identities = full, selected, identities

    def restore(self, checked):
        computed = checked["configuration"]
        devices = {d["id"]: d for d in computed["devices"]}
        configuration = dict(
            self.full,
            devices=[devices.get(d["id"], d) for d in self.full["devices"]],
            quotation=self.restore_quote(computed.get("quotation")),
        )
        for key in (
            "definition_snapshot_id",
            "knowledge_snapshot_id",
            "knowledge_snapshot",
            "decision_bundle_id",
        ):
            configuration[key] = computed[key]
        return dict(
            checked,
            configuration=configuration,
            evaluation_scope={key: sorted(ids) for key, ids in self.identities.items()},
        )

    def restore_quote(self, computed):
        if computed is None:
            return self.full.get("quotation")
        original = self.full.get("quotation") or {}
        devices = self.identities["device"]
        return dict(
            computed,
            prices=[p for p in original.get("prices", []) if p["device_id"] not in devices]
            + computed["prices"],
            sections={**original.get("sections", {}), **computed["sections"]},
            descriptions={**original.get("descriptions", {}), **computed["descriptions"]},
        )
