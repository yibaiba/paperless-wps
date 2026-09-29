from copy import deepcopy

from .conftest import AUTHOR, BASE, knowledge, post
from .test_package_readiness import bundle


def payload(rule):
    return {
        k: v
        for k, v in rule.items()
        if k
        not in {
            "id",
            "revision",
            "updated_at",
            "completion",
            "missing_fields",
        }
    }


def test_mapping_batch_preserves_evidence_and_fixed_package_and_retries(client, catalog):
    definition, original, package = bundle(client, catalog)
    data = payload(original)
    data.update(
        system=definition["name"],
        role="服务端",
        identity_mapping={
            "actor": AUTHOR["actor"],
            "evidence": "逐条核对历史文字",
            "definition_revision": 1,
            "previous_system": original["system"],
            "previous_revision": 1,
        },
    )
    items = [dict(id=original["id"], expected_revision=1, payload=data)]
    before = client.get(BASE + "/knowledge-packages").json()
    preview = post(client, "/knowledge/change-preview", dict(items=items))
    assert client.get(BASE + "/knowledge").json()[0]["revision"] == 1
    request = dict(items=items, fingerprint=preview["fingerprint"], operation_id="mapping-test")
    first = post(client, "/knowledge/change-apply", request)
    assert post(client, "/knowledge/change-apply", request) == first
    assert first[0]["revision"] == 2
    for key in ("status", "quantity_review", "evidence", "selector", "conditions", "evidence_refs"):
        assert first[0][key] == original[key]
    assert client.get(BASE + "/knowledge-packages").json() == before
    report = client.get(BASE + "/knowledge-packages/" + package["id"] + "/readiness").json()
    assert report["rules"][0]["revision"] == 1
    assert report["version_changes"][0]["latest"] == 2
    stale = dict(request, operation_id="another-mapping")
    assert client.post(BASE + "/knowledge/change-apply", json=stale).status_code == 409


def test_quantity_confirmation_requires_evidence_and_keeps_unknown_draft(client, catalog):
    rule = knowledge(
        client,
        catalog["variants"][0],
        kind="accessory",
        schema_version=2,
        need_name="服务端",
        mode=None,
        calculation_scope=None,
        factor=None,
    )
    data = payload(rule)
    data["quantity_review"] = "confirmed"
    rejected = client.put(
        BASE + "/knowledge/" + rule["id"], json=dict(expected_revision=1, payload=data)
    )
    assert rejected.status_code == 422
    data.update(quantity_review="unreviewed", quantity_evidence="仍缺少容量依据")
    saved = client.put(
        BASE + "/knowledge/" + rule["id"], json=dict(expected_revision=1, payload=data)
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["factor"] is None
    assert saved.json()["status"] == "confirmed"
    confirmed = deepcopy(data)
    confirmed.update(
        target_variant_ids=[catalog["variants"][1]["id"]],
        calculation_scope="system",
        mode="per_group",
        factor="1",
        quantity_review="confirmed",
        quantity_evidence="隔离测试：每系统一台",
    )
    response = client.put(
        BASE + "/knowledge/" + rule["id"], json=dict(expected_revision=2, payload=confirmed)
    )
    assert response.status_code == 200, response.text
    assert response.json()["quantity_review"] == "confirmed"
    assert response.json()["selector"] == rule["selector"]
