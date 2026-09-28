from presales.configuration.common import Entities

from .test_list_mcp import call, create, device_operations, mutation


def test_draft_catalog_fixed_before_selection_and_refresh_is_explicit(client, catalog):
    draft = create(client)
    variant = catalog["variants"][0]
    with client.app.state.session_factory() as session:
        entities = Entities(session)
        old = entities.get(variant["id"], kind="variant")
        entities.save(
            "variant",
            dict(old.payload, name="新资料名称"),
            entity_id=old.id,
            expected_revision=old.revision,
        )
        session.commit()
    detail = call(client, "catalog_get", dict(variant_id=variant["id"], draft_id=draft["id"]))
    assert detail["variant"]["revision"] == 1
    assert call(client, "catalog_get", dict(variant_id=variant["id"]))["variant"]["revision"] == 2
    edited = call(client, "list_update", mutation(draft, operations=device_operations(catalog)))
    detail = call(client, "catalog_get", dict(variant_id=variant["id"], draft_id=draft["id"]))
    assert detail["variant"]["revision"] == 1
    checked = call(client, "list_check", mutation(edited, refresh_knowledge=True))
    assert checked["catalog_snapshot_id"] != draft["catalog_snapshot_id"]
    detail = call(client, "catalog_get", dict(variant_id=variant["id"], draft_id=draft["id"]))
    assert detail["variant"]["revision"] == 2
    changes = call(client, "list_get", dict(draft_id=draft["id"], view="changes"))
    assert any(c["kind"] == "devices" for c in changes["items"])


def test_accessory_apply_requires_current_explicit_check(client, catalog):
    draft = call(
        client, "list_update", mutation(create(client), operations=device_operations(catalog))
    )
    response = client.post(
        "/api/list-tools/list_update",
        json=mutation(
            draft,
            operations=[
                {
                    "action": "accessory_apply",
                    "suggestion_id": "obsolete",
                    "fingerprint": draft["calculation_fingerprint"],
                    "existing_device_id": "server",
                }
            ],
        ),
    )
    assert response.status_code == 409 and "CHECK_STALE" in response.text
