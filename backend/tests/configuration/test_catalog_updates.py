from io import BytesIO
from uuid import uuid4

from openpyxl import Workbook

from .conftest import AUTHOR, knowledge, post

ROOT = "/api/catalog-updates"
COLUMN = "出厂指导价"


def call(client, path, data, *, method="post", status=200):
    response = getattr(client, method)(ROOT + path, json=data)
    assert response.status_code == status, response.text
    return response.json()


def batch_for(client, variant):
    return call(
        client,
        "",
        dict(name="隔离更新", variant_ids=[variant["id"]], operation_id=str(uuid4()), **AUTHOR),
    )


def decision(selected, **extra):
    return dict(
        action="prices",
        variant_id=selected["id"],
        expected_variant_revision=selected["revision"],
        **AUTHOR,
        **extra,
    )


def edit(client, batch, value):
    return call(
        client,
        "/" + batch["id"],
        dict(
            expected_revision=batch["revision"],
            operation_id=str(uuid4()),
            edits=[dict(row_id=batch["rows"][0]["id"], decision=value)],
        ),
        method="patch",
    )


def publish(client, variant, *, amount="12.345", day="2026-09-01", state="amount"):
    batch = edit(
        client,
        batch_for(client, variant),
        decision(
            variant, prices=[dict(column=COLUMN, amount=amount, effective_date=day, state=state)]
        ),
    )
    request = dict(expected_revision=batch["revision"], row_ids=[batch["rows"][0]["id"]])
    preview = call(client, "/" + batch["id"] + "/preview", request)
    request.update(fingerprint=preview["fingerprint"], operation_id=str(uuid4()))
    result = call(client, "/" + batch["id"] + "/apply", request)
    assert call(client, "/" + batch["id"] + "/apply", request) == result
    return preview


def test_effective_slots_zero_inquiry_and_historical_revision(client, catalog):
    variant = catalog["variants"][0]
    publish(client, variant, amount="0")
    publish(client, variant, amount="20", day="2027-01-01")

    def price(day):
        return client.get(ROOT + "/prices/" + variant["id"], params={"on_date": day}).json()[
            "current"
        ][COLUMN]

    first = price("2026-09-02")
    assert first["amount"] == "0" and first["revision"] == 1
    publish(client, variant, amount="10")
    assert price("2026-09-02")["revision"] == 2
    history = client.get(ROOT + "/price-history/" + first["id"]).json()
    assert [p["amount"] for p in history] == ["10", "0"]
    publish(client, variant, amount=None, day="2026-10-01", state="inquiry")
    assert price("2026-12-01")["state"] == "inquiry"
    assert price("2027-01-01")["amount"] == "20"
    assert price("2020-01-01") is None
    assert client.get("/api/configuration/variants").json()[0]["revision"] == 1


def test_preview_atomic_and_stale_price_slot(client, catalog):
    variant = catalog["variants"][0]
    batch = edit(
        client,
        batch_for(client, variant),
        decision(
            variant,
            prices=[dict(column=COLUMN, state="amount", amount="8", effective_date="2026-09-01")],
        ),
    )
    request = dict(expected_revision=batch["revision"], row_ids=[batch["rows"][0]["id"]])
    preview = call(client, "/" + batch["id"] + "/preview", request)
    publish(client, variant, amount="9")
    call(
        client,
        "/" + batch["id"] + "/apply",
        dict(**request, fingerprint=preview["fingerprint"], operation_id=str(uuid4())),
        status=409,
    )
    assert client.get(ROOT + "/" + batch["id"]).json()["rows"][0]["state"] == "pending"


def test_cross_import_reordered_same_model_and_notes(client, catalog):
    wb = Workbook()
    ws = wb.active
    ws.title = "新版"
    ws.append(["产品型号", "产品名称", "性能描述(完整参数）", "备注", COLUMN, "单位"])
    ws.append(["SERVER-X", "服务器", "128GB", "新授权条件", 0, "台"])
    ws.append(["SERVER-X", "服务器", "64GB", "需要核对部署容量", None, "台"])
    stream = BytesIO()
    wb.save(stream)
    imported = client.post("/api/imports", files={"file": ("新版.xlsx", stream.getvalue())}).json()
    batch = call(
        client,
        "",
        dict(name="新版对比", import_id=imported["id"], operation_id=str(uuid4()), **AUTHOR),
    )
    assert len(batch["rows"]) == 2
    assert all(len(r["candidates"]) == 2 and not r["variant_id"] for r in batch["rows"])
    assert any(c["classification"] != "prices" for r in batch["rows"] for c in r["candidates"])
    assert all(r["classification"] == "unmatched" for r in batch["rows"])


def test_correction_scoped_impact_and_historical_project(client, catalog, config):
    variant = catalog["variants"][0]
    rule = knowledge(client, variant)
    original = post(client, "/check", dict(configuration=config))
    batch = batch_for(client, variant)
    fields = {k: v for k, v in variant.items() if k not in {"id", "revision", "updated_at"}}
    fields["attributes"] = [dict(key="memory", kind="quantity", value="96", unit="GB")]
    value = decision(variant, variant=fields)
    value["action"] = "correct"
    batch = edit(client, batch, value)
    request = dict(expected_revision=batch["revision"], row_ids=[batch["rows"][0]["id"]])
    preview = call(client, "/" + batch["id"] + "/preview", request)
    assert preview["changes"][0]["impact"]["rules"][0]["id"] == rule["id"]
    call(
        client,
        "/" + batch["id"] + "/apply",
        dict(**request, fingerprint=preview["fingerprint"], operation_id=str(uuid4())),
    )
    fresh = post(client, "/check", dict(configuration=config))
    assert any(c["kind"] == "catalog_review" for c in fresh["checks"])
    previous = post(client, "/check", dict(configuration=original["configuration"]))
    assert not any(c["kind"] == "catalog_review" for c in previous["checks"])
    assert client.get("/api/configuration/knowledge").json()[0]["status"] == "confirmed"


