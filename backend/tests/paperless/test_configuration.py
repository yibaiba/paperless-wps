from .conftest import DISTRIBUTED


def test_candidate_modules_require_selection_and_count_existing_roles(paperless):
    lift = paperless.product("IPH-S156AM", sheet=DISTRIBUTED)
    chair = paperless.product("PCS-310C", sheet=DISTRIBUTED)
    delegate = paperless.product("PCS-310D", sheet=DISTRIBUTED)
    paperless.rule(
        lift,
        chair,
        relation="choice",
        alternative_target_ids=[delegate["id"]],
        evidence="试验假设：每席一模块；主席/代表分配由人选择，本测试不确认席位角色。",
    )
    paperless.add(lift, quantity="20")
    preview = paperless.preview()
    assert preview["suggestions"] == []
    check = preview["choice_checks"][0]
    assert check["missing"] == "20" and check["status"] == "needs_selection"
    forged = paperless.client.post(
        paperless.path + "/rule-apply",
        json={
            "fingerprint": preview["fingerprint"],
            "suggestion_ids": [check["id"]],
        },
    )
    assert forged.status_code == 422
    paperless.add(chair, quantity="1")
    paperless.add(delegate, quantity="18")
    assert paperless.preview()["choice_checks"][0]["missing"] == "1"
    paperless.add(delegate, quantity="1", group="其他系统")
    assert paperless.preview()["choice_checks"][0]["missing"] == "1"
    paperless.add(delegate, quantity="1")
    assert paperless.preview()["choice_checks"][0]["status"] == "quantity_satisfied"


def test_shared_required_host_is_not_added_for_each_lift_model(paperless):
    host = paperless.product("ACS-320M", sheet=DISTRIBUTED)
    for model in ("IPH-S156AM", "IPH-S173BM"):
        lift = paperless.product(model, sheet=DISTRIBUTED)
        paperless.rule(lift, host, relation="required", mode="per_group", factor="1")
        paperless.add(lift, quantity="20")
    suggestion = paperless.preview()["suggestions"][0]
    assert suggestion["required"] == "1"
    assert len(suggestion["rules"]) == 2


def test_source_set_revision_invalidates_preview_and_retains_history(paperless):
    a = paperless.product("PCS-6580T", sheet=DISTRIBUTED)
    b = paperless.product("PCS-6780T", sheet=DISTRIBUTED)
    rule = paperless.rule(
        a,
        paperless.product("PCS-1516N", sheet=DISTRIBUTED),
        mode="per_capacity",
        factor="50",
        additional_source_ids=[b["id"]],
    )
    paperless.add(a, quantity="20")
    paperless.add(b, quantity="40")
    preview = paperless.preview()
    keys = (
        "name",
        "source_product_id",
        "target_product_id",
        "mode",
        "factor",
        "status",
        "evidence",
        "actor",
        "relation",
        "alternative_target_ids",
    )
    update = {key: rule[key] for key in keys}
    paperless.request(
        "put",
        f"/api/rules/{rule['id']}",
        json={
            **update,
            "additional_source_ids": [],
            "expected_revision": 1,
        },
    )
    assert paperless.apply(preview).status_code == 409
    assert paperless.preview()["suggestions"][0]["required"] == "1"
    history = paperless.request("get", f"/api/rules/{rule['id']}/history")
    assert [len(r["sources"]) for r in history] == [1, 2]


def test_draft_relation_is_visible_but_not_calculated(paperless):
    lift = paperless.product("IPH-S156AM")
    rule = paperless.rule(
        lift, paperless.product("ACS-320M"), mode="per_group", relation="required", status="draft"
    )
    paperless.add(lift, quantity="20")
    preview = paperless.preview()
    assert preview["suggestions"] == []
    assert [r["id"] for r in preview["pending_relations"]] == [rule["id"]]


def test_note_conflict_has_sources_and_remains_unconfirmed_in_project(paperless):
    host = paperless.product("PCS-1516N", sheet=DISTRIBUTED)
    detail = paperless.detail(host)
    issue = next(i for i in detail["issues"] if i["kind"] == "note_difference")
    assert any(e["range"] == "J104" and "5台" in e["value"] for e in issue["evidence"])
    assert any("50台" in e["value"] for e in issue["evidence"])
    paperless.add(host)
    assert issue["id"] in {i["id"] for i in paperless.preview()["source_concerns"]}
    paperless.request(
        "post",
        f"/api/issues/{issue['id']}/reviews",
        json={
            "status": "confirmed_variant",
            "actor": "隔离测试",
            "note": "仅测试状态同步，不确认业务容量",
            "expected_revision": 0,
        },
    )
    assert issue["id"] not in {i["id"] for i in paperless.preview()["source_concerns"]}
    before = paperless.detail(host)
    result = paperless.request("post", f"/api/imports/{host['import_id']}/recheck")
    assert result["added"] == 0
    assert before == paperless.detail(host)
