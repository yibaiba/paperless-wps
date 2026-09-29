"""Preserve explicit split selections and expose quantity changes through normal checks."""


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
    if not protected:
        return None
    # Retain the whole explicit assignment: silently redistributing its unlocked
    # portion would also change the meaning of the user's mixed configuration.
    return (
        data,
        [],
        [
            dict(
                requirement_id=requirement["id"],
                device_ids=[a["device_id"] for a in allocations],
                allocations=allocations,
                reason="保留包含人工锁定设备的拆分选型；数量变化由角色分配检查提示",
            )
        ],
    )
