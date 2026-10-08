from io import BytesIO
from zipfile import ZipFile

import pytest

from presales.configuration.definitions.schemas import KnowledgePackage
from presales.configuration.knowledge.schemas import KnowledgeInput

from .conftest import AUTHOR, post
from .test_evolution_versions import editable
from .test_proposal_generation import apply, draft_for, plan, published, read, write
from .test_proposal_prices_and_cycles import priced


def test_source_disagreement_survives_price_edit_save_and_manual_regeneration(
    client, catalog, workbook, project
):
    stream = BytesIO(workbook)
    with ZipFile(stream, "a") as archive:
        archive.comment = b"Independent source copy for isolated test"
    imported = client.post(
        "/api/imports", files={"file": ("additional.xlsx", stream.getvalue())}
    ).json()
    sources = client.get("/api/products", params={"import_id": imported["id"]}).json()
    sources = [client.get("/api/products/" + s["id"]).json() for s in sources]
    source = next(s for s in sources if s["specification"] == "64GB")
    post(
        client,
        "/source-links",
        dict(
            variant_id=catalog["variants"][0]["id"],
            items=[dict(source_id=source["id"], expected_revision=0)],
            **AUTHOR,
        ),
    )
    draft = priced(client, catalog, amount="10")
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    device = data["devices"][0]
    requirement = data["requirements"][0]
    # Same configuration, two valid sources; explicitly choose the other source.
    alternate = next(
        s for s in device["variant_snapshot"]["source_ids"] if s != device["source_id"]
    )
    generation = dict(
        data["generation"],
        preferences=[
            dict(
                requirement_id=requirement["id"],
                source_id=alternate,
                evidence="隔离客户明确资料版本",
            )
        ],
    )
    draft = write(client, draft, [dict(action="requirements_patch", generation=generation)])
    draft = write(
        client,
        draft,
        [
            dict(
                action="requirement_put",
                value=dict(
                    requirement,
                    device_id=None,
                    allocations=[
                        dict(
                            device_id=device["id"],
                            quantity=device["quantity"],
                            evidence="隔离人工分配",
                        )
                    ],
                ),
            )
        ],
    )
    draft = apply(client, draft, plan(client, draft))
    assert read(client, draft)["configuration"]["devices"][0]["source_id"] == device["source_id"]
    draft = write(
        client,
        draft,
        [
            dict(
                action="price_set",
                value=dict(
                    device_id=device["id"],
                    variant_id=device["variant_id"],
                    source_id=device["source_id"],
                    mode="manual",
                    unit_price="20",
                    evidence="隔离单价修改不能消除来源冲突",
                ),
            )
        ],
    )
    checked = read(client, draft)["checked"]
    assert any(
        c["kind"] == "product_constraint" and c["status"] == "conflict" for c in checked["checks"]
    ), checked["readiness"]
    assert not checked["readiness"]["ready_for_confirmation"]
    url = "/api/configuration/projects/" + project["id"]
    saved = client.put(url, json=dict(expected_revision=0, configuration=checked["configuration"]))
    assert saved.status_code == 200, saved.text
    response = client.post(
        url + "/confirm",
        json=dict(
            expected_revision=1,
            fingerprint=saved.json()["fingerprint"],
            **AUTHOR,
        ),
    )
    assert response.status_code == 422
    generation["preferences"][0]["source_id"] = device["source_id"]
    draft = write(client, draft, [dict(action="requirements_patch", generation=generation)])
    assert not any(
        c["kind"] == "product_constraint" for c in read(client, draft)["checked"]["checks"]
    )


@pytest.mark.parametrize("existing", ["new", "automatic", "manual"])
@pytest.mark.parametrize("scope", ["device", "system"])
def test_fulfilled_role_resolves_all_parent_demands(client, catalog, existing, scope):
    definition, package = published(client, catalog, accessory=True)
    # Separate device-scoped accessory demands need distinct servers.
    rule = next(
        r for r in client.get("/api/configuration/knowledge").json() if r["kind"] == "accessory"
    )
    payload = editable(KnowledgeInput, rule)
    payload["calculation_scope"] = scope
    response = client.put(
        "/api/configuration/knowledge/" + rule["id"],
        json=dict(expected_revision=rule["revision"], payload=payload),
    )
    assert response.status_code == 200, response.text
    rule = response.json()
    payload = editable(KnowledgePackage, package)
    payload["members"] = [
        dict(m, revision=rule["revision"]) if m["id"] == rule["id"] else m
        for m in payload["members"]
    ]
    response = client.put(
        "/api/configuration/knowledge-packages/" + package["id"],
        json=dict(expected_revision=package["revision"], payload=payload),
    )
    assert response.status_code == 200, response.text
    draft = draft_for(client, definition, response.json())
    original_alias = None
    if existing != "new":
        draft = apply(client, draft, plan(client, draft))
        original_alias = next(
            r
            for r in read(client, draft)["configuration"]["requirements"]
            if r["role_id"] == "server"
        )
        assert original_alias["device_id"] is not None
        if existing == "manual":
            original_alias = dict(
                original_alias,
                device_id=None,
                allocations=[
                    dict(
                        device_id=original_alias["device_id"],
                        quantity="1",
                        evidence="隔离人工关联",
                    )
                ],
            )
            draft = write(client, draft, [dict(action="requirement_put", value=original_alias)])
    data = read(client, draft)["configuration"]
    terminal = next(r for r in data["requirements"] if r["role_id"] == "terminal")
    draft = write(
        client,
        draft,
        [
            dict(
                action="requirement_put",
                value=dict(terminal, id="second-terminal", device_id=None, allocations=[]),
            )
        ],
    )
    proposal = plan(client, draft)
    draft = apply(client, draft, proposal)
    actual = read(client, draft)["configuration"]
    servers = {a["device_id"] for a in actual["accessory_allocations"]}
    assert len(servers) == (2 if scope == "device" else 1)
    alias = next(r for r in actual["requirements"] if r["role_id"] == "server")
    if existing == "manual":
        assert alias == original_alias
    elif scope == "system":
        assert alias["device_id"] in servers
    else:
        assert alias["device_id"] is None, "Ambiguous parent demands silently chose one server"
        if existing != "manual":
            assert {allocation["device_id"] for allocation in alias["allocations"]} == servers
            assert read(client, draft)["checked"]["readiness"]["ready_for_confirmation"]
    questions = client.post(
        "/api/list-tools/list_get",
        json=dict(
            draft_id=draft["id"],
            proposal_id=proposal["proposal_id"],
            option_id=proposal["option"]["id"],
            view="proposal_questions",
        ),
    ).json()
    codes = {question["code"] for question in questions["items"]}
    assert "role_fulfillment_missing" not in codes
    assert ("manual_fulfillment_conflict" in codes) == (
        scope == "device" and existing == "manual"
    )


def test_explicit_source_selects_its_candidate_instead_of_aborting_search(client, catalog):
    draft = priced(client, catalog, amount="10")
    data = read(client, draft)["configuration"]
    source = catalog["sources"][1]["id"]
    generation = dict(
        data["generation"],
        preferences=[
            dict(
                requirement_id=data["requirements"][0]["id"],
                source_id=source,
                evidence="隔离明确第二候选的资料来源",
            )
        ],
    )
    draft = write(client, draft, [dict(action="requirements_patch", generation=generation)])
    proposal = plan(client, draft)
    assert not read(client, draft)["configuration"]["devices"]
    draft = apply(client, draft, proposal)
    device = read(client, draft)["configuration"]["devices"][0]
    assert device["variant_id"] == catalog["variants"][1]["id"]
    assert device["source_id"] == source
