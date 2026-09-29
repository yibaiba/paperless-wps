"""One deletion projection for explicit edits and adopted proposal removals."""

from copy import deepcopy

from ..drawing import remove_device_references
from ..planning.references import remove_generation_references
from ..role_allocations import unbind_device
from .manual_edits import prune


def remove_devices(configuration, identities, *, demands):
    data = deepcopy(configuration)
    removed = set(identities)
    removed_demands = {
        s["id"] for s in demands if s.get("scope") == "device" and s.get("scope_id") in removed
    }
    data["devices"] = [d for d in data["devices"] if d["id"] not in removed]
    for identity in removed:
        data["requirements"] = [unbind_device(r, identity) for r in data["requirements"]]
        data["drawing_xml"] = remove_device_references(data["drawing_xml"], identity)
    for collection in ("accessory_allocations", "included_allocations", "supply_allocations"):
        data[collection] = [
            a
            for a in data[collection]
            if a["device_id"] not in removed and a.get("demand_id") not in removed_demands
        ]
    data["accessory_choices"] = [
        a for a in data["accessory_choices"] if a["demand_id"] not in removed_demands
    ]
    if data.get("quotation"):
        data["quotation"]["prices"] = [
            p for p in data["quotation"]["prices"] if p["device_id"] not in removed
        ]
        for field in ("sections", "descriptions"):
            data["quotation"][field] = {
                k: v for k, v in data["quotation"].get(field, {}).items() if k not in removed
            }
    data["generation"] = remove_generation_references(data["generation"], removed)
    return prune(data)
