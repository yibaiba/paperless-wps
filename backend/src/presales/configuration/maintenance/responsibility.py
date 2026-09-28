"""Read old saved coverage records without rewriting or parsing their message text."""


def is_knowledge_gap(check, project):
    if check["kind"] != "coverage":
        return True
    if check.get("responsibility"):
        return check["responsibility"] == "knowledge"
    # Older calculations emitted accessory coverage even for unbound roles.
    # Resolve their saved role before treating the device check as knowledge work.
    if check.get("device_id"):
        return has_defined_role(check, project)
    if check.get("requirement_id") or check.get("role_id"):
        return False
    system_id = check.get("system_id")
    if not system_id:
        return False
    definition = system_definition(system_id, project)
    # A confirmed definition's system-only check means missing project roles.
    return not definition or definition["status"] != "confirmed"


def has_defined_role(check, project):
    requirement = next(
        r for r in project["configuration"]["requirements"] if r["id"] == check["requirement_id"]
    )
    definition = system_definition(requirement["system_id"], project)
    return bool(definition) and any(
        role["id"] == requirement.get("role_id") for role in definition["roles"]
    )


def system_definition(system_id, project):
    system = next(s for s in project["configuration"]["systems"] if s["id"] == system_id)
    definitions = project.get("definitions", {})
    package = next(
        (
            p
            for p in definitions.get("packages", [])
            if p["id"] == system.get("knowledge_package_id")
        ),
        None,
    )
    return (
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
