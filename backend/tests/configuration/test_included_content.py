from copy import deepcopy
from uuid import uuid4

import pytest

from .conftest import AUTHOR, BASE, post
from .test_evolution import modern_rule
from .test_list_mcp import call, mutation
from .test_web_drafts import start, write


def update_variant(client, variant, **changes):
    payload = {k: v for k, v in variant.items() if k not in {"id", "revision", "updated_at"}}
    response = client.put(
        BASE + "/variants/" + variant["id"],
        json=dict(expected_revision=variant["revision"], payload={**payload, **changes}),
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def included(client, catalog, config):
    host, target = catalog["variants"]
    fact = dict(
        id="bundled",
        name="隔离测试内置授权",
        variant_id=target["id"],
        kind="license",
        quantity="1",
        need_keys=["client-license"],
        status="confirmed",
        evidence=AUTHOR["evidence"],
    )
    host = update_variant(client, host, included_items=[fact])
    rule = modern_rule(
        client,
        host,
        kind="accessory",
        need_key="client-license",
        need_name="终端授权",
        target_variant_ids=[target["id"]],
        calculation_scope="device",
        mode="per_unit",
        factor="1",
        quantity_review="confirmed",
        quantity_evidence=AUTHOR["evidence"],
        output_kind="license",
        resource_policy="not_applicable",
    )
    checked = post(client, "/check", dict(configuration={**config, "calculation_version": 3}))
    return dict(host=host, target=target, fact=fact, rule=rule, checked=checked)


def allocation(included, **changes):
    checked = included["checked"]
    offer = checked["suggestions"][0]["included_offers"][0]
    return dict(
        id="credit",
        demand_id=checked["suggestions"][0]["id"],
        quantity="1",
        evidence=AUTHOR["evidence"],
        **{
            k: offer[k]
            for k in ("device_id", "included_item_id", "host_variant_id", "host_variant_revision")
        },
        **changes,
    )


def checked_with(client, included, allocations):
    data = dict(included["checked"]["configuration"], included_allocations=allocations)
    return post(client, "/check", dict(configuration=data))


def test_explicit_credit_no_procurement_and_no_input_mutation(client, included):
    original = deepcopy(included)
    assert included["checked"]["suggestions"][0]["missing"] == "1"
    result = checked_with(client, included, [allocation(included)])
    demand = result["suggestions"][0]
    assert (demand["missing"], demand["included_quantity"], demand["separately_allocated"]) == (
        "0",
        "1",
        "0",
    )
    assert len(result["configuration"]["devices"]) == len(result["project_output"]["lines"]) == 1
    assert included == original
    assert (
        next(c for c in result["checks"] if c["kind"] == "included_allocation")["status"] == "pass"
    )


@pytest.mark.parametrize(
    "change",
    [
        dict(status="draft"),
        dict(quantity=None, status="draft"),
        dict(need_keys=["different"]),
        dict(kind="software"),
        dict(status="disabled"),
    ],
)
def test_unconfirmed_or_mismatched_fact_does_not_credit(client, included, change):
    host = update_variant(client, included["host"], included_items=[{**included["fact"], **change}])
    data = dict(
        included["checked"]["configuration"],
        included_allocations=[{**allocation(included), "host_variant_revision": host["revision"]}],
    )
    result = post(client, "/check", dict(configuration=data, refresh_knowledge=True))
    assert result["suggestions"][0]["missing"] == "1"
    assert any(
        c["status"] != "pass" for c in result["checks"] if c["kind"] == "included_allocation"
    )


def test_historical_snapshot_refresh_and_omitted_field_preserved(client, included):
    credited = checked_with(client, included, [allocation(included)])
    host = update_variant(client, included["host"], name="新名称")
    legacy_payload = {
        k: v for k, v in host.items() if k not in {"id", "revision", "updated_at", "included_items"}
    }
    response = client.put(
        BASE + "/variants/" + host["id"],
        json=dict(expected_revision=host["revision"], payload=legacy_payload),
    )
    assert (
        response.status_code == 200 and response.json()["included_items"] == host["included_items"]
    )
    unchanged = post(client, "/check", dict(configuration=credited["configuration"]))
    assert unchanged["suggestions"][0]["missing"] == "0"
    refreshed = post(
        client, "/check", dict(configuration=credited["configuration"], refresh_knowledge=True)
    )
    assert refreshed["suggestions"][0]["missing"] == "1"
    assert any(
        "修订" in c.get("message", "")
        for c in refreshed["checks"]
        if c["kind"] == "included_allocation"
    )


def test_global_pool_quantity_reduction_and_cross_host_rejected(client, included):
    rule = included["rule"]
    modern_rule(
        client,
        included["host"],
        **{
            k: v
            for k, v in rule.items()
            if k
            not in {
                "id",
                "revision",
                "updated_at",
                "actor",
                "evidence",
                "schema_version",
                "selector",
                "missing_fields",
                "completion",
            }
        },
    )
    refreshed = post(
        client,
        "/check",
        dict(configuration=included["checked"]["configuration"], refresh_knowledge=True),
    )
    data = refreshed["configuration"]
    data["included_allocations"] = [
        dict(allocation(included), id=f"a{i}", demand_id=s["id"])
        for i, s in enumerate(refreshed["suggestions"])
    ]
    result = post(client, "/check", dict(configuration=data))
    assert all(s["included_quantity"] == "0" for s in result["suggestions"])
    assert (
        len(
            [
                c
                for c in result["checks"]
                if c["kind"] == "included_allocation" and c["status"] == "conflict"
            ]
        )
        == 2
    )
    data["included_allocations"] = data["included_allocations"][:1]
    data["devices"][0]["quantity"] = "0.5"
    result = post(client, "/check", dict(configuration=data))
    assert any("超出" in c.get("message", "") for c in result["checks"])
    data["devices"].append(dict(data["devices"][0], id="another", quantity="1"))
    data["included_allocations"][0]["device_id"] = "another"
    result = post(client, "/check", dict(configuration=data))
    assert any("不是本需求的宿主" in c.get("message", "") for c in result["checks"])


def test_save_web_mcp_retry_undo_and_delete(client, included, project):
    saved_response = client.put(
        BASE + "/projects/" + project["id"],
        json=dict(expected_revision=0, configuration=included["checked"]["configuration"]),
    )
    assert saved_response.status_code == 200, saved_response.text
    saved = saved_response.json()
    web = start(client, saved)
    command = dict(action="included_link", value=allocation(included))
    request_id = str(uuid4())
    edited = write(client, web, [command], operation_id=request_id)
    assert edited.status_code == 200, edited.text
    assert write(client, web, [command], operation_id=request_id).json() == edited.json()
    current = client.get("/api/work-drafts/" + web["id"]).json()
    assert current["checked"]["suggestions"][0]["missing"] == "0"
    restored = client.post(
        "/api/work-drafts/" + web["id"] + "/restore",
        json=dict(
            draft_id=web["id"],
            expected_revision=current["revision"],
            checkpoint_revision=web["revision"],
            operation_id=str(uuid4()),
        ),
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["configuration"]["included_allocations"] == []
    agent = call(
        client,
        "list_create",
        dict(
            name="已含内容隔离测试",
            project_id=project["id"],
            revision=1,
            operation_id=str(uuid4()),
            **AUTHOR,
        ),
    )
    updated = call(client, "list_update", mutation(agent, operations=[command]))
    entries = call(client, "list_get", dict(draft_id=agent["id"], view="allocations"))["items"]
    assert [a["allocation_type"] for a in entries] == ["included"]
    issues = call(client, "list_get", dict(draft_id=agent["id"], view="issues"))["items"]
    assert next(i for i in issues if i["kind"] == "accessory")["missing"] == "0"
    call(
        client,
        "list_update",
        mutation(updated, operations=[dict(action="remove", collection="devices", id="device-1")]),
    )
    assert call(client, "list_get", dict(draft_id=agent["id"], view="allocations"))["items"] == []
    saved_credit = client.put(
        BASE + "/projects/" + project["id"],
        json=dict(
            expected_revision=1,
            configuration=checked_with(client, included, [allocation(included)])["configuration"],
        ),
    )
    assert saved_credit.status_code == 200, saved_credit.text
    assert (
        client.get(BASE + "/projects/" + project["id"]).json()["suggestions"][0]["missing"] == "0"
    )


def test_catalog_validation_and_legacy_snapshot_injection(client, catalog, config):
    host, target = catalog["variants"]
    fact = dict(id="x", name="未确认", kind="software", status="confirmed")
    response = client.put(
        BASE + "/variants/" + host["id"],
        json=dict(
            expected_revision=1,
            payload={
                **{k: v for k, v in host.items() if k not in {"id", "revision", "updated_at"}},
                "included_items": [fact],
            },
        ),
    )
    assert response.status_code == 422
    data = post(client, "/check", dict(configuration=config))["configuration"]
    data["devices"][0]["variant_snapshot"]["included_items"] = [fact]
    assert client.post(BASE + "/check", json=dict(configuration=data)).status_code == 422


def test_edit_rejects_over_credit_and_replays_same_id(client, included, project):
    data = included["checked"]["configuration"]
    value = allocation(included)
    url = BASE + "/projects/" + project["id"] + "/edit-preview"

    def edit(configuration, amount):
        return client.post(
            url,
            json=dict(
                configuration=configuration,
                expected_revision=0,
                draft_version=0,
                operations=[dict(action="included_link", value={**value, "quantity": amount})],
            ),
        )

    rejected = edit(data, "2")
    assert rejected.status_code == 422
    assert "超过" in rejected.text
    accepted = edit(data, "1")
    assert accepted.status_code == 200, accepted.text
    repeated = edit(accepted.json()["checked"]["configuration"], "1")
    assert repeated.status_code == 200
    assert len(repeated.json()["checked"]["configuration"]["included_allocations"]) == 1
    assert repeated.json()["checked"]["suggestions"][0]["missing"] == "0"


def test_purchase_surplus_is_preserved_and_unknown_quantity_cannot_be_hidden(
    client, included, catalog
):
    checked = included["checked"]
    bought = post(
        client,
        "/apply",
        dict(
            configuration=checked["configuration"],
            fingerprint=checked["fingerprint"],
            suggestion_id=checked["suggestions"][0]["id"],
            variant_id=included["target"]["id"],
            source_id=catalog["sources"][1]["id"],
        ),
    )
    data = dict(bought["configuration"], included_allocations=[allocation(included)])
    result = post(client, "/check", dict(configuration=data))
    assert result["suggestions"][0]["surplus"] == "1"
    assert len(result["configuration"]["devices"]) == 2
    rule = included["rule"]
    from presales.configuration.knowledge.schemas import KnowledgeInput

    payload = {k: v for k, v in rule.items() if k in KnowledgeInput.model_fields}
    response = client.put(
        BASE + "/knowledge/" + rule["id"],
        json=dict(
            expected_revision=rule["revision"], payload={**payload, "quantity_review": "unreviewed"}
        ),
    )
    assert response.status_code == 200, response.text
    result = post(client, "/check", dict(configuration=data, refresh_knowledge=True))
    assert result["suggestions"][0]["required"] is None
    assert result["suggestions"][0]["included_quantity"] == "0"


def test_missing_target_self_reference_and_duplicate_facts_rejected(client, included):
    host, fact = included["host"], included["fact"]
    payload = {k: v for k, v in host.items() if k not in {"id", "revision", "updated_at"}}
    for facts in (
        [{**fact, "variant_id": "absent"}],
        [{**fact, "variant_id": host["id"]}],
        [fact, {**fact, "id": "duplicate"}],
    ):
        response = client.put(
            BASE + "/variants/" + host["id"],
            json=dict(
                expected_revision=host["revision"], payload={**payload, "included_items": facts}
            ),
        )
        assert response.status_code == 422, response.text
