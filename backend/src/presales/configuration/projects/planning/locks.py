"""Preserve explicit split selections and expose quantity changes through normal checks."""

from ..role_allocations import device_ids
from ..services.manual_edits import marked


def locked_split_branch(data, requirement, *, reusable_ids):
    allocations = requirement.get("allocations", [])
    devices = {d["id"]: d for d in data["devices"]}
    protected = [
        a["device_id"]
        for a in allocations
        if (
            not devices[a["device_id"]].get("generated_origin")
            and a["device_id"] not in reusable_ids
        )
        or any(
            (devices[a["device_id"]].get("generated_origin") or {}).get(key)
            for key in ("variant_locked", "quantity_locked")
        )
    ]
    if not protected and not marked(data, "requirements", requirement["id"]):
        return None
    # Retain the whole explicit assignment: silently redistributing its unlocked
    # portion would also change the meaning of the user's mixed configuration.
    return (
        data,
        [],
        [
            dict(
                requirement_id=requirement["id"],
                device_ids=device_ids(requirement),
                allocations=allocations,
                reason="保留人工角色关联或包含锁定设备的拆分选型；数量变化由角色分配检查提示",
            )
        ],
    )
