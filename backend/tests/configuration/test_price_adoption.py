from copy import deepcopy
from uuid import uuid4

from .conftest import post
from .test_catalog_updates import COLUMN, call, publish


def prepare(client, config):
    config = deepcopy(config)
    config.update(
        calculation_version=3,
        quotation=dict(price_column=COLUMN, price_adoption_date="2026-09-29"),
        supply_allocations=[
            dict(
                id="purchase",
                device_id="device-1",
                source="purchase",
                quantity="1",
                evidence="隔离采购依据",
            )
        ],
    )
    return post(client, "/check", dict(configuration=config))["configuration"]


def price_preview(client, data, day="2026-09-29"):
    return call(client, "/project-price-preview", dict(configuration=data, adoption_date=day))


def adopt(client, project, data, preview):
    ref = preview["rows"][0]["price"]
    operation = dict(
        action="price_versions_adopt",
        adoption_date=preview["adoption_date"],
        fingerprint=preview["fingerprint"],
        items=[dict(device_id="device-1", price=dict(id=ref["id"], revision=ref["revision"]))],
    )
    return client.post(
        "/api/configuration/projects/" + project["id"] + "/edit-preview",
        json=dict(configuration=data, expected_revision=0, draft_version=0, operations=[operation]),
    )


def test_adoption_immutable_decimal_and_forgery(client, catalog, config, project):
    variant = catalog["variants"][0]
    publish(client, variant, amount="12.345")
    data = prepare(client, config)
    original = deepcopy(data)
    preview = price_preview(client, data)
    result = adopt(client, project, data, preview)
    assert result.status_code == 200, result.text
    checked = result.json()["checked"]
    assert checked["quotation_output"]["total"] == "12.35"
    assert checked["configuration"]["devices"] == original["devices"]
    chosen = checked["configuration"]["quotation"]["prices"][0]
    assert chosen["mode"] == "version" and chosen["unit_price"] == "12.345"
    publish(client, variant, amount="25")
    historical = post(client, "/check", dict(configuration=checked["configuration"]))
    assert historical["quotation_output"]["total"] == "12.35"
    assert price_preview(client, checked["configuration"])["rows"][0]["difference"] == "12.65"
    tampered = deepcopy(checked["configuration"])
    tampered["quotation"]["prices"][0]["unit_price"] = "1"
    response = client.post("/api/configuration/check", json=dict(configuration=tampered))
    assert response.status_code == 422, response.text
    stale = adopt(client, project, data, preview)
    assert stale.status_code == 409, stale.text


def test_manual_protected_inquiry_and_future_price(client, catalog, config, project):
    variant = catalog["variants"][0]
    publish(client, variant, amount="0")
    data = prepare(client, config)
    selected = data["quotation"]["prices"][0]
    selected.update(mode="manual", unit_price="18", evidence="隔离人工优惠")
    preview = price_preview(client, data)
    assert preview["rows"][0]["protected"]
    assert preview["rows"][0]["difference"] == "-18.00"
    publish(client, variant, amount=None, state="inquiry", day="2026-10-01")
    assert price_preview(client, data)["rows"][0]["price"]["amount"] == "0"
    inquiry = price_preview(client, data, "2026-10-02")
    assert inquiry["rows"][0]["issues"]
    blocked = adopt(client, project, data, inquiry)
    assert blocked.status_code == 422, blocked.text


def test_mcp_reads_and_applies_same_price(client, catalog, config, project):
    publish(client, catalog["variants"][0], amount="20.005")
    data = prepare(client, config)
    saved = client.put(
        "/api/configuration/projects/" + project["id"],
        json=dict(expected_revision=0, configuration=data),
    )
    assert saved.status_code == 200, saved.text

    def tool(name, payload):
        result = client.post("/api/list-tools/" + name, json=payload)
        assert result.status_code == 200, result.text
        return result.json()

    draft = tool(
        "list_create",
        dict(
            name="隔离改单",
            project_id=project["id"],
            revision=1,
            actor="测试",
            evidence="隔离",
            operation_id=str(uuid4()),
        ),
    )
    preview = tool(
        "list_get",
        dict(draft_id=draft["id"], view="price_updates", price_adoption_date="2026-09-29"),
    )
    row = preview["rows"][0]
    tool(
        "list_update",
        dict(
            draft_id=draft["id"],
            expected_revision=draft["revision"],
            operation_id=str(uuid4()),
            operations=[
                dict(
                    action="price_versions_adopt",
                    adoption_date="2026-09-29",
                    fingerprint=preview["fingerprint"],
                    items=[
                        dict(
                            device_id="device-1",
                            price={k: row["price"][k] for k in ("id", "revision")},
                        )
                    ],
                )
            ],
        ),
    )
    quote = tool("list_get", dict(draft_id=draft["id"], view="quotation"))
    assert quote["total"] == "20.01"
    assert quote["items"][0]["price_selection"]["mode"] == "version"
