from io import BytesIO
from zipfile import ZipFile

import pytest

from presales.configuration.definitions.schemas import KnowledgePackage
from presales.configuration.knowledge.schemas import KnowledgeInput

from .conftest import AUTHOR, post
from .test_evolution_versions import editable
from .test_proposal_generation import apply, draft_for, plan, published, read, write


def add_source_copy(client, catalog, workbook):
    stream = BytesIO(workbook)
    with ZipFile(stream, "a") as archive:
        archive.comment = b"Isolated manual source review"
    imported = client.post("/api/imports", files={"file": ("copy.xlsx", stream.getvalue())}).json()
    rows = client.get("/api/products", params={"import_id": imported["id"]}).json()
    sources = [client.get("/api/products/" + row["id"]).json() for row in rows]
    for variant, original in zip(catalog["variants"], catalog["sources"], strict=True):
        source = next(s for s in sources if s["specification"] == original["specification"])
        post(
            client,
            "/source-links",
            dict(
                variant_id=variant["id"],
                items=[dict(source_id=source["id"], expected_revision=0)],
                **AUTHOR,
            ),
        )


@pytest.mark.parametrize("role_id", ["terminal", "server"])
def test_manual_source_survives_regeneration_reopen_and_undo(
    client, catalog, workbook, project, role_id
):
    add_source_copy(client, catalog, workbook)
    definition, package = published(client, catalog, accessory=role_id == "server")
    draft = draft_for(client, definition, package)
    draft = apply(client, draft, plan(client, draft))
    data = read(client, draft)["configuration"]
    requirement = next(r for r in data["requirements"] if r["role_id"] == role_id)
    device = next(d for d in data["devices"] if d["id"] == requirement["device_id"])
    checkpoint = draft["revision"]
    alternate = next(
        s for s in device["variant_snapshot"]["source_ids"] if s != device["source_id"]
    )
    replacement = {k: device[k] for k in ["id", "name", "variant_id", "quantity", "kind", "note"]}
    replacement["source_id"] = alternate
    operation = dict(action="device_put", value=replacement)
    preview = client.post(
        "/api/work-drafts/" + draft["id"] + "/preview",
        json=dict(
            expected_revision=draft["revision"],
            draft_version=1,
            operations=[operation],
        ),
    )
    assert preview.status_code == 200, preview.text
    draft = write(client, draft, [operation])
    edited = next(
        d for d in read(client, draft)["configuration"]["devices"] if d["id"] == device["id"]
    )
    delta = preview.json()["configuration_patch"]["device_changes"][0]
    assert all(edited[key] == value for key, value in delta.items())
    draft = apply(client, draft, plan(client, draft))
    actual = read(client, draft)["configuration"]
    selected = next(d for d in actual["devices"] if d["id"] == device["id"])
    assert selected["source_id"] == alternate
    assert selected["generated_origin"]["variant_locked"]
    assert not selected["generated_origin"]["quantity_locked"]
    saved = client.put(
        "/api/configuration/projects/" + project["id"],
        json=dict(
            expected_revision=0,
            configuration=actual,
        ),
    )
    assert saved.status_code == 200, saved.text
    from .test_proposal_generation import call

    reopened = call(
        client,
        "list_create",
        dict(
            project_id=project["id"],
            revision=1,
            name="隔离重开来源",
            operation_id="source-reopen",
            **AUTHOR,
        ),
    )
    reopened = apply(client, reopened, plan(client, reopened))
    assert (
        next(
            d for d in read(client, reopened)["configuration"]["devices"] if d["id"] == device["id"]
        )["source_id"]
        == alternate
    )
    restored = client.post(
        "/api/work-drafts/" + draft["id"] + "/restore",
        json=dict(
            draft_id=draft["id"],
            expected_revision=draft["revision"],
            checkpoint_revision=checkpoint,
            operation_id="source-undo",
        ),
    )
    assert restored.status_code == 200, restored.text
    original = next(
        d for d in restored.json()["configuration"]["devices"] if d["id"] == device["id"]
    )
    assert original["source_id"] == device["source_id"]
    assert not original["generated_origin"]["variant_locked"]


