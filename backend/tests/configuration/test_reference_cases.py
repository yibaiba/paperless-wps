from presales.configuration.reference_cases.comparison import compare_row

from .conftest import AUTHOR, BASE
from .test_workbook_materials import upload, workbook_bytes


def case_payload(client, catalog):
    material = upload(client, workbook_bytes()).json()
    segment = material["segments"][0]
    row = dict(
        id="r1",
        section="一号",
        name="原设备",
        model="同型号",
        quantity="20",
        unit="台",
        evidence_refs=[
            dict(
                material_id=material["id"],
                material_revision=1,
                segment_id=segment["id"],
                locator=segment["location"],
                quote=segment["text"],
            )
        ],
        variant_ids=[catalog["variants"][0]["id"]],
        mapping_evidence="逐项核对原配置",
    )
    return dict(value=dict(**AUTHOR, name="隔离参考案例", rows=[row]), operation_id="case-create")


def test_case_revision_does_not_mutate_sources_or_prior_case(client, catalog):
    payload = case_payload(client, catalog)
    first = client.post(BASE + "/reference-cases", json=payload)
    assert first.status_code == 200, first.text
    old = first.json()
    assert client.post(BASE + "/reference-cases", json=payload).json() == old
    changed = {
        **payload,
        "operation_id": "case-update",
        "case_id": old["id"],
        "expected_revision": 1,
    }
    changed["value"]["rows"][0]["quantity"] = "21"
    updated = client.post(BASE + "/reference-cases", json=changed)
    assert updated.status_code == 200, updated.text
    assert updated.json()["revision"] == 2
    previous = client.get(BASE + f"/reference-cases/{old['id']}/revisions/1").json()
    assert previous["rows"][0]["quantity"] == "20"
    changed["operation_id"] = "stale-request"
    assert client.post(BASE + "/reference-cases", json=changed).status_code == 409
    assert client.get(BASE + f"/reference-cases/{old['id']}/revisions/88").status_code == 422


def context(quantity="20"):
    return dict(
        known_features={"s": {"字幕"}},
        configuration=dict(
            requirements=[], accessory_allocations=[], included_allocations=[], systems=[]
        ),
        checked=dict(checks=[], suggestions=[]),
        devices={"a": {"id": "a", "variant_id": "v"}},
        lines={
            "a": {
                "device_id": "a",
                "quantity": quantity,
                "supply": {"purchase": quantity, "existing": "0"},
            }
        },
    )


def binding(**changes):
    return dict(
        row_id="row",
        device_ids=["a"],
        requirement_ids=[],
        demand_ids=[],
        included_allocation_ids=[],
        disposition="compare",
        feature_system_id="",
        feature="",
        evidence="人工明确对应",
        **changes,
    )


def test_quantity_changes_and_deleted_mapping_remain_visible():
    row = dict(id="row", quantity="20", variant_ids=["v"])
    result = compare_row(row, binding(), context=context("21"))
    assert result["status"] == "matched"
    assert result["quantity_delta"] == "1" and result["purchase"] == "21"
    removed = context()
    removed["devices"] = {}
    removed["lines"] = {}
    result = compare_row(row, binding(), context=removed)
    assert result["status"] == "unknown" and "删除" in result["reason"]


def test_alternative_requires_explicit_configuration_identity_and_unknown_not_pass():
    row = dict(id="row", quantity="20", variant_ids=["old"])
    result = compare_row(row, binding(), context=context())
    assert result["status"] == "alternative"
    row["variant_ids"] = []
    assert compare_row(row, binding(), context=context())["status"] == "unknown"
    ctx = context()
    ctx["checked"]["checks"] = [dict(status="conflict", device_id="a")]
    assert compare_row(row, binding(), context=ctx)["status"] == "conflict"


