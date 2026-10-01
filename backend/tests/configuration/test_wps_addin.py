from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import uuid4

from sqlalchemy import select

from presales.wps.auth import WpsAuth
from presales.wps.feedback import CompletionFeedback
from presales.wps.models import WpsAccessToken, WpsDiagnosticEvent, WpsSuggestionFeedback
from presales.wps.schemas import SuggestionRequest


def paired(client, actor="测试售前"):
    with client.app.state.session_factory() as session:
        code = WpsAuth(session).issue_pairing(actor)
        session.commit()
    response = client.post("/api/wps/pairings/exchange", json={"code": code})
    assert response.status_code == 200, response.text
    return response.json(), code


def authorized(token):
    return {"Authorization": "Bearer " + token["access_token"]}


def update_variant_context(client, variant, *, series, systems, product_id=None, name=None):
    fields = {
        "description": "",
        "supply_status": "available",
        "replacements": [],
        "review_requirements": [],
        "included_items": [],
        "capability_ids": [],
        "attributes": [],
        "functions": [],
        "interfaces": [],
    }
    payload = {key: variant.get(key, default) for key, default in fields.items()}
    payload.update(
        product_id=product_id or variant["product_id"],
        name=name or variant["name"],
        status=variant["status"],
        series=series,
        systems=systems,
        actor="测试维护者",
        evidence="隔离测试资料，不是业务确认",
    )
    response = client.put(
        f"/api/configuration/variants/{variant['id']}",
        json={"expected_revision": variant["revision"], "payload": payload},
    )
    assert response.status_code == 200, response.text
    return response.json()


