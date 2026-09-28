from copy import deepcopy

from presales.configuration.definitions.schemas import KnowledgePackage, SystemDefinition
from presales.configuration.knowledge.schemas import KnowledgeInput

from .conftest import AUTHOR, BASE, knowledge, post
from .test_evolution import ready_project


def test_quantity_inputs_require_matching_units_and_have_provenance(client, catalog, config):
    data = deepcopy(config)
    data["calculation_version"] = 3
    data["requirements"][0]["environment"] = [
        dict(key="storage", kind="quantity", value="12", unit="GB")
    ]
    knowledge(
        client,
        catalog["variants"][0],
        schema_version=2,
        kind="accessory",
        target_variant_ids=[catalog["variants"][1]["id"]],
        quantity_review="confirmed",
        quantity_evidence=AUTHOR["evidence"],
        calculation_scope="system",
        mode="per_capacity",
        factor="5",
        quantity_source="environment",
        quantity_key="storage",
        quantity_unit="GB",
    )
    checked = post(client, "/check", dict(configuration=data))
    suggestion = checked["suggestions"][0]
    assert suggestion["required"] == "3"
    item = suggestion["quantity_inputs"][0]
    assert (item["value"], item["unit"], item["variant_revision"]) == ("12", "GB", 1)
    assert item["source_id"] == catalog["sources"][0]["id"]
    before = deepcopy(checked["configuration"])
    repeated = post(client, "/check", dict(configuration=before))
    assert repeated["configuration"] == before
    assert repeated["fingerprint"] == checked["fingerprint"]
    before["requirements"][0]["environment"][0]["unit"] = "TB"
    unknown = post(client, "/check", dict(configuration=before))["suggestions"][0]
    assert unknown["status"] == "unknown" and unknown["required"] is None
    assert "单位" in unknown["quantity_inputs"][0]["error"]


def test_package_member_and_definition_revisions_stay_fixed_until_refresh(client, catalog, config):
    checked = post(client, "/check", dict(configuration=ready_project(client, catalog, config)))
    package = client.get(BASE + "/knowledge-packages").json()[0]
    rule = package["rules"][0]
    rule_payload = editable(KnowledgeInput, rule)
    rule_payload["effect"] = "deny"
    response = client.put(
        BASE + "/knowledge/" + rule["id"], json=dict(payload=rule_payload, expected_revision=1)
    )
    assert response.status_code == 200, response.text
    latest = post(
        client, "/check", dict(configuration=checked["configuration"], refresh_knowledge=True)
    )
    assert latest["readiness"]["ready_for_confirmation"], "已发布包仍固定成员 v1"
    definition = package["definition"]
    payload = editable(SystemDefinition, definition)
    payload["name"] = "重命名无纸化，身份不变"
    response = client.put(
        BASE + "/definitions/" + definition["id"], json=dict(payload=payload, expected_revision=1)
    )
    assert response.status_code == 200, response.text
    package_payload = editable(KnowledgePackage, package)
    package_payload.update(definition_revision=2, members=[dict(id=rule["id"], revision=2)])
    response = client.put(
        BASE + "/knowledge-packages/" + package["id"],
        json=dict(payload=package_payload, expected_revision=1),
    )
    assert response.status_code == 200, response.text
    frozen = post(client, "/check", dict(configuration=checked["configuration"]))
    assert frozen["checks"] == checked["checks"]
    assert frozen["fingerprint"] == checked["fingerprint"]
    assert {"system_definition", "knowledge_package"} <= {
        c["kind"] for c in frozen["version_changes"]
    }
    refreshed = post(
        client, "/check", dict(configuration=checked["configuration"], refresh_knowledge=True)
    )
    assert any(
        c["kind"] == "compatibility" and c["status"] == "conflict" for c in refreshed["checks"]
    )
    assert not refreshed["readiness"]["ready_for_confirmation"]


def editable(schema, record):
    return schema.model_validate(
        {k: v for k, v in record.items() if k in schema.model_fields}
    ).model_dump(mode="json")
