from copy import deepcopy

from .conftest import BASE, knowledge, post


def candidates(client, environment=None, **extra):
    return post(
        client,
        "/candidates",
        dict(system="无纸化", role="服务端", environment=environment or [], **extra),
    )


def test_explicit_denial_not_overridden_by_allow(client, catalog):
    variant = catalog["variants"][0]
    knowledge(client, variant)
    knowledge(client, variant, effect="deny")
    result = next(r for r in candidates(client) if r["variant"]["id"] == variant["id"])
    assert result["status"] == "conflict"
    assert len(result["evidence"]) == 2


def test_architecture_os_unknown_and_exclusions(client, catalog):
    variant = catalog["variants"][0]
    knowledge(
        client,
        variant,
        conditions=[
            dict(field="product.cpu_arch", operator="eq", value="arm"),
            dict(field="project.os", operator="eq", value="麒麟"),
        ],
    )
    result = next(r for r in candidates(client) if r["variant"]["id"] == variant["id"])
    assert result["status"] == "conflict"
    assert result["evidence"][0]["conditions"][1]["result"] == "unknown"
    unknown = next(
        r for r in candidates(client, include_all=True) if r["variant"]["id"] != variant["id"]
    )
    assert unknown["status"] == "unknown"


def test_numeric_ranges_sets_and_units(client, catalog):
    variant = catalog["variants"][0]
    knowledge(
        client,
        variant,
        conditions=[
            dict(field="product.cpu_arch", operator="any", value=["x86", "arm"]),
            dict(field="product.memory", operator="range", minimum="32", maximum="256", unit="GB"),
        ],
    )
    assert (
        next(r for r in candidates(client) if r["variant"]["id"] == variant["id"])["status"]
        == "pass"
    )
    knowledge(
        client,
        variant,
        effect="deny",
        selector={"category": "服务器", "exclude_variant_ids": [variant["id"]]},
    )
    checked = candidates(client, include_all=True)
    assert next(r for r in checked if r["variant"]["id"] == variant["id"])["status"] == "pass"
    assert next(r for r in checked if r["variant"]["id"] != variant["id"])["status"] == "conflict"


def test_accessory_application_idempotent(client, catalog, config):
    target = catalog["variants"][1]
    rule = knowledge(
        client,
        catalog["variants"][0],
        kind="accessory",
        target_variant_ids=[target["id"]],
        factor="2",
    )
    checked = post(client, "/check", dict(configuration=config))
    suggestion = checked["suggestions"][0]
    assert suggestion["required"] == "2"
    request = dict(
        configuration=checked["configuration"],
        fingerprint=checked["fingerprint"],
        suggestion_id=suggestion["id"],
        variant_id=target["id"],
        source_id=catalog["sources"][1]["id"],
    )
    applied = post(client, "/apply", request)
    assert len(applied["configuration"]["devices"]) == 2
    assert applied["suggestions"][0]["missing"] == "0"
    repeated = post(
        client,
        "/apply",
        {
            **request,
            "configuration": applied["configuration"],
            "fingerprint": applied["fingerprint"],
        },
    )
    assert len(repeated["configuration"]["devices"]) == 2
    assert repeated["suggestions"][0]["rule"]["id"] == rule["id"]
    stale = {**request, "configuration": deepcopy(request["configuration"])}
    stale["configuration"]["devices"][0]["quantity"] = "3"
    assert client.post(BASE + "/apply", json=stale).status_code == 409


def test_accessory_conflicting_knowledge_not_applied(client, catalog, config):
    target = catalog["variants"][1]
    for effect in ["allow", "deny"]:
        knowledge(
            client,
            catalog["variants"][0],
            kind="accessory",
            effect=effect,
            target_variant_ids=[target["id"]],
        )
    result = post(client, "/check", dict(configuration=config))
    assert result["suggestions"][0]["status"] == "conflict"


def test_sharing_confirmed_and_software_requirements_stay_separate(client, catalog, config):
    config["requirements"].append({**config["requirements"][0], "id": "r2", "system_id": "booking"})
    knowledge(
        client,
        catalog["variants"][0],
        kind="sharing",
        shared_roles=["无纸化/服务端", "会议预约/服务端"],
    )
    result = post(client, "/check", dict(configuration=config))
    assert all(c["status"] == "pass" for c in result["checks"] if c["kind"] == "sharing")
    assert len(result["configuration"]["devices"]) == 1
    config["devices"][0]["quantity"] = "2"
    assert client.post(BASE + "/check", json=dict(configuration=config)).status_code == 422


def test_explicit_environment_cannot_ignore_architecture(client, catalog):
    knowledge(client, catalog["variants"][0])
    result = candidates(client, [dict(key="cpu_arch", kind="text", value="arm", unit="")])
    assert (
        next(c for c in result if c["variant"]["id"] == catalog["variants"][0]["id"])["status"]
        == "conflict"
    )


def test_snapshot_cannot_drop_conflicting_rule(client, catalog, config):
    knowledge(client, catalog["variants"][0])
    knowledge(client, catalog["variants"][0], effect="deny")
    checked = post(client, "/check", dict(configuration=config))
    data = checked["configuration"]
    data["knowledge_snapshot"] = [k for k in data["knowledge_snapshot"] if k["effect"] != "deny"]
    assert client.post(BASE + "/check", json=dict(configuration=data)).status_code == 422
    data["knowledge_snapshot_id"] = None
    assert client.post(BASE + "/check", json=dict(configuration=data)).status_code == 422


def test_candidates_default_to_related_scope_and_can_use_snapshot(client, catalog, config):
    variant = catalog["variants"][0]
    rule = knowledge(client, variant)
    knowledge(client, catalog["variants"][1], status="draft")
    scoped = candidates(client)
    assert {item["variant"]["id"] for item in scoped} == {
        variant["id"],
        catalog["variants"][1]["id"],
    }
    unknown = next(item for item in scoped if item["variant"]["id"] != variant["id"])
    assert unknown["status"] == "unknown"
    assert len(candidates(client, include_all=True)) == 2
    checked = post(client, "/check", dict(configuration=config))
    payload = {k: v for k, v in rule.items() if k not in {"id", "revision", "updated_at"}}
    payload["effect"] = "deny"
    updated = client.put(
        BASE + "/knowledge/" + rule["id"],
        json=dict(expected_revision=1, payload=payload),
    )
    assert updated.status_code == 200, updated.text
    assert next(
        item for item in candidates(client) if item["variant"]["id"] == variant["id"]
    )["status"] == "conflict"
    pinned = candidates(
        client,
        knowledge_snapshot_id=checked["configuration"]["knowledge_snapshot_id"],
    )
    pinned_variant = next(item for item in pinned if item["variant"]["id"] == variant["id"])
    assert pinned_variant["status"] == "pass"
