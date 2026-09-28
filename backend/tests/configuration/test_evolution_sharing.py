from copy import deepcopy

from .conftest import AUTHOR, BASE, post
from .test_evolution import modern_rule


def cross_system(client, catalog):
    software, server = catalog["variants"]
    accessory = modern_rule(
        client,
        software,
        kind="accessory",
        system="",
        role="",
        need_key="server",
        target_variant_ids=[server["id"]],
        calculation_scope="system",
        mode="per_group",
        factor="1",
        quantity_review="confirmed",
        quantity_evidence="隔离测试每系统一服务器需求",
        allocation_mode="shareable",
        resource_policy="required",
        output_kind="hardware",
    )
    systems, requirements, devices, refs = [], [], [], []
    for index, name in enumerate(("红盾 Windows 隔离测试", "会议预约隔离测试")):
        system_id, role_id, device_id = f"system{index}", "software", f"software{index}"
        definition = post(
            client,
            "/definitions",
            dict(
                name=name,
                status="confirmed",
                roles=[dict(id=role_id, name="服务端软件")],
                **AUTHOR,
            ),
        )
        suitability = modern_rule(
            client,
            software,
            system=name,
            role="服务端软件",
            system_definition_id=definition["id"],
            role_id=role_id,
        )
        package = post(
            client,
            "/knowledge-packages",
            dict(
                name=name,
                branch="隔离环境",
                status="published",
                system_definition_id=definition["id"],
                definition_revision=1,
                members=[
                    dict(id=r["id"], revision=r["revision"]) for r in (suitability, accessory)
                ],
                coverage=[
                    dict(
                        role_id=role_id,
                        selector={"variant_ids": [software["id"]]},
                        accessories="complete",
                        resources="not_applicable",
                        evidence=AUTHOR["evidence"],
                    )
                ],
                **AUTHOR,
            ),
        )
        systems.append(
            dict(
                id=system_id,
                name=name,
                kind=name,
                room_id="room",
                definition_id=definition["id"],
                knowledge_package_id=package["id"],
            )
        )
        requirements.append(
            dict(
                id=f"r{index}",
                system_id=system_id,
                role="服务端软件",
                role_id=role_id,
                device_id=device_id,
                environment=[],
                resources=[
                    dict(
                        key="memory",
                        amount="40",
                        unit="GB",
                        applies_to="accessory",
                        target_need_key="server",
                    )
                ],
            )
        )
        devices.append(
            dict(
                id=device_id,
                variant_id=software["id"],
                source_id=catalog["sources"][0]["id"],
                name=name,
                quantity="1",
                kind="software",
            )
        )
        refs.append(dict(system_definition_id=definition["id"], role_id=role_id))
    data = dict(
        calculation_version=3,
        rooms=[dict(id="room", name="隔离会议室")],
        systems=systems,
        requirements=requirements,
        devices=devices,
        **AUTHOR,
    )
    return data, refs


def add_server(data, catalog, identity):
    data["devices"].append(
        dict(
            id=identity,
            name="隔离服务器",
            variant_id=catalog["variants"][1]["id"],
            source_id=catalog["sources"][1]["id"],
            quantity="1",
            kind="hardware",
        )
    )


def allocate(data, demands, server_ids):
    data["accessory_allocations"] = [
        dict(
            id=f"a{index}",
            demand_id=d["id"],
            device_id=server_ids[index],
            quantity="1",
            evidence=AUTHOR["evidence"],
        )
        for index, d in enumerate(demands)
    ]
    data["supply_allocations"] = [
        dict(
            id="supply-" + d["id"],
            device_id=d["id"],
            quantity=d["quantity"],
            source="purchase",
            evidence=AUTHOR["evidence"],
        )
        for d in data["devices"]
    ]


