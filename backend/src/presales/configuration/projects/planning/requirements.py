"""Structured inputs never promote unconfirmed interpretations to hard requirements."""

from copy import deepcopy

from ...definitions.requirements import RequirementDescription, read_description
from ..schemas import Configuration
from ..services.setup import SystemSetup, apply_setup


def patch_requirements(configuration, operation, *, repository):
    data = deepcopy(configuration)
    if operation.generation is not None:
        data["generation"] = operation.generation.model_dump(mode="json")
    data.setdefault("generation", {})
    for room in operation.rooms:
        value = room.model_dump(mode="json")
        data["rooms"] = [r for r in data["rooms"] if r["id"] != room.id] + [value]
    for item in operation.systems:
        description = read_description(
            repository.session,
            RequirementDescription(
                definition_id=item.system.definition_id,
                knowledge_package_id=item.system.knowledge_package_id,
                definition_snapshot_id=data.get("definition_snapshot_id"),
                features=item.system.features,
            ),
        )
        role_ids = list(
            dict.fromkeys(
                [r["id"] for r in description["roles"] if r["necessary"]]
                + [r.role_id for r in item.roles]
            )
        )
        setup = SystemSetup(
            system=item.system,
            features_confirmed=item.features_confirmed,
            role_ids=role_ids,
            role_environment={
                r.role_id: r.environment for r in item.roles if r.environment is not None
            },
        )
        data = apply_setup(data, setup, session=repository.session)
        apply_role_resources(data, item)
    if operation.room_inputs is not None:
        data["room_inputs"] = {
            k: [a.model_dump(mode="json") for a in v] for k, v in operation.room_inputs.items()
        }
    if operation.project_inputs is not None:
        data["project_inputs"] = [a.model_dump(mode="json") for a in operation.project_inputs]
    validate_preferences(data, repository=repository)
    validate_interpretations(configuration, data)
    return Configuration.model_validate(data).model_dump(mode="json")


def validate_preferences(data, *, repository):
    requirements = {r["id"] for r in data["requirements"]}
    devices = {d["id"] for d in data["devices"]}
    variants = {v["id"] for v in repository.catalog.variants()}
    for preference in data.get("generation", {}).get("preferences", []):
        if preference["requirement_id"] not in requirements:
            raise ValueError("选型偏好引用的需求不存在")
        if set(preference["reusable_device_ids"]) - devices:
            raise ValueError("允许复用的设备不存在")
        selected = {preference["required_variant_id"]} - {""}
        if (selected | set(preference["excluded_variant_ids"])) - variants:
            raise ValueError("指定或排除的配置不在当前产品快照内")


def validate_interpretations(before, after):
    """Unconfirmed source fields can be recorded but must not change effective inputs."""
    objects = requirement_objects(after)
    old = requirement_objects(before)
    for source in after.get("generation", {}).get("sources", []):
        if source["confirmed"] or source["kind"] != "agent_interpretation":
            continue
        value = objects.get(source["object_id"], {})
        previous = old.get(source["object_id"], {})
        field = source["field"]
        if field_value(value, field) != field_value(previous, field):
            raise ValueError("Agent 待确认理解只能记录原文，确认后再修改对应有效需求：" + field)


def requirement_objects(data):
    objects = {i["id"]: i for key in ("systems", "requirements") for i in data[key]}
    for room in data["rooms"]:
        objects[room["id"]] = dict(room, inputs=data.get("room_inputs", {}).get(room["id"], []))
    objects["project"] = data
    return objects


def field_value(value, field):
    for key in field.split("."):
        if isinstance(value, dict):
            value = value.get(key)
        elif isinstance(value, list):
            value = next(
                (item for item in value if isinstance(item, dict) and item.get("key") == key), None
            )
        else:
            return None
    return value


def apply_role_resources(data, item):
    for role in item.roles:
        if role.resources is not None:
            for requirement in data["requirements"]:
                if (
                    requirement["system_id"] == item.system.id
                    and requirement["role_id"] == role.role_id
                ):
                    requirement["resources"] = [r.model_dump(mode="json") for r in role.resources]