def test_role_reuse_permission_does_not_extend_to_another_accessory_need(client, catalog):
    definition, package = published(client, catalog, accessory=True)
    rule = next(
        r for r in client.get("/api/configuration/knowledge").json() if r["kind"] == "accessory"
    )
    payload = editable(KnowledgeInput, rule)
    payload.update(name="隔离另一台控制主机", need_key="control", need_name="控制主机")
    extra = post(client, "/knowledge", payload)
    payload = editable(KnowledgePackage, package)
    payload["members"].append(dict(id=extra["id"], revision=extra["revision"]))
    response = client.put(
        "/api/configuration/knowledge-packages/" + package["id"],
        json=dict(
            expected_revision=package["revision"],
            payload=payload,
        ),
    )
    assert response.status_code == 200, response.text
    draft = draft_for(client, definition, response.json())
    data = read(client, draft)["configuration"]
    role = next(r for r in data["requirements"] if r["role_id"] == "server")
    existing = dict(
        id="existing-server",
        name="隔离客户已有服务端主机",
        quantity="1",
        kind="hardware",
        variant_id=catalog["variants"][1]["id"],
        source_id=catalog["sources"][1]["id"],
    )
    draft = write(
        client,
        draft,
        [
            dict(action="device_put", value=existing),
            dict(
                action="supply_set",
                device_id=existing["id"],
                allocations=[
                    dict(
                        id="existing-supply",
                        device_id=existing["id"],
                        quantity="1",
                        source="existing",
                        evidence="客户确认服务器可以复用",
                    )
                ],
            ),
            dict(
                action="requirements_patch",
                generation=dict(
                    data["generation"],
                    preferences=[
                        dict(
                            requirement_id=role["id"],
                            reusable_device_ids=[existing["id"]],
                            evidence="仅服务器角色允许复用，不允许控制主机使用",
                        )
                    ],
                ),
            ),
        ],
    )
    draft = apply(client, draft, plan(client, draft))
    result = read(client, draft)
    server_need = next(s for s in result["checked"]["suggestions"] if s["need_key"] == "server")
    control_need = next(s for s in result["checked"]["suggestions"] if s["need_key"] == "control")
    allocations = result["configuration"]["accessory_allocations"]
    assert (
        next(a for a in allocations if a["demand_id"] == server_need["id"])["device_id"]
        == existing["id"]
    )
    assert (
        next(a for a in allocations if a["demand_id"] == control_need["id"])["device_id"]
        != existing["id"]
    )
    control_id = next(a for a in allocations if a["demand_id"] == control_need["id"])["device_id"]
    supplies = result["configuration"]["supply_allocations"]
    assert next(a for a in supplies if a["device_id"] == control_id)["source"] == "purchase"
    assert next(a for a in supplies if a["device_id"] == existing["id"])["source"] == "existing"
    assert next(a for a in supplies if a["device_id"] == control_id)["quantity"] == "1"


def test_note_edit_does_not_lock_automatic_selection(client, catalog):
    definition, package = published(client, catalog)
    draft = draft_for(client, definition, package)
    draft = apply(client, draft, plan(client, draft))
    device = read(client, draft)["configuration"]["devices"][0]
    replacement = {
        k: device[k] for k in ["id", "name", "variant_id", "source_id", "quantity", "kind"]
    }
    replacement["note"] = "隔离仅补充备注"
    draft = write(client, draft, [dict(action="device_put", value=replacement)])
    from .test_proposal_evolution import change_seats

    draft = change_seats(client, draft, "48")
    draft = apply(client, draft, plan(client, draft))
    current = read(client, draft)["configuration"]["devices"][0]
    assert current["quantity"] == "48"
    assert current["note"] == replacement["note"]
    assert not current["generated_origin"]["variant_locked"]