def test_keep_empty_does_not_replace_and_supply_is_independent(client, catalog):
    variant = catalog["variants"][0]
    publish(client, variant, amount="99")
    batch = edit(
        client,
        batch_for(client, variant),
        decision(variant, prices=[dict(column=COLUMN, state="keep", effective_date="2026-09-29")]),
    )
    req = dict(expected_revision=batch["revision"], row_ids=[batch["rows"][0]["id"]])
    preview = call(client, "/" + batch["id"] + "/preview", req)
    assert preview["changes"][0]["prices"] == []
    call(
        client,
        "/" + batch["id"] + "/apply",
        dict(**req, fingerprint=preview["fingerprint"], operation_id=str(uuid4())),
    )
    current = client.get(
        ROOT + "/prices/" + variant["id"], params=dict(on_date="2026-09-29")
    ).json()["current"]
    assert current[COLUMN]["amount"] == "99" and current["甲方指导价"] is None
    batch = batch_for(client, variant)
    value = decision(variant)
    value.update(
        action="supply", supply_status="discontinued", replacements=[catalog["variants"][1]["id"]]
    )
    batch = edit(client, batch, value)
    req = dict(expected_revision=batch["revision"], row_ids=[batch["rows"][0]["id"]])
    preview = call(client, "/" + batch["id"] + "/preview", req)
    call(
        client,
        "/" + batch["id"] + "/apply",
        dict(**req, fingerprint=preview["fingerprint"], operation_id=str(uuid4())),
    )
    variants = client.get("/api/configuration/variants").json()
    revised = next(v for v in variants if v["id"] == variant["id"])
    assert revised["status"] == "confirmed" and revised["supply_status"] == "discontinued"
    assert revised["attributes"] == variant["attributes"]


def test_new_configuration_copied_rules_draft_and_atomic_failure(client, catalog):
    variant = catalog["variants"][0]
    rule = knowledge(client, variant)
    batch = batch_for(client, variant)
    payload = {k: v for k, v in variant.items() if k not in {"id", "revision", "updated_at"}}
    payload.update(
        name="新规格", attributes=[dict(key="memory", kind="quantity", value="256", unit="GB")]
    )
    value = decision(variant, variant=payload, copy_rule_ids=[rule["id"]])
    value["action"] = "new_variant"
    batch = edit(client, batch, value)
    req = dict(expected_revision=batch["revision"], row_ids=[batch["rows"][0]["id"]])
    preview = call(client, "/" + batch["id"] + "/preview", req)
    result = call(
        client,
        "/" + batch["id"] + "/apply",
        dict(**req, fingerprint=preview["fingerprint"], operation_id=str(uuid4())),
    )
    identity = result["rows"][0]["result_variant_id"]
    assert identity != variant["id"]
    rules = client.get("/api/configuration/knowledge").json()
    copied = next(r for r in rules if r["id"] != rule["id"])
    assert copied["status"] == "draft" and copied["quantity_review"] == "unreviewed"
    assert copied["selector"]["variant_ids"] == [identity]
    assert len(client.get("/api/configuration/variants").json()) == 3


def test_unselected_row_not_published_and_late_error_rolls_back(client, catalog):
    selected = catalog["variants"]
    batch = call(
        client,
        "",
        dict(
            name="原子批次",
            variant_ids=[v["id"] for v in selected],
            operation_id=str(uuid4()),
            **AUTHOR,
        ),
    )
    edits = []
    for index, row in enumerate(sorted(batch["rows"], key=lambda r: r["id"])):
        v = next(v for v in selected if v["id"] == row["id"])
        d = decision(
            v,
            prices=[dict(column=COLUMN, state="amount", amount="12", effective_date="2026-09-29")],
        )
        if index == 1:
            d.update(
                action="supply", supply_status="available", replacements=["missing-configuration"]
            )
        edits.append(dict(row_id=row["id"], decision=d))
    batch = call(
        client,
        "/" + batch["id"],
        dict(expected_revision=batch["revision"], operation_id=str(uuid4()), edits=edits),
        method="patch",
    )
    req = dict(expected_revision=batch["revision"], row_ids=[r["id"] for r in batch["rows"]])
    preview = call(client, "/" + batch["id"] + "/preview", req)
    call(
        client,
        "/" + batch["id"] + "/apply",
        dict(**req, fingerprint=preview["fingerprint"], operation_id=str(uuid4())),
        status=422,
    )
    assert all(not client.get(ROOT + "/prices/" + v["id"]).json()["history"] for v in selected)
    req["row_ids"] = [edits[0]["row_id"]]
    preview = call(client, "/" + batch["id"] + "/preview", req)
    result = call(
        client,
        "/" + batch["id"] + "/apply",
        dict(**req, fingerprint=preview["fingerprint"], operation_id=str(uuid4())),
    )
    assert sorted(r["state"] for r in result["rows"]) == ["applied", "pending"]
