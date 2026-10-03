from .conftest import BASE
from .test_list_mcp import call
from .test_proposal_generation import published


def test_readiness_description_and_agent_share_structured_gaps(client, catalog):
    definition, package = published(client, catalog, quantity=False, ranked=False)
    readiness = client.get(BASE + f"/knowledge-packages/{package['id']}/readiness").json()
    description = client.post(
        BASE + "/requirement-description",
        json=dict(definition_id=definition["id"], knowledge_package_id=package["id"]),
    ).json()
    agent = call(
        client,
        "systems_list",
        dict(definition_id=definition["id"], knowledge_package_id=package["id"]),
    )
    assert readiness["gaps"] == description["generation"]["gaps"]
    assert readiness["gaps"] == agent["requirement_description"]["generation"]["gaps"]
    assert {g["code"] for g in readiness["gaps"]} >= {
        "role_quantity_missing",
        "recommendation_missing",
        "sharing_basis_missing",
    }
    maintenance = client.get(BASE + "/maintenance-tasks").json()
    assert maintenance["knowledge_gaps"] == readiness["gaps"]
    for item in readiness["gaps"]:
        assert item["object_id"] and item["missing_fields"] and item["maintenance_url"]


def test_shared_knowledge_gap_does_not_block_independent_generation(client, catalog):
    definition, package = published(client, catalog)
    description = client.post(
        BASE + "/requirement-description",
        json=dict(definition_id=definition["id"], knowledge_package_id=package["id"]),
    ).json()
    coverage = description["generation"]
    assert coverage["supported"]
    assert any(
        g["code"] == "sharing_basis_missing" and g["scenario"] == "shared" for g in coverage["gaps"]
    )


def test_fulfillment_gap_checks_system_identity(client, catalog):
    from copy import deepcopy

    from presales.configuration.definitions.gaps import knowledge_gaps

    definition, package = published(client, catalog, accessory=True)
    package = deepcopy(package)
    assert not any(
        g["code"] == "role_fulfillment_target_missing" for g in knowledge_gaps(definition, package)
    )
    for rule in package["rules"]:
        if rule["kind"] == "accessory":
            rule["system_definition_id"] = "another-system"
    assert any(
        g["code"] == "role_fulfillment_target_missing" for g in knowledge_gaps(definition, package)
    )


def test_fulfillment_accepts_explicitly_unrestricted_accessory(client, catalog):
    from copy import deepcopy

    from presales.configuration.definitions.gaps import knowledge_gaps

    definition, package = published(client, catalog, accessory=True)
    package = deepcopy(package)
    for rule in package["rules"]:
        if rule["kind"] == "accessory":
            rule.update(system_definition_id="", system="", role_id="", role="")
    assert not any(
        g["code"] == "role_fulfillment_target_missing" for g in knowledge_gaps(definition, package)
    )