def test_shared_separate_existing_over_capacity_delete(client, catalog):
    data, refs = cross_system(client, catalog)
    initial = post(client, "/check", dict(configuration=data))
    assert len(initial["suggestions"]) == 2
    independent = deepcopy(initial["configuration"])
    add_server(independent, catalog, "server0")
    add_server(independent, catalog, "server1")
    allocate(independent, initial["suggestions"], ["server0", "server1"])
    independent_check = post(client, "/check", dict(configuration=independent))
    assert independent_check["readiness"]["ready_for_confirmation"]
    assert (
        len(
            [
                line
                for line in independent_check["project_output"]["procurement_lines"]
                if line["kind"] == "hardware"
            ]
        )
        == 2
    )

    shared = deepcopy(initial["configuration"])
    add_server(shared, catalog, "shared")
    allocate(shared, initial["suggestions"], ["shared", "shared"])
    unknown = post(client, "/check", dict(configuration=shared))
    assert next(c for c in unknown["checks"] if c["kind"] == "sharing")["status"] == "unknown"
    modern_rule(client, catalog["variants"][1], kind="sharing", shared_role_refs=refs)
    passed = post(client, "/check", dict(configuration=shared, refresh_knowledge=True))
    assert passed["readiness"]["ready_for_confirmation"]
    assert (
        len(
            [
                line
                for line in passed["project_output"]["procurement_lines"]
                if line["kind"] == "hardware"
            ]
        )
        == 1
    )
    used = next(u for u in passed["device_usages"] if u["device_id"] == "shared")
    assert len({c["system_id"] for c in used["consumers"]}) == 2

    existing = deepcopy(passed["configuration"])
    next(a for a in existing["supply_allocations"] if a["device_id"] == "shared")["source"] = (
        "existing"
    )
    checked = post(client, "/check", dict(configuration=existing))
    assert not [
        line
        for line in checked["project_output"]["procurement_lines"]
        if line["kind"] == "hardware"
    ]
    assert len(checked["project_output"]["lines"]) == 3
    existing["requirements"][0]["resources"][0]["amount"] = "120"
    assert any(
        c["status"] == "conflict"
        for c in post(client, "/check", dict(configuration=existing))["checks"]
        if c["kind"] == "capacity"
    )
    existing["devices"] = [d for d in existing["devices"] if d["id"] != "shared"]
    existing["accessory_allocations"] = []
    existing["supply_allocations"] = [
        a for a in existing["supply_allocations"] if a["device_id"] != "shared"
    ]
    assert [
        s["missing"] for s in post(client, "/check", dict(configuration=existing))["suggestions"]
    ] == ["1", "1"]


def test_quantity_change_preview_cleanup_and_repeated_apply(client, catalog, project):
    data, _ = cross_system(client, catalog)
    checked = post(client, "/check", dict(configuration=data))
    suggestion = checked["suggestions"][0]
    request = dict(
        configuration=checked["configuration"],
        fingerprint=checked["fingerprint"],
        suggestion_id=suggestion["id"],
        variant_id=catalog["variants"][1]["id"],
        source_id=catalog["sources"][1]["id"],
    )
    applied = post(client, "/apply", request)
    repeated = post(
        client,
        "/apply",
        dict(request, configuration=applied["configuration"], fingerprint=applied["fingerprint"]),
    )
    assert len(repeated["configuration"]["devices"]) == 3
    saved = client.put(
        BASE + "/projects/" + project["id"],
        json=dict(expected_revision=0, configuration=applied["configuration"]),
    ).json()
    changed = deepcopy(saved["configuration"])
    changed["requirements"] = []
    preview = post(
        client,
        f"/projects/{project['id']}/change-preview",
        dict(configuration=changed, expected_revision=1, cleanup_allocations=True),
    )
    assert preview["checked"]["configuration"]["accessory_allocations"] == []
    assert client.get(BASE + "/projects/" + project["id"]).json()["configuration"][
        "accessory_allocations"
    ]


def test_identity_mapping_does_not_confirm_definitions_and_is_repeatable(client, catalog):
    modern_rule(client, catalog["variants"][0])
    before = post(client, "/check", dict(configuration={**AUTHOR, "calculation_version": 3}))
    preview = client.get(BASE + "/definition-mapping-preview").json()
    post(client, "/definition-mapping-apply", dict(fingerprint=preview["fingerprint"], **AUTHOR))
    definitions = client.get(BASE + "/definitions").json()["definitions"]
    assert len(definitions) == 1 and definitions[0]["status"] == "draft"
    again = client.get(BASE + "/definition-mapping-preview").json()
    post(client, "/definition-mapping-apply", dict(fingerprint=again["fingerprint"], **AUTHOR))
    assert client.get(BASE + "/definitions").json()["definitions"] == definitions
    assert before["configuration"]["definition_snapshot_id"]