def template(client, headers, catalog=None):
    catalog_scope = (
        {"import_id": catalog["imported"]["id"], "sheet": "产品表"} if catalog else None
    )
    response = client.post(
        "/api/wps/template-profiles",
        headers=headers,
        json={
            "name": "现场报价模板",
            "sheet_selector": "报价表",
            "header_row": 2,
            "field_columns": {"model": 2, "name": 3, "quantity": 5, "unit": 6},
            "managed_fields": ["model", "name", "unit"],
            "header_values": ["序号", "产品型号", "产品名称", "说明", "数量", "单位"],
            **({"catalog_scope": catalog_scope} if catalog_scope else {}),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def binding(client, headers, profile):
    response = client.post(
        "/api/wps/bindings",
        headers=headers,
        json={
            "workbook_instance_id": str(uuid4()),
            "name": "WPS 现场项目",
            "template_profile_id": profile["id"],
            "template_profile_revision": profile["revision"],
            "operation_id": str(uuid4()),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def sync_body(bound, profile, catalog):
    return {
        "binding_id": bound["binding_id"],
        "expected_draft_revision": bound["draft_revision"],
        "expected_project_revision": bound["base_revision"],
        "template_profile_revision": profile["revision"],
        "known_device_ids": bound["managed_device_ids"],
        "lines": [
            {
                "line_id": "报价表:3",
                "sheet": "报价表",
                "row": 3,
                "model": "SERVER-X",
                "name": "测试服务器",
                "description": "64GB",
                "quantity": "2",
                "unit": "台",
                "price": "1200",
                "note": "WPS 测试",
                "section": "无纸化会议系统",
                "kind": "hardware",
                "variant_id": catalog["variants"][0]["id"],
                "source_id": catalog["sources"][0]["id"],
            }
        ],
    }


def test_pairing_is_single_use_and_token_is_required(client):
    token, code = paired(client)
    assert token["actor"] == "测试售前"
    assert client.post("/api/wps/pairings/exchange", json={"code": code}).status_code == 422
    assert client.get("/api/wps/template-profiles").status_code == 401
    assert client.get("/api/wps/template-profiles", headers=authorized(token)).status_code == 200
    with client.app.state.session_factory() as session:
        access = session.scalar(select(WpsAccessToken).where(WpsAccessToken.actor == "测试售前"))
        WpsAuth(session).revoke(access.id)
        session.commit()
    assert client.get("/api/wps/template-profiles", headers=authorized(token)).status_code == 401


def diagnostic_event(**extra):
    return {
        "event_id": str(uuid4()),
        "installation_id": "anonymous-installation",
        "session_id": "anonymous-session",
        "occurred_at": datetime.now(UTC).isoformat(),
        "plugin_version": "0.1.0",
        "host_os": "macOS",
        "host_version": "12.1.28496",
        "event_type": "query_success",
        "completion_phase": "ghost",
        "duration_ms": 120,
        "candidate_count": 3,
        "completion_ready": True,
        "outcome": "success",
        **extra,
    }


def test_diagnostics_are_idempotent_private_and_expire(client):
    token, _ = paired(client)
    headers = authorized(token)
    event = diagnostic_event()
    first = client.post("/api/wps/diagnostics/batch", headers=headers, json={"events": [event]})
    repeated = client.post(
        "/api/wps/diagnostics/batch", headers=headers, json={"events": [event]}
    )
    assert first.status_code == 200, first.text
    assert first.json()["accepted"] == 1
    assert repeated.json()["duplicates"] == 1

    rejected = client.post(
        "/api/wps/diagnostics/batch",
        headers=headers,
        json={"events": [{**diagnostic_event(), "query": "客户原始输入"}]},
    )
    assert rejected.status_code == 422

    with client.app.state.session_factory() as session:
        saved = session.scalar(
            select(WpsDiagnosticEvent).where(WpsDiagnosticEvent.event_id == event["event_id"])
        )
        assert saved is not None
        assert not hasattr(saved, "actor")
        session.add(
            WpsDiagnosticEvent(
                **{
                    **diagnostic_event(event_id=str(uuid4())),
                    "occurred_at": datetime.now(UTC),
                    "received_at": datetime.now(UTC) - timedelta(days=31),
                }
            )
        )
        session.commit()

    cleanup = client.post(
        "/api/wps/diagnostics/batch",
        headers=headers,
        json={"events": [diagnostic_event()]},
    )
    assert cleanup.status_code == 200, cleanup.text
    assert cleanup.json()["purged"] == 1


def test_template_revision_and_suggestions(client, catalog):
    token, _ = paired(client)
    headers = authorized(token)
    created = template(client, headers)
    change = {
        "profile_id": created["id"],
        "expected_revision": created["revision"],
        "name": "现场报价模板二版",
        "sheet_selector": "报价表",
        "header_row": 3,
        "field_columns": {"model": 2, "name": 3, "quantity": 5, "unit": 6},
        "managed_fields": ["model", "name", "unit"],
        "header_values": ["序号", "型号", "名称", "说明", "数量", "单位"],
    }
    updated = client.post("/api/wps/template-profiles", headers=headers, json=change)
    assert updated.status_code == 200, updated.text
    assert updated.json()["revision"] == 2
    assert (
        updated.json()["normalized_header_fingerprint"] != created["normalized_header_fingerprint"]
    )
    historical = client.get(
        f"/api/wps/template-profiles/{created['id']}?revision=1", headers=headers
    )
    assert historical.status_code == 200
    assert historical.json()["name"] == "现场报价模板"

    response = client.post(
        "/api/wps/suggestions",
        headers=headers,
        json={"query": "SERVER-X", "limit": 10},
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 2
    assert {item["source_id"] for item in items} == {source["id"] for source in catalog["sources"]}
    assert all(item["group"] == "direct" for item in items)
    assert all(item["confidence"] == "high" for item in items)


def test_template_source_scope_preview_and_revision(client, catalog):
    token, _ = paired(client)
    headers = authorized(token)
    preview = client.post(
        "/api/wps/template-profiles/source-scope-preview",
        headers=headers,
        json={"rows": [{"model": "SERVER-X", "name": "测试服务器"}]},
    )
    assert preview.status_code == 200, preview.text
    scope = preview.json()["items"][0]
    assert scope["import_id"] == catalog["imported"]["id"]
    assert scope["sheet"] == "产品表"
    assert scope["matched_rows"] == 1
    assert scope["ambiguous_rows"] == 1

    created = template(client, headers, catalog)
    assert created["schema_version"] == 2
    assert created["catalog_scope"] == {
        "import_id": catalog["imported"]["id"],
        "sheet": "产品表",
    }


def test_suggestion_index_invalidates_on_catalog_revision(client, catalog):
    token, _ = paired(client)
    headers = authorized(token)
    profile = template(client, headers, catalog)
    request = {
        "query": "SERVER-X",
        "template_profile_id": profile["id"],
        "template_profile_revision": profile["revision"],
    }
    initial = client.post("/api/wps/suggestions", headers=headers, json=request)
    assert initial.status_code == 200, initial.text
    initial_item = next(
        item
        for item in initial.json()["items"]
        if item["variant_id"] == catalog["variants"][0]["id"]
    )
    assert initial_item["variant_name"] == "64GB"

    update_variant_context(
        client,
        catalog["variants"][0],
        series=[],
        systems=[],
        name="64GB 已更新",
    )
    refreshed = client.post("/api/wps/suggestions", headers=headers, json=request)
    assert refreshed.status_code == 200, refreshed.text
    refreshed_item = next(
        item
        for item in refreshed.json()["items"]
        if item["variant_id"] == catalog["variants"][0]["id"]
    )
    assert refreshed_item["variant_name"] == "64GB 已更新"


def test_warm_suggestion_latency_stays_below_pilot_threshold(client, catalog):
    token, _ = paired(client)
    headers = authorized(token)
    profile = template(client, headers, catalog)
    request = {
        "query": "SERVER-X",
        "template_profile_id": profile["id"],
        "template_profile_revision": profile["revision"],
    }
    warmup = client.post("/api/wps/suggestions", headers=headers, json=request)
    assert warmup.status_code == 200, warmup.text

    durations = []
    for _ in range(25):
        started = perf_counter()
        response = client.post("/api/wps/suggestions", headers=headers, json=request)
        durations.append((perf_counter() - started) * 1000)
        assert response.status_code == 200, response.text
    p95 = sorted(durations)[int(len(durations) * 0.95) - 1]
    assert p95 <= 500


def test_suggestions_use_previous_product_series_and_current_system(client, catalog):
    product = client.post(
        "/api/configuration/products",
        json={
            "name": "测试备选服务器",
            "model": "SERVER-Y",
            "category": "服务器",
            "actor": "测试维护者",
            "evidence": "隔离测试资料，不是业务确认",
        },
    )
    assert product.status_code == 200, product.text
    first = update_variant_context(
        client, catalog["variants"][0], series=["服务器系列"], systems=["系统甲"]
    )
    second = update_variant_context(
        client,
        catalog["variants"][1],
        series=["服务器系列"],
        systems=["系统乙"],
        product_id=product.json()["id"],
    )
    token, _ = paired(client)
    headers = authorized(token)
    context = {
        "system": "系统乙",
        "selected_variant_id": first["id"],
        "previous_variant_ids": [first["id"]],
    }

    direct = client.post(
        "/api/wps/suggestions",
        headers=headers,
        json={"query": "SERVER", "context": context, "limit": 10},
    )
    assert direct.status_code == 200, direct.text
    assert direct.json()["items"][0]["variant_id"] == second["id"]
    assert direct.json()["items"][0]["context_reasons"] == [
        "延续清单顺序 SERVER-X → SERVER-Y",
        "匹配当前系统",
        "延续同系列 服务器系列",
    ]

    proactive = client.post(
        "/api/wps/suggestions",
        headers=headers,
        json={"query": "", "context": context, "limit": 10},
    )
    assert proactive.status_code == 200, proactive.text
    assert proactive.json()["items"][0]["variant_id"] == second["id"]
    assert proactive.json()["items"][0]["group"] == "series"
    assert proactive.json()["items"][0]["confidence"] == "high"

    bridge = client.post(
        "/api/wps/suggestions",
        headers=headers,
        json={
            "query": "",
            "context": {"next_variant_ids": [second["id"]]},
            "limit": 10,
        },
    )
    assert bridge.status_code == 200, bridge.text
    assert bridge.json()["items"][0]["variant_id"] == first["id"]
    assert bridge.json()["items"][0]["confidence"] == "high"
    assert "衔接清单顺序" in bridge.json()["items"][0]["context_reasons"][0]

    completed_context = {
        **context,
        "selected_variant_id": second["id"],
        "previous_variant_ids": [second["id"], first["id"]],
    }
    completed = client.post(
        "/api/wps/suggestions",
        headers=headers,
        json={"query": "", "context": completed_context, "limit": 10},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["items"] == []


def test_confirmed_software_pair_recommends_its_hardware_in_reverse(client, catalog):
    software_product = client.post(
        "/api/configuration/products",
        json={
            "name": "红盾 Windows 客户端软件",
            "model": "RS-MSC100C-W",
            "category": "Windows 客户端",
            "actor": "测试维护者",
            "evidence": "隔离测试资料，不是业务确认",
        },
    )
    assert software_product.status_code == 200, software_product.text
    hardware = update_variant_context(
        client, catalog["variants"][0], series=[], systems=["红盾无纸化会议系统"]
    )
    software = update_variant_context(
        client,
        catalog["variants"][1],
        series=[],
        systems=["红盾无纸化会议系统"],
        product_id=software_product.json()["id"],
    )
    relation = client.post(
        "/api/configuration/knowledge",
        json={
            "name": "红盾 Windows 终端每台配客户端软件",
            "kind": "accessory",
            "status": "confirmed",
            "selector": {"variant_ids": [hardware["id"]]},
            "need_key": "redshield.windows.client-software",
            "need_name": "红盾 Windows 客户端软件",
            "target_variant_ids": [software["id"]],
            "accessory_type": "required",
            "calculation_scope": "device",
            "quantity_source": "device_quantity",
            "mode": "per_unit",
            "factor": "1",
            "output_kind": "software",
            "allocation_mode": "consumable",
            "actor": "测试维护者",
            "evidence": "隔离测试资料，不是业务确认",
        },
    )
    assert relation.status_code == 200, relation.text
    token, _ = paired(client)
    headers = authorized(token)
    profile = template(client, headers, catalog)

    response = client.post(
        "/api/wps/suggestions",
        headers=headers,
        json={
            "query": "",
            "template_profile_id": profile["id"],
            "template_profile_revision": profile["revision"],
            "context": {
                "sheet": "报价表",
                "system": "红盾无纸化会议系统",
                "previous_variant_ids": [software["id"]],
            },
            "limit": 10,
        },
    )

    assert response.status_code == 200, response.text
    top = response.json()["items"][0]
    assert top["variant_id"] == hardware["id"]
    assert top["group"] == "accessory"
    assert top["context_reasons"][0] == "补齐已选产品的对应主设备"
    assert top["completion_ready"] is True


def test_compact_product_name_keywords_recall_catalog_candidates(client, catalog):
    product = client.post(
        "/api/configuration/products",
        json={
            "name": "无纸化会议系统客户端软件",
            "model": "RS-MSC100C-W",
            "category": "客户端软件",
            "actor": "测试维护者",
            "evidence": "隔离测试资料，不是业务确认",
        },
    )
    assert product.status_code == 200, product.text
    software = update_variant_context(
        client,
        catalog["variants"][0],
        series=["无纸化终端"],
        systems=["红盾无纸化会议系统"],
        product_id=product.json()["id"],
        name="Windows 客户端",
    )
    token, _ = paired(client)

    response = client.post(
        "/api/wps/suggestions",
        headers=authorized(token),
        json={"query": "红盾软件", "limit": 10},
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items
    assert items[0]["variant_id"] == software["id"]
    assert items[0]["group"] == "direct"
    assert items[0]["completion_ready"] is False


def test_confirmed_line_source_scopes_contextual_completion_for_v1_template(client, catalog):
    second_product = client.post(
        "/api/configuration/products",
        json={
            "name": "来源范围内的下一产品",
            "model": "SERVER-Y",
            "category": "服务器",
            "actor": "测试维护者",
            "evidence": "隔离测试资料，不是业务确认",
        },
    )
    assert second_product.status_code == 200, second_product.text
    first = update_variant_context(
        client, catalog["variants"][0], series=["服务器系列"], systems=[]
    )
    second = update_variant_context(
        client,
        catalog["variants"][1],
        series=["服务器系列"],
        systems=[],
        product_id=second_product.json()["id"],
    )
    token, _ = paired(client)
    headers = authorized(token)
    profile = template(client, headers)

    response = client.post(
        "/api/wps/suggestions",
        headers=headers,
        json={
            "query": "",
            "template_profile_id": profile["id"],
            "template_profile_revision": profile["revision"],
            "context": {
                "previous_variant_ids": [first["id"]],
                "previous_source_ids": [catalog["sources"][0]["id"]],
            },
            "limit": 10,
        },
    )

    assert response.status_code == 200, response.text
    top = response.json()["items"][0]
    assert top["variant_id"] == second["id"]
    assert top["completion_blocker"] is None
    assert top["completion_ready"] is True


def test_accepted_suggestion_feedback_is_idempotent_and_affects_ranking(client, catalog):
    product = client.post(
        "/api/configuration/products",
        json={
            "name": "反馈学习产品",
            "model": "LEARN-Y",
            "category": "服务器",
            "actor": "测试维护者",
            "evidence": "隔离测试资料，不是业务确认",
        },
    )
    assert product.status_code == 200, product.text
    previous = update_variant_context(
        client, catalog["variants"][0], series=["反馈系列"], systems=[]
    )
    chosen = update_variant_context(
        client,
        catalog["variants"][1],
        series=["反馈系列"],
        systems=[],
        product_id=product.json()["id"],
    )
    token, _ = paired(client, actor="反馈测试售前")
    headers = authorized(token)
    profile = template(client, headers)
    operation_id = str(uuid4())
    payload = {
        "operation_id": operation_id,
        "workbook_instance_id": "feedback-workbook",
        "template_profile_id": profile["id"],
        "template_profile_revision": profile["revision"],
        "sheet": "报价表",
        "section": "反馈系统",
        "previous_variant_id": previous["id"],
        "context_previous_variant_ids": [previous["id"]],
        "context_next_variant_ids": [],
        "suggested_variant_id": previous["id"],
        "chosen_variant_id": chosen["id"],
        "chosen_source_id": catalog["sources"][1]["id"],
        "query_kind": "contextual",
    }

    first = client.post("/api/wps/suggestion-feedback", headers=headers, json=payload)
    repeated = client.post("/api/wps/suggestion-feedback", headers=headers, json=payload)
    assert first.status_code == 200, first.text
    assert repeated.status_code == 200, repeated.text
    assert first.json()["id"] == repeated.json()["id"]
    with client.app.state.session_factory() as session:
        records = session.scalars(
            select(WpsSuggestionFeedback).where(WpsSuggestionFeedback.operation_id == operation_id)
        ).all()
        assert len(records) == 1

    suggestion_request = {
        "query": "",
        "workbook_instance_id": "feedback-workbook",
        "template_profile_id": profile["id"],
        "template_profile_revision": profile["revision"],
        "context": {
            "sheet": "报价表",
            "section": "反馈系统",
            "previous_variant_ids": [previous["id"]],
        },
        "limit": 10,
    }
    suggestions = client.post(
        "/api/wps/suggestions",
        headers=headers,
        json=suggestion_request,
    )
    assert suggestions.status_code == 200, suggestions.text
    assert suggestions.json()["items"][0]["variant_id"] == chosen["id"]
    assert suggestions.json()["items"][0]["context_reasons"][0] == "采用当前工作簿上下文顺序"

    request_data = {
        **suggestion_request,
        "workbook_instance_id": "another-workbook",
        "template_profile_id": None,
        "template_profile_revision": None,
    }
    new_revision = client.post("/api/wps/suggestions", headers=headers, json=request_data)
    assert new_revision.status_code == 200, new_revision.text
    assert new_revision.json()["items"][0]["context_reasons"][0] == "采用个人历史顺序"

    another_token, _ = paired(client, actor="另一个反馈测试售前")
    collision = client.post(
        "/api/wps/suggestion-feedback", headers=authorized(another_token), json=payload
    )
    assert collision.status_code == 422
    assert "反馈操作编号已被其他账号使用" in collision.text


def test_typed_choice_does_not_train_blank_row_completion(client, catalog):
    actor = "搜索反馈测试售前"
    token, _ = paired(client, actor=actor)
    headers = authorized(token)
    profile = template(client, headers)
    previous = catalog["variants"][0]
    chosen = catalog["variants"][1]
    payload = {
        "operation_id": str(uuid4()),
        "workbook_instance_id": "typed-feedback-workbook",
        "template_profile_id": profile["id"],
        "template_profile_revision": profile["revision"],
        "sheet": "报价表",
        "section": "会议系统",
        "previous_variant_id": previous["id"],
        "context_previous_variant_ids": [previous["id"]],
        "context_next_variant_ids": [],
        "suggested_variant_id": previous["id"],
        "chosen_variant_id": chosen["id"],
        "chosen_source_id": catalog["sources"][1]["id"],
        "query_kind": "typed",
    }

    recorded = client.post("/api/wps/suggestion-feedback", headers=headers, json=payload)
    assert recorded.status_code == 200, recorded.text
    contextual_request = SuggestionRequest(
        query="",
        workbook_instance_id=payload["workbook_instance_id"],
        template_profile_id=profile["id"],
        template_profile_revision=profile["revision"],
        context={
            "sheet": payload["sheet"],
            "section": payload["section"],
            "previous_variant_ids": [previous["id"]],
        },
    )
    typed_request = contextual_request.model_copy(update={"query": "服务器"})

    with client.app.state.session_factory() as session:
        feedback = CompletionFeedback(session)
        assert feedback.scores(contextual_request, actor) == {}
        assert feedback.scores(typed_request, actor) == {}


def test_preview_commit_retry_and_stale_conflict(client, catalog):
    token, _ = paired(client)
    headers = authorized(token)
    profile = template(client, headers)
    bound = binding(client, headers, profile)
    request = sync_body(bound, profile, catalog)

    preview = client.post("/api/wps/sync/preview", headers=headers, json=request)
    assert preview.status_code == 200, preview.text
    preview_data = preview.json()
    assert preview_data["has_changes"] is True
    assert preview_data["line_bindings"][0]["device_id"]
    assert preview_data["line_bindings"][0]["section"] == "无纸化会议系统"
    assert bound["project_id"] is None

    commit_request = {
        **request,
        "preview_fingerprint": preview_data["preview_fingerprint"],
        "operation_id": str(uuid4()),
    }
    first = client.post("/api/wps/sync/commit", headers=headers, json=commit_request)
    assert first.status_code == 200, first.text
    saved = first.json()
    assert saved["status"] == "saved" and saved["project_revision"] == 1
    assert saved["managed_device_ids"] == [saved["line_bindings"][0]["device_id"]]
    retry = client.post("/api/wps/sync/commit", headers=headers, json=commit_request)
    assert retry.status_code == 200 and retry.json() == saved

    project = client.get("/api/configuration/projects/" + saved["project_id"]).json()
    device = project["configuration"]["devices"][0]
    assert device["quantity"] == "2" and device["note"] == "WPS 测试"
    assert project["configuration"]["quotation"]["prices"][0]["unit_price"] == "1200"

    stale = client.post("/api/wps/sync/preview", headers=headers, json=request)
    assert stale.status_code == 409
    assert "VERSION_CONFLICT" in stale.text

    current_line = {
        **commit_request["lines"][0],
        "device_id": saved["line_bindings"][0]["device_id"],
    }
    current_request = {
        **request,
        "expected_draft_revision": saved["draft_revision"],
        "expected_project_revision": saved["project_revision"],
        "known_device_ids": saved["managed_device_ids"],
        "lines": [current_line],
    }
    unchanged = client.post("/api/wps/sync/preview", headers=headers, json=current_request)
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["has_changes"] is False

    delete_request = {**current_request, "lines": []}
    delete_preview = client.post("/api/wps/sync/preview", headers=headers, json=delete_request)
    assert delete_preview.status_code == 200, delete_preview.text
    deleted = client.post(
        "/api/wps/sync/commit",
        headers=headers,
        json={
            **delete_request,
            "preview_fingerprint": delete_preview.json()["preview_fingerprint"],
            "operation_id": str(uuid4()),
        },
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["project_revision"] == 2
    project = client.get("/api/configuration/projects/" + saved["project_id"]).json()
    assert project["configuration"]["devices"] == []
