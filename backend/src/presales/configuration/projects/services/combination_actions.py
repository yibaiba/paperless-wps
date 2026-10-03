"""Separate a proven selection conflict from missing authored knowledge."""


def combination_action(check):
    if check["status"] != "conflict" or not check["generation_enabled"]:
        return {}
    excluded = check["code"] == "combination_exclude"
    group = next(
        (g for g in check["groups"] if (g["present"] if excluded else g["state"] != "pass")),
        None,
    )
    if group is None:
        return {}
    if group["demand_ids"]:
        return dict(type="edit_accessory", demand_id=group["demand_ids"][0])
    if group["requirement_ids"]:
        return dict(type="select_candidate", requirement_id=group["requirement_ids"][0])
    return {}
