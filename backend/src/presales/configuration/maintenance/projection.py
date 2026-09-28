"""Knowledge work is grouped by evidence identity, never by the wording of a warning."""

from presales.rules.calculation import digest

from ..projects.calculation.demands import quantity_missing

KNOWLEDGE_KINDS = {"compatibility", "coverage", "resource_policy", "inspection", "sharing"}


def project_findings(project):
    data = project["configuration"]
    requirements = {r["id"]: r for r in data["requirements"]}
    devices = {d["id"]: d for d in data["devices"]}
    systems = {s["id"]: s for s in data["systems"]}
    for check in project.get("checks", []):
        if check["status"] == "pass" or check["kind"] not in KNOWLEDGE_KINDS:
            continue
        role_ids = (
            check.get("requirement_ids")
            or check.get("action", {}).get("requirement_ids")
            or [check.get("requirement_id")]
        )
        for role_id in role_ids:
            role = requirements.get(role_id, {})
            system = systems.get(check.get("system_id") or role.get("system_id"), {})
            device = devices.get(check.get("device_id"), {})
            identity = check_identity(
                check,
                role=role,
                system=system,
                device=device,
                definitions=project.get("definitions", {}),
                snapshot=data.get("knowledge_snapshot", []),
            )
            yield dict(
                identity=identity,
                kind=check["kind"],
                title=check.get("message") or "产品适配依据待确认",
                action=check.get("action", {}),
                rule_id=check.get("rule_id"),
                profile_id=check.get("profile_id"),
                objects=[device.get("name") or role.get("role") or system.get("name", "系统知识")],
                evidence=check.get("evidence", []),
            )
    for demand in project.get("suggestions", []):
        if demand.get("selected", True) is False or demand["status"] == "pass":
            continue
        rule = demand["rule"]
        missing = sorted(quantity_missing(rule))
        if not missing:
            continue
        yield dict(
            identity=["accessory", rule["id"], rule["revision"], missing],
            kind="accessory",
            title=(demand.get("need_name") or rule["name"]) + "：" + "；".join(missing),
            action=dict(type="edit_knowledge", rule_id=rule["id"]),
            rule_id=rule["id"],
            profile_id=None,
            used_revision=rule["revision"],
            objects=[demand.get("need_name") or rule["name"]],
            evidence=demand.get("evidence", []),
        )


def check_identity(check, *, role, system, device, definitions, snapshot):
    if check.get("profile_id"):
        return [check["kind"], "profile", check["profile_id"], check.get("profile_revision")]
    if check.get("rule_id"):
        return [
            check["kind"],
            "rule",
            check["rule_id"],
            check.get("rule_revision")
            or next((r["revision"] for r in snapshot or [] if r["id"] == check["rule_id"]), None),
        ]
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
            {},
        )
    )
    return [
        check["kind"],
        system.get("definition_id") or system.get("kind"),
        definition.get("revision"),
        package["id"] if package else None,
        package["revision"] if package else None,
        check.get("role_id") or role.get("role_id") or role.get("role"),
        device.get("variant_id"),
        (device.get("variant_snapshot") or {}).get("revision"),
        sorted((e.get("id", ""), e.get("revision", 0)) for e in check.get("evidence", [])),
    ]


def maintenance_tasks(projects, current_revisions):
    grouped = {}
    for project in projects:
        for finding in project_findings(project):
            key = digest(finding["identity"])
            task = grouped.setdefault(
                key,
                dict(
                    id=key,
                    kind=finding["kind"],
                    title=finding["title"],
                    owner="知识维护者",
                    action=finding["action"],
                    evidence=finding["evidence"],
                    impacts=[],
                ),
            )
            impact = dict(
                project_id=project["project_id"],
                project_name=project["name"],
                revision=project["revision"],
                objects=finding["objects"],
            )
            if impact not in task["impacts"]:
                task["impacts"].append(impact)
            identity = finding.get("rule_id") or finding.get("profile_id")
            used = finding.get("used_revision") or next(
                (e.get("revision") for e in finding["evidence"] if e.get("id") == identity), None
            )
            if finding["identity"][1:2] in (["profile"], ["rule"]):
                used = finding["identity"][-1]
            task["newer_knowledge_available"] = bool(
                task.get("newer_knowledge_available")
                or (identity and used and current_revisions.get(identity, used) > used)
            )
    for task in grouped.values():
        task["project_count"] = len({i["project_id"] for i in task["impacts"]})
    return sorted(grouped.values(), key=lambda t: (-t["project_count"], t["kind"], t["id"]))
