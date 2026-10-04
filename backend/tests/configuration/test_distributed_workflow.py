"""Isolated approvals validate generation mechanics, not real distributed compatibility."""

from uuid import uuid4

from .conftest import AUTHOR, post
from .test_proposal_generation import apply, call, plan, read, write

ROLE_INPUTS = (
    ("服务端", "hardware", "", "paperless_server_count"),
    ("服务端软件", "software", "", "paperless_management_count"),
    ("会议平板", "hardware", "平板参会", "paperless_tablet_count"),
    ("客户端软件", "software", "平板参会", "paperless_tablet_license_count"),
    ("信号输入控制器", "hardware", "外部视频输入", "paperless_video_input_count"),
    ("信号输出控制器", "hardware", "视频输出到大屏", "paperless_video_output_count"),
    ("信息发布终端", "hardware", "会议信息发布", "paperless_info_terminal_count"),
    ("信息发布软件", "software", "会议信息发布", "paperless_info_license_count"),
    ("会议服务终端", "hardware", "会议服务", "paperless_service_terminal_count"),
    ("会议服务软件", "software", "会议服务", "paperless_service_license_count"),
    ("候会语音播报终端", "hardware", "候会播报", "paperless_broadcast_terminal_count"),
    ("候会播报软件", "software", "候会播报", "paperless_broadcast_license_count"),
)


def approved_fixture(client, catalog):
    roles, rules, coverage = [], [], []
    for name, kind, feature, key in ROLE_INPUTS:
        roles.append(
            dict(
                id=str(uuid4()),
                name=name,
                output_kind=kind,
                required=True,
                feature=feature,
                quantity_basis=dict(
                    status="confirmed",
                    mode="per_unit",
                    factor="1",
                    input_key=key,
                    scope="system",
                    **AUTHOR,
                ),
            )
        )
    definition = post(
        client,
        "/definitions",
        dict(name="隔离分布式流程", status="confirmed", roles=roles, **AUTHOR),
    )
    for role in roles:
        variant = catalog["variants"][0]["id"]
        rules.append(
            post(
                client,
                "/knowledge",
                dict(
                    name="隔离适用",
                    kind="suitability",
                    status="confirmed",
                    selector=dict(variant_ids=[variant]),
                    system_definition_id=definition["id"],
                    role_id=role["id"],
                    **AUTHOR,
                ),
            )
        )
        coverage.append(
            dict(
                role_id=role["id"],
                selector=dict(variant_ids=[variant]),
                accessories="none",
                resources="not_applicable",
                evidence=AUTHOR["evidence"],
            )
        )
    package = post(
        client,
        "/knowledge-packages",
        dict(
            name="隔离已确认分布式知识",
            branch="仅软件验收",
            status="published",
            system_definition_id=definition["id"],
            definition_revision=definition["revision"],
            members=[dict(id=r["id"], revision=r["revision"]) for r in rules],
            coverage=coverage,
            **AUTHOR,
        ),
    )
    return definition, package


def system_inputs(definition, package):
    values = {key: "1" for _, _, _, key in ROLE_INPUTS}
    values.update(paperless_tablet_count="30", paperless_tablet_license_count="32")
    return dict(
        id="paper",
        room_id="room",
        name="独立分布式",
        kind=definition["name"],
        definition_id=definition["id"],
        knowledge_package_id=package["id"],
        features=sorted({f for _, _, f, _ in ROLE_INPUTS if f}),
        inputs=[dict(key=k, kind="number", value=v) for k, v in values.items()],
    )


def start(client, catalog):
    definition, package = approved_fixture(client, catalog)
    draft = call(
        client, "list_create", dict(name="隔离分布式自动生成", operation_id=str(uuid4()), **AUTHOR)
    )
    system = system_inputs(definition, package)
    draft = write(
        client,
        draft,
        [
            dict(
                action="requirements_patch",
                rooms=[dict(id="room", name="会议室")],
                systems=[dict(system=system, features_confirmed=True)],
                generation=dict(supply_source="purchase", supply_evidence=AUTHOR["evidence"]),
            ),
            dict(action="quotation_set", value=dict(price_column="报价", customer="隔离客户")),
        ],
    )
    return draft, system


def by_role(configuration):
    devices = {d["id"]: d for d in configuration["devices"]}
    return {r["role"]: devices.get(r["device_id"]) for r in configuration["requirements"]}


def test_distributed_generates_twelve_roles_and_requantifies_software_independently(
    client, catalog
):
    draft, system = start(client, catalog)
    proposal = plan(client, draft)
    assert proposal["option"]["device_count"] == 12
    draft = apply(client, draft, proposal)
    original = read(client, draft)["configuration"]
    roles = by_role(original)
    assert roles["客户端软件"]["quantity"] == "32" and roles["会议平板"]["quantity"] == "30"
    assert roles["客户端软件"]["kind"] == "software"
    assert len({d["id"] for d in original["devices"]}) == 12
    system["inputs"] = [
        {**a, "value": "48"} if a["key"] == "paperless_tablet_license_count" else a
        for a in system["inputs"]
    ]
    draft = write(
        client,
        draft,
        [dict(action="requirements_patch", systems=[dict(system=system, features_confirmed=True)])],
    )
    draft = apply(client, draft, plan(client, draft))
    current = read(client, draft)["configuration"]
    roles = by_role(current)
    assert roles["客户端软件"]["quantity"] == "48" and roles["会议平板"]["quantity"] == "30"
    assert {d["id"] for d in original["devices"]} == {d["id"] for d in current["devices"]}


def test_distributed_disabled_features_and_unknown_quantities_do_not_create_default_devices(
    client, catalog
):
    draft, system = start(client, catalog)
    system["features"] = ["平板参会"]
    system["inputs"] = [a for a in system["inputs"] if a["key"] != "paperless_tablet_license_count"]
    draft = write(
        client,
        draft,
        [dict(action="requirements_patch", systems=[dict(system=system, features_confirmed=True)])],
    )
    proposal = plan(client, draft)
    draft = apply(client, draft, proposal)
    roles = by_role(read(client, draft)["configuration"])
    assert roles["客户端软件"] is None
    assert roles["信息发布终端"] is None and roles["候会播报软件"] is None
    assert roles["会议平板"]["quantity"] == "30"
    assert proposal["option"]["status"] == "partial"