def test_existing_counts_and_explicit_disabled_feature():
    row = dict(id="row", quantity="20", variant_ids=["v"])
    ctx = context()
    ctx["lines"]["a"]["supply"] = {"purchase": "0", "existing": "20"}
    result = compare_row(row, binding(), context=ctx)
    assert result["status"] == "satisfied" and result["purchase"] == "0"
    b = binding()
    b.update(device_ids=[], disposition="not_enabled", feature_system_id="s", feature="字幕")
    ctx["configuration"]["systems"] = [dict(id="s", features=[])]
    ctx["configuration"]["generation"] = dict(features_confirmed=["s"])
    assert compare_row(row, b, context=ctx)["status"] == "not_enabled"
    ctx["configuration"]["systems"][0]["features"] = ["字幕"]
    assert compare_row(row, b, context=ctx)["status"] == "conflict"


def test_http_mcp_case_binding_save_reopen_delete_and_replay(client, catalog):
    from .test_list_mcp import call, create, device_operations, mutation

    payload = case_payload(client, catalog)
    case = client.post(BASE + "/reference-cases", json=payload).json()
    draft = create(client)
    link = dict(
        action="reference_case_set",
        value=dict(
            id=case["id"],
            revision=1,
            bindings=[dict(row_id="r1", device_ids=["server"], evidence="明确映射")],
        ),
    )
    request = mutation(draft, operations=[*device_operations(catalog), link])
    edited = call(client, "list_update", request)
    assert call(client, "list_update", request) == edited
    compared = call(client, "list_get", dict(draft_id=draft["id"], view="case_comparison", limit=1))
    assert compared["total"] == 1 and compared["items"][0]["device_ids"] == ["server"]
    checked = call(client, "list_check", mutation(edited))
    saved = call(
        client,
        "list_save",
        mutation(checked, expected_project_revision=0, fingerprint=checked["check_fingerprint"]),
    )
    reopened = call(
        client, "list_get", dict(project_id=saved["project_id"], revision=1, view="case_comparison")
    )
    assert reopened["items"] == compared["items"]
    configuration = client.get(BASE + "/projects/" + saved["project_id"]).json()["configuration"]
    browser = client.post(BASE + "/reference-cases/compare", json=configuration)
    assert browser.status_code == 200, browser.text
    assert browser.json()["rows"] == compared["items"]
    current = call(client, "list_get", dict(draft_id=draft["id"]))
    deleted = call(
        client,
        "list_update",
        mutation(current, operations=[dict(action="remove", collection="devices", id="server")]),
    )
    result = call(client, "list_get", dict(draft_id=deleted["id"], view="case_comparison"))
    assert result["items"][0]["status"] == "unknown"
    assert "删除" in result["items"][0]["reason"]


def test_included_content_cannot_count_when_allocation_failed():
    ctx = context()
    ctx["configuration"]["included_allocations"] = [dict(id="i", quantity="1", demand_id="need")]
    ctx["checked"]["suggestions"] = [dict(id="need", status="pass")]
    ctx["checked"]["checks"] = [
        dict(kind="included_allocation", allocation_id="i", status="conflict", counted_quantity="0")
    ]
    b = binding()
    b.update(device_ids=[], included_allocation_ids=["i"])
    result = compare_row(dict(id="row", quantity="1", variant_ids=["v"]), b, context=ctx)
    assert result["included"] == "0" and result["status"] == "conflict"


