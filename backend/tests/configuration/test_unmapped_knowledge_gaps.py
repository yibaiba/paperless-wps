from copy import deepcopy

from presales.configuration.definitions.gaps import knowledge_gaps
from presales.configuration.definitions.readiness import package_readiness
from presales.configuration.definitions.schemas import KnowledgePackage
from presales.configuration.knowledge.schemas import KnowledgeInput

from .conftest import AUTHOR, BASE, knowledge, post
from .test_list_mcp import call
from .test_list_mcp import create as create_draft


def legacy_bundle(client, catalog):
    definition = post(
        client,
        "/definitions",
        dict(
            name="会议预约与信息发布系统",
            status="confirmed",
            roles=[dict(id="server", name="服务端软件")],
            **AUTHOR,
        ),
    )
    rule = knowledge(client, catalog["variants"][0], system="会议预约", role="服务端软件")
    package = post(
        client,
        "/knowledge-packages",
        dict(
            name="隔离旧文字资料包",
            branch="预约",
            status="published",
            system_definition_id=definition["id"],
            definition_revision=1,
            members=[dict(id=rule["id"], revision=1)],
            **AUTHOR,
        ),
    )
    return definition, rule, package


def mapping_gaps(items):
    return [i for i in items if i["code"] == "relation_role_unmapped"]


def test_unmapped_relation_has_the_same_action_across_readiness_agent_and_maintenance(
    client, catalog
):
    definition, rule, package = legacy_bundle(client, catalog)
    readiness = client.get(BASE + f"/knowledge-packages/{package['id']}/readiness").json()
    agent = call(
        client,
        "systems_list",
        dict(definition_id=definition["id"], knowledge_package_id=package["id"]),
    )
    maintenance = client.get(BASE + "/maintenance-tasks").json()
    gaps = mapping_gaps(readiness["gaps"])
    assert len(gaps) == 1
    assert gaps == mapping_gaps(agent["requirement_description"]["generation"]["gaps"])
    assert gaps == mapping_gaps(maintenance["knowledge_gaps"])
    assert gaps[0]["object_id"] == rule["id"]
    assert gaps[0]["object_revision"] == 1
    assert gaps[0]["missing_fields"] == ["system_definition_id", "role_id"]
    assert gaps[0]["action"] == dict(type="edit_knowledge", rule_id=rule["id"])
    assert gaps[0]["evidence"] == rule["evidence"]


def test_explicit_mapping_requires_package_adoption_and_preserves_old_revision(client, catalog):
    definition, rule, package = legacy_bundle(client, catalog)
    original = client.get(BASE + "/knowledge-packages").json()[0]
    payload = {k: v for k, v in rule.items() if k in KnowledgeInput.model_fields}
    payload.update(system_definition_id=definition["id"], role_id="server")
    response = client.put(
        BASE + "/knowledge/" + rule["id"], json=dict(expected_revision=1, payload=payload)
    )
    assert response.status_code == 200, response.text
    before = client.get(BASE + f"/knowledge-packages/{package['id']}/readiness").json()
    assert mapping_gaps(before["gaps"])
    value = {k: v for k, v in package.items() if k in KnowledgePackage.model_fields}
    value["members"] = [dict(id=rule["id"], revision=2)]
    preview = post(
        client,
        f"/knowledge-packages/{package['id']}/change-preview",
        dict(expected_revision=1, payload=value),
    )
    assert not mapping_gaps(preview["readiness"]["gaps"])
    assert preview["readiness"]["roles"][0]["candidate_ids"] == [catalog["variants"][0]["id"]]
    assert preview["readiness"]["roles"][0]["missing"]
    assert client.get(BASE + "/knowledge-packages").json() == [original]
    response = client.put(
        BASE + "/knowledge-packages/" + package["id"],
        json=dict(expected_revision=1, payload=value),
    )
    assert response.status_code == 200, response.text
    assert mapping_gaps(knowledge_gaps(original["definition"], original))
    assert not mapping_gaps(knowledge_gaps(response.json()["definition"], response.json()))


def test_matching_legacy_labels_disabled_rules_and_explicit_wrong_ids_stay_distinct(
    client, catalog
):
    definition, rule, package = legacy_bundle(client, catalog)
    legacy = dict(rule, system=definition["name"])
    wrong = dict(legacy, id="wrong", system_definition_id="other-system")
    disabled = dict(rule, id="disabled", status="disabled")
    package["rules"] = [legacy, wrong, disabled]
    before = deepcopy(package)
    report = package_readiness(package, latest={definition["id"]: 1, rule["id"]: 1})
    assert report["unmapped_rule_ids"] == ["wrong"]
    assert [g["object_id"] for g in mapping_gaps(report["gaps"])] == ["wrong"]
    assert package == before


def test_agent_unmapped_systems_uses_explicit_ids_and_the_selected_knowledge_snapshot(
    client, catalog
):
    definition, rule, _ = legacy_bundle(client, catalog)
    draft = create_draft(client)
    fixed = {key: draft[key] for key in ("definition_snapshot_id", "knowledge_snapshot_id")}
    before = call(client, "systems_list", fixed)
    assert before["unmapped_systems"] == [dict(name="会议预约", status="unmapped")]
    payload = {k: v for k, v in rule.items() if k in KnowledgeInput.model_fields}
    payload.update(system_definition_id=definition["id"], role_id="server")
    response = client.put(
        BASE + "/knowledge/" + rule["id"], json=dict(expected_revision=1, payload=payload)
    )
    assert response.status_code == 200, response.text
    assert call(client, "systems_list", {})["unmapped_systems"] == []
    assert call(client, "systems_list", fixed) == before
