from copy import deepcopy

import pytest

from .conftest import BASE, post
from .test_package_readiness import bundle


def prepare(client, catalog, *, status="confirmed"):
    definition, rule, package = bundle(client, catalog)
    payload = {
        k: v
        for k, v in rule.items()
        if k not in {"id", "revision", "updated_at", "completion", "missing_fields"}
    }
    payload.update(
        status=status, conditions=[dict(field="project.os", operator="eq", value="Windows")]
    )
    response = client.put(
        BASE + "/knowledge/" + rule["id"], json=dict(expected_revision=1, payload=payload)
    )
    assert response.status_code == 200, response.text
    data = {
        k: v
        for k, v in package.items()
        if k not in {"id", "revision", "updated_at", "definition", "rules"}
    }
    data["members"] = [dict(id=rule["id"], revision=2)]
    response = client.put(
        BASE + "/knowledge-packages/" + package["id"], json=dict(expected_revision=1, payload=data)
    )
    assert response.status_code == 200, response.text
    return definition, response.json()


def request(catalog, **extra):
    return dict(expected_revision=2, role_id="s", variant_id=catalog["variants"][0]["id"], **extra)


@pytest.mark.parametrize(
    "value,expected", [("Windows", "pass"), ("Linux", "conflict"), (None, "unknown")]
)
def test_trial_uses_same_conditions_and_never_approves_draft_package(
    client, catalog, value, expected
):
    _, package = prepare(client, catalog)
    before = client.get(BASE + "/knowledge-packages").json()
    environment = [] if value is None else [dict(key="os", kind="text", value=value)]
    result = post(
        client,
        "/knowledge-packages/" + package["id"] + "/trial",
        request(catalog, environment=environment),
    )
    assert result["status"] == expected
    assert result["package_status"] == result["definition_status"] == "draft"
    assert result["coverage"]["status"] == "unknown"
    assert result["package_revision"] == 2
    assert result["variant_revision"] == 1
    assert result["evidence"][0]["revision"] == 2
    assert client.get(BASE + "/knowledge-packages").json() == before
    assert (
        post(
            client,
            "/knowledge-packages/" + package["id"] + "/trial",
            request(catalog, environment=environment),
        )
        == result
    )


def test_draft_rule_is_visible_but_never_passes(client, catalog):
    _, package = prepare(client, catalog, status="draft")
    result = post(
        client,
        "/knowledge-packages/" + package["id"] + "/trial",
        request(catalog, environment=[dict(key="os", kind="text", value="Windows")]),
    )
    assert result["status"] == "unknown"
    assert len(result["draft_relations"]) == 1


def test_pinned_rule_not_silently_updated(client, catalog):
    _, package = prepare(client, catalog)
    rule = package["rules"][0]
    payload = {k: v for k, v in rule.items() if k not in {"id", "revision"}}
    payload["conditions"][0]["value"] = "Linux"
    assert (
        client.put(
            BASE + "/knowledge/" + rule["id"], json=dict(expected_revision=2, payload=payload)
        ).status_code
        == 200
    )
    result = post(
        client,
        "/knowledge-packages/" + package["id"] + "/trial",
        request(catalog, environment=[dict(key="os", kind="text", value="Windows")]),
    )
    assert result["status"] == "pass"
    assert result["evidence"][0]["revision"] == 2


@pytest.mark.parametrize(
    "change,status",
    [
        ({"expected_revision": 1}, 409),
        ({"role_id": "other"}, 422),
        ({"variant_id": "missing"}, 422),
    ],
)
def test_invalid_trial_has_explicit_error(client, catalog, change, status):
    _, package = prepare(client, catalog)
    response = client.post(
        BASE + "/knowledge-packages/" + package["id"] + "/trial",
        json={**request(catalog), **change},
    )
    assert response.status_code == status, response.text


def test_duplicate_inputs_do_not_use_last_value(client, catalog):
    _, package = prepare(client, catalog)
    inputs = [dict(key="os", kind="text", value=v) for v in ("Windows", "Linux")]
    assert (
        client.post(
            BASE + "/knowledge-packages/" + package["id"] + "/trial",
            json=request(catalog, environment=inputs),
        ).status_code
        == 422
    )


@pytest.mark.parametrize("field", ["engine_version", "compiler_version", "hash"])
def test_published_trial_validates_fixed_decision_bundle(client, catalog, field):
    from presales.configuration.models import Entity

    from .test_proposal_generation import published

    _, package = published(client, catalog)
    payload = dict(
        expected_revision=package["revision"],
        role_id="terminal",
        variant_id=catalog["variants"][0]["id"],
    )
    path = BASE + "/knowledge-packages/" + package["id"] + "/trial"
    normal = client.post(path, json=payload)
    assert normal.status_code == 200 and normal.json()["status"] == "pass", normal.text
    with client.app.state.session_factory() as session:
        record = session.get(Entity, package["decision_bundle_id"])
        record.payload = dict(record.payload, **{field: "unavailable"})
        session.commit()
    invalid = client.post(path, json=payload)
    assert invalid.status_code == 422 and "不能静默重编译" in invalid.text


def test_missing_feature_role_carries_correct_action(client, catalog, config):
    from .test_evolution import ready_project

    data = ready_project(client, catalog, config)
    snapshot = post(client, "/check", dict(configuration=data))["configuration"]
    definition = client.get(BASE + "/definitions").json()["definitions"][0]
    original = deepcopy(definition)
    definition["roles"].append(
        dict(id="voting", name="投票客户端", required=True, feature="投票", capability_ids=[])
    )
    payload = {
        k: v
        for k, v in definition.items()
        if k not in {"id", "revision", "updated_at", "inspection_profiles"}
    }
    assert (
        client.put(
            BASE + "/definitions/" + definition["id"],
            json=dict(expected_revision=1, payload=payload),
        ).status_code
        == 200
    )
    # Old project retains package v1 and its original roles even after the definition changes.
    snapshot["systems"][0]["features"] = ["投票"]
    old = post(client, "/check", dict(configuration=snapshot))
    assert not any(c.get("role_id") == "voting" for c in old["checks"])
    data["systems"][0].update(knowledge_package_id="", features=["投票"])
    current = post(client, "/check", dict(configuration=data))
    missing = next(c for c in current["checks"] if c.get("role_id") == "voting")
    assert missing["action"]["type"] == "add_requirement"
    assert missing["action"]["role_id"] == "voting"
    assert missing["action"]["role_name"] == "投票客户端"
    assert missing["action"]["feature"] == "投票"
    data["systems"][0]["features"] = []
    inactive = post(client, "/check", dict(configuration=data))
    assert not any(c.get("role_id") == "voting" for c in inactive["checks"])
    assert len(original["roles"]) == 1
