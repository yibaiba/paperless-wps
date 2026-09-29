from copy import deepcopy

from .conftest import BASE, post
from .test_package_readiness import bundle


def test_preview_keeps_fixed_definition_and_is_read_only(client, catalog):
    definition, rule, package = bundle(client, catalog)
    before = client.get(BASE + "/knowledge-packages").json()
    body = {
        k: v
        for k, v in definition.items()
        if k not in {"id", "revision", "updated_at", "inspection_profiles"}
    }
    body["roles"].append(dict(id="another", name="新角色"))
    assert (
        client.put(
            BASE + "/definitions/" + definition["id"], json=dict(expected_revision=1, payload=body)
        ).status_code
        == 200
    )
    payload = {
        k: v
        for k, v in package.items()
        if k not in {"id", "revision", "updated_at", "definition", "rules"}
    }
    original = deepcopy(payload)
    result = post(
        client,
        "/knowledge-packages/" + package["id"] + "/change-preview",
        dict(expected_revision=1, payload=payload),
    )
    assert result["definition"]["after"]["revision"] == 1
    assert result["relations"] == []
    payload["definition_revision"] = 2
    upgraded = post(
        client,
        "/knowledge-packages/" + package["id"] + "/change-preview",
        dict(expected_revision=1, payload=payload),
    )
    assert upgraded["definition"]["after"]["revision"] == 2
    assert len(upgraded["definition"]["after"]["roles"]) == 2
    assert client.get(BASE + "/knowledge-packages").json() == before
    response = client.post(
        BASE + "/knowledge-packages/" + package["id"] + "/change-preview",
        json=dict(expected_revision=9, payload=original),
    )
    assert response.status_code == 409
