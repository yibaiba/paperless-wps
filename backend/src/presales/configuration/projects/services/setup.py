"""One explicit system setup batch, reused by web preview and MCP edits."""

from copy import deepcopy
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from ...common import Input
from ...definitions.requirements import RequirementDescription, read_description
from ..schemas import Configuration, EnvironmentParameter, Room, System


class SystemSetup(Input):
    system: System
    features_confirmed: bool | None = None
    new_room: Room | None = None
    role_ids: list[str] = Field(default_factory=list)
    role_environment: dict[str, list[EnvironmentParameter]] = Field(default_factory=dict)


class SetupPreview(Input):
    configuration: Configuration
    setup: SystemSetup


def apply_setup(configuration, setup, *, session):
    data = deepcopy(configuration)
    system = setup.system.model_dump(mode="json")
    description = read_description(
        session,
        RequirementDescription(
            definition_id=system["definition_id"],
            knowledge_package_id=system["knowledge_package_id"],
            definition_snapshot_id=data.get("definition_snapshot_id"),
            knowledge_snapshot_id=data.get("knowledge_snapshot_id"),
            features=system["features"],
        ),
    )
    roles = {r["id"]: r for r in description["roles"]}
    if (set(setup.role_ids) | set(setup.role_environment)) - roles.keys():
        raise ValueError("选择的角色不属于当前资料版本")
    if setup.new_room:
        room = setup.new_room.model_dump(mode="json")
        previous = next((r for r in data["rooms"] if r["id"] == room["id"]), None)
        if previous and previous != room:
            raise ValueError("新房间标识已存在，请明确选择已有房间")
        if system["room_id"] != room["id"]:
            raise ValueError("系统与新建房间关联不一致")
        if not previous:
            data["rooms"].append(room)
    if any(s["id"] == system["id"] for s in data["systems"]):
        data["systems"] = [system if s["id"] == system["id"] else s for s in data["systems"]]
    else:
        data["systems"].append(system)
    if setup.features_confirmed is not None:
        confirmed = [i for i in data["generation"]["features_confirmed"] if i != system["id"]]
        data["generation"]["features_confirmed"] = sorted(
            set(confirmed) | ({system["id"]} if setup.features_confirmed else set())
        )
    for identity in dict.fromkeys(setup.role_ids):
        matches = [
            r
            for r in data["requirements"]
            if r["system_id"] == system["id"] and r.get("role_id") == identity
        ]
        if len(matches) > 1 and identity in setup.role_environment:
            raise ValueError("该角色已有多项需求，请分别编辑环境，不批量覆盖")
        if matches:
            if identity in setup.role_environment:
                matches[0]["environment"] = [
                    v.model_dump(mode="json") for v in setup.role_environment[identity]
                ]
            continue
        data["requirements"].append(
            dict(
                id=str(uuid5(NAMESPACE_URL, f"presales-role:{system['id']}:{identity}")),
                system_id=system["id"],
                role_id=identity,
                role=roles[identity]["name"],
                device_id=None,
                environment=[
                    v.model_dump(mode="json") for v in setup.role_environment.get(identity, [])
                ],
                resources=[],
            )
        )
    return Configuration.model_validate(data).model_dump(mode="json")
