"""Describe prospective requirements with the same pinned definitions used by checks."""

from pydantic import Field

from ..catalog.attributes import attribute_definitions
from ..common import Entities, Input
from ..knowledge.semantics import role_matches
from .accessory_inputs import accessory_inputs, merged_inputs
from .generation import generation_coverage
from .readiness import package_readiness
from .service import Definitions


class RequirementDescription(Input):
    definition_id: str = ""
    knowledge_package_id: str = ""
    definition_snapshot_id: str | None = None
    knowledge_snapshot_id: str | None = None
    catalog_snapshot_id: str | None = None
    features: list[str] = Field(default_factory=list)


def definitions_for(session, snapshot_id):
    if snapshot_id:
        return Entities(session).get(snapshot_id, kind="definition_snapshot").payload
    return Definitions(session).current_snapshot()


def active_required_roles(definition, features):
    if definition.get("status") != "confirmed":
        return []
    return [
        r
        for r in definition["roles"]
        if r["required"] and (not r["feature"] or r["feature"] in features)
    ]


def describe_requirements(definition, *, rules, features, variants=()):
    required = {r["id"] for r in active_required_roles(definition, features)}
    attributes = {a["key"]: a for a in attribute_definitions()}
    profiles = {(p["id"], p["revision"]): p for p in definition.get("inspection_profiles", [])}
    roles = []
    gaps = []
    variants_by_id = {v["id"]: v for v in variants}
    for role in definition["roles"]:
        reference = role.get("inspection_profile")
        profile = profiles.get((reference["id"], reference["revision"])) if reference else None
        if reference and profile is None:
            raise ValueError("系统定义缺少引用的用途检查修订")
        requirement = dict(
            system_definition_id=definition["id"],
            system=definition["name"],
            role_id=role["id"],
            role=role["name"],
        )
        related = [r for r in rules if r["status"] != "disabled" and role_matches(r, requirement)]
        fields = role_fields(profile, related, attributes)
        extra, issues = accessory_inputs(
            requirement, role=role, rules=rules, variants=variants_by_id, attributes=attributes
        )
        fields.extend(extra)
        gaps.extend(issues)
        basis = role.get("quantity_basis")
        if basis and basis.get("input_key"):
            fields.append(
                dict(
                    key=basis["input_key"],
                    label=attributes.get(basis["input_key"], {}).get("label", basis["input_key"]),
                    kind="quantity" if basis["input_unit"] else "number",
                    unit=basis["input_unit"],
                    scope=basis["scope"],
                    purpose="project_input",
                    evidence=[dict(kind="role_quantity", **basis)],
                )
            )
        fields, issues = merged_inputs(fields, role["id"])
        gaps.extend(issues)
        roles.append(
            dict(
                **role,
                active=not role["feature"] or role["feature"] in features,
                necessary=role["id"] in required,
                definition_status=definition["status"],
                inputs=fields,
            )
        )
    return dict(
        definition_id=definition["id"],
        definition_revision=definition["revision"],
        definition_status=definition["status"],
        name=definition["name"],
        roles=roles,
        features=sorted({r["feature"] for r in definition["roles"] if r["feature"]}),
        input_gaps=gaps,
    )


def role_fields(profile, rules, attributes):
    fields = {}
    for metric in (profile or {}).get("metrics", []):
        key = ("system", metric["input_key"], metric["input_unit"])
        fields[key] = dict(
            key=metric["input_key"],
            label=metric["input_label"],
            kind="quantity",
            unit=metric["input_unit"],
            scope="system",
            purpose="project_input",
            evidence=[
                dict(
                    kind="inspection_profile",
                    id=profile["id"],
                    revision=profile["revision"],
                    status=profile["status"],
                )
            ],
        )
    for rule in rules:
        for condition in [*rule["conditions"], *rule.get("activation_conditions", [])]:
            if not condition["field"].startswith("project."):
                continue
            name = condition["field"].removeprefix("project.")
            metric_key = ("system", name, condition["unit"])
            key = metric_key if metric_key in fields else ("role", name, condition["unit"])
            attribute = attributes.get(name, {})
            fields.setdefault(
                key,
                dict(
                    key=name,
                    label=attribute.get("label", name + "（未注册字段）"),
                    kind=("quantity" if condition["unit"] else "number")
                    if condition["operator"] == "range"
                    else (
                        "text"
                        if condition["operator"] == "eq" and attribute.get("kind") == "enum"
                        else attribute.get("kind", "text")
                    ),
                    unit=condition["unit"],
                    scope=key[0],
                    purpose="product_requirement",
                    evidence=[],
                ),
            )
            if condition["operator"] == "eq" and fields[key]["kind"] == "enum":
                fields[key]["kind"] = "text"
            fields[key]["evidence"].append(
                dict(
                    kind="knowledge",
                    id=rule["id"],
                    revision=rule["revision"],
                    status=rule["status"],
                )
            )
    return list(fields.values())


def read_description(session, request, *, catalog=None):
    from presales.lists.catalog_snapshot import DraftCatalog

    from ..catalog.service import CatalogService

    catalog = catalog or (
        DraftCatalog(session, request.catalog_snapshot_id)
        if request.catalog_snapshot_id
        else CatalogService(session)
    )
    snapshot = definitions_for(session, request.definition_snapshot_id)
    package = next(
        (p for p in snapshot["packages"] if p["id"] == request.knowledge_package_id), None
    )
    if request.knowledge_package_id and (
        not package or package["system_definition_id"] != request.definition_id
    ):
        raise ValueError("资料版本不在当前快照中或不属于此系统，请先预览资料升级")
    definition = (
        package["definition"]
        if package
        else next((d for d in snapshot["definitions"] if d["id"] == request.definition_id), None)
    )
    if definition is None:
        raise ValueError("当前快照中未找到系统定义")
    from ..projects.knowledge_snapshot import candidate_knowledge

    rules = (
        package["rules"] if package else candidate_knowledge(session, request.knowledge_snapshot_id)
    )
    return dict(
        **describe_requirements(
            definition, rules=rules, features=request.features, variants=catalog.variants()
        ),
        generation=generation_coverage(definition, package),
        package_id=package["id"] if package else None,
        package_revision=package["revision"] if package else None,
        coverage=package["coverage"] if package else [],
        readiness=package_readiness(
            package, latest={r["id"]: r["revision"] for r in [definition, *rules]}
        )
        if package
        else None,
        notice="资料描述用于填写需求，不自动选择设备；草稿不作为必要性或兼容性依据。",
    )
