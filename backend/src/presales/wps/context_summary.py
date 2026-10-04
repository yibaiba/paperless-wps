"""Explain the pinned, temporary configuration; never resolve against latest knowledge."""

from collections import defaultdict

from presales.configuration.definitions.gaps import knowledge_gaps
from presales.configuration.projects.projections.comparison import configuration_diff


def knowledge_summary(configuration, definitions, *, system_ids=None):
    packages = {p["id"]: p for p in definitions["packages"]}
    available = {d["id"]: d for d in definitions["definitions"]}
    result = []
    for system in configuration["systems"]:
        if system_ids is not None and system["id"] not in system_ids:
            continue
        package = packages.get(system.get("knowledge_package_id"))
        definition = (
            package["definition"] if package else available.get(system.get("definition_id"))
        )
        gaps = (
            knowledge_gaps(definition, package)
            if definition
            else [
                dict(
                    code="definition_missing",
                    field="definition_id",
                    message="固定版本中没有此系统定义",
                )
            ]
        )
        result.append(
            dict(
                system_id=system["id"],
                system_name=system["name"],
                definition=record_reference(definition),
                package=record_reference(package),
                gaps=[dict(g, system_id=system["id"]) for g in gaps],
            )
        )
    return result


def record_reference(record):
    if record is None:
        return None
    return {key: record[key] for key in ("id", "revision", "name", "status")}


def context_rows(projection, request, *, allowed_sources):
    configuration = projection["checked"]["configuration"]
    evaluated = set(projection["checked"]["evaluation_scope"]["device"])
    bindings = {b["device_id"]: b for b in projection["line_bindings"]}
    supply, uses = defaultdict(list), defaultdict(list)
    for allocation in configuration["supply_allocations"]:
        supply[allocation["device_id"]].append(allocation)
    for requirement in configuration["requirements"]:
        identities = {a["device_id"] for a in requirement.get("allocations", [])}
        if requirement.get("device_id"):
            identities.add(requirement["device_id"])
        for identity in identities:
            uses[identity].append(
                dict(
                    requirement_id=requirement["id"],
                    system_id=requirement["system_id"],
                    role=requirement["role"],
                )
            )
    rows = []
    for device in configuration["devices"]:
        binding = bindings.get(device["id"], {})
        in_area = (
            binding.get("sheet") == request.scope.sheet
            and request.scope.start_row <= binding.get("row", 0) <= request.scope.end_row
        )
        inventory = device["source_id"] in allowed_sources.get(device["variant_id"], []) and any(
            a["source"] == "existing" for a in supply[device["id"]]
        )
        if not (device["id"] in evaluated or in_area or inventory):
            continue
        rows.append(
            dict(
                **{
                    key: device[key]
                    for key in ("id", "name", "kind", "quantity", "variant_id", "source_id")
                },
                line_id=binding.get("line_id"),
                sheet=binding.get("sheet"),
                row=binding.get("row"),
                participation="dependency"
                if device["id"] in evaluated
                else "inventory"
                if inventory
                else "business_area",
                supply_allocations=supply[device["id"]],
                uses=uses[device["id"]],
            )
        )
    return rows


def completion_context_summary(projection, *, request, profile, context, issues):
    configuration = projection["checked"]["configuration"]
    system = next(s for s in configuration["systems"] if s["id"] == request.scope.system_id)
    room = next((r for r in configuration["rooms"] if r["id"] == system["room_id"]), None)
    # PlanningContext already loaded this immutable definition snapshot for the request.
    return dict(
        mode="business",
        project_id=projection["state"]["binding"].payload["project_id"],
        scope=request.scope.model_dump(mode="json"),
        system={key: system[key] for key in ("id", "name", "kind")},
        room=room,
        versions=projection["versions"],
        local_revision=request.local_revision,
        catalog_scope=profile["catalog_scope"],
        rows=context_rows(projection, request, allowed_sources=context.allowed_sources or {}),
        local_changes=[
            {key: change[key] for key in ("kind", "id")}
            for change in configuration_diff(
                projection["state"]["configuration"],
                configuration,
            )
        ],
        knowledge=knowledge_summary(configuration, context.definitions, system_ids={system["id"]}),
        issues=issues,
    )
