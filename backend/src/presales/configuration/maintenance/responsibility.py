"""Read old saved coverage records without rewriting or parsing their message text."""


def is_knowledge_gap(check, project):
    if check["kind"] != "coverage":
        return True
    if check.get("responsibility"):
        return check["responsibility"] == "knowledge"
    # Legacy role-coverage checks always identify the selected device. Role binding
    # failures identify a requirement/role but have no selected-device reference.
    if check.get("device_id"):
        return True
    if check.get("requirement_id") or check.get("role_id"):
        return False
    system_id = check.get("system_id")
    if not system_id:
        return False
    data = project["configuration"]
    system = next(s for s in data["systems"] if s["id"] == system_id)
    definitions = project.get("definitions", {})
    package = next(
        (
            p
            for p in definitions.get("packages", [])
            if p["id"] == system.get("knowledge_package_id")
        ),
        None,
    )
    definition = (
        package["definition"]
        if package
        else next(
            (
                d
                for d in definitions.get("definitions", [])
                if d["id"] == system.get("definition_id")
            ),
            None,
        )
    )
    # For a confirmed definition, a legacy system-only check means that this
    # project did not instantiate its roles. Unconfirmed definitions need knowledge work.
    return not definition or definition["status"] != "confirmed"