def test_web_draft_case_map_undo_restore_keeps_original_project(client, catalog):
    from .test_list_mcp import saved_project
    from .test_web_drafts import start, write

    case = client.post(BASE + "/reference-cases", json=case_payload(client, catalog)).json()
    saved = saved_project(client, catalog)
    draft = start(client, saved)
    reference = dict(
        id=case["id"],
        revision=1,
        bindings=[dict(row_id="r1", device_ids=["server"], evidence="对照配置")],
    )
    changed = write(client, draft, [dict(action="reference_case_set", value=reference)])
    assert changed.status_code == 200, changed.text
    current = client.get("/api/work-drafts/" + draft["id"]).json()
    assert current["configuration"]["reference_case"]["id"] == case["id"]
    old = client.get(BASE + "/projects/" + saved["project_id"]).json()
    assert old["configuration"]["reference_case"] is None
    restored = client.post(
        "/api/work-drafts/" + draft["id"] + "/restore",
        json=dict(
            draft_id=draft["id"],
            expected_revision=current["revision"],
            checkpoint_revision=draft["revision"],
            operation_id="case-undo",
        ),
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["configuration"]["reference_case"] is None


def test_disabled_feature_requires_current_confirmation():
    row = dict(id="row", quantity="1", variant_ids=[])
    ctx = context()
    ctx["configuration"]["systems"] = [dict(id="s", features=[])]
    b = binding()
    b.update(device_ids=[], disposition="not_enabled", feature_system_id="s", feature="字幕")
    assert compare_row(row, b, context=ctx)["status"] == "unknown"


def test_raw_case_cells_preserve_whitespace():
    from presales.configuration.reference_cases.schemas import CaseRow

    row = CaseRow(
        id="1",
        section="原表",
        name="设备",
        raw={"D1": "  原文\n "},
        evidence_refs=[dict(source_id="source", locator="D1", quote="原文")],
    )
    assert row.raw["D1"] == "  原文\n "


def test_served_rooms_are_explicit_and_cleanup_does_not_infer_quantities(client, catalog):
    from .test_proposal_generation import read, write
    from .test_proposal_prices_and_cycles import priced

    draft = priced(client, catalog, amount="10")
    before = read(client, draft)["configuration"]
    system = dict(before["systems"][0], served_room_ids=["room", "second"])
    draft = write(
        client,
        draft,
        [
            dict(action="room_put", value=dict(id="second", name="二号")),
            dict(action="system_put", value=system),
        ],
    )
    applied = read(client, draft)["configuration"]
    assert applied["systems"][0]["served_room_ids"] == ["room", "second"]
    assert applied["devices"] == before["devices"]
    draft = write(client, draft, [dict(action="remove", collection="rooms", id="second")])
    assert read(client, draft)["configuration"]["systems"][0]["served_room_ids"] == ["room"]


def test_partial_role_allocation_compares_assigned_use_separately_from_deployment():
    ctx = context("20")
    ctx["configuration"]["requirements"] = [
        dict(id="role", allocations=[dict(device_id="a", quantity="5")])
    ]
    b = binding()
    b.update(device_ids=[], requirement_ids=["role"])
    result = compare_row(dict(id="row", quantity="5", variant_ids=["v"]), b, context=ctx)
    assert result["status"] == "matched" and result["quantity_delta"] == "0"
    assert result["mapped_quantity"] == "5" and result["deployed"] == "20"


def test_same_device_from_multiple_demands_is_one_physical_server():
    ctx = context("1")
    ctx["lines"]["a"]["kind"] = "hardware"
    ctx["configuration"]["accessory_allocations"] = [
        dict(id=i, demand_id=i, device_id="a", quantity="1") for i in ("one", "two")
    ]
    b = binding()
    b.update(device_ids=[], demand_ids=["one", "two"])
    result = compare_row(dict(id="row", quantity="1", variant_ids=["v"]), b, context=ctx)
    assert result["mapped_quantity"] == result["deployed"] == result["purchase"] == "1"


def test_duplicate_included_references_reject_at_boundary():
    import pytest
    from pydantic import ValidationError

    from presales.configuration.reference_cases.schemas import RowBinding

    b = binding()
    b["included_allocation_ids"] = ["credit", "credit"]
    with pytest.raises(ValidationError, match="重复引用"):
        RowBinding.model_validate(b)


def test_partial_included_credit_does_not_label_purchase_as_fully_satisfied():
    ctx = context("19")
    ctx["configuration"]["included_allocations"] = [dict(id="credit", demand_id="need")]
    ctx["checked"]["checks"] = [
        dict(
            kind="included_allocation", allocation_id="credit", status="pass", counted_quantity="1"
        )
    ]
    b = binding()
    b["included_allocation_ids"] = ["credit"]
    result = compare_row(dict(id="row", quantity="20", variant_ids=["v"]), b, context=ctx)
    assert result["mapped_quantity"] == "20" and result["purchase"] == "19"
    assert result["status"] == "matched"
    b["device_ids"] = []
    assert (
        compare_row(dict(id="row", quantity="1", variant_ids=["v"]), b, context=ctx)["status"]
        == "satisfied"
    )
