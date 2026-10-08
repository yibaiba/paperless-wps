from sqlalchemy import select

from presales.configuration.models import Entity

from .definition_snapshot import definition_version_changes


def configuration_version_changes(session, entities, payload):
    used = {item["id"]: item["revision"] for item in payload["knowledge_snapshot"]}
    current = {item["id"]: item["revision"] for item in entities.list("knowledge")}
    changes = [
        dict(kind="knowledge", id=key, used=used.get(key), current=revision)
        for key, revision in current.items()
        if used.get(key) != revision
    ]
    if payload.get("calculation_version", 1) < 3:
        changes.append(
            dict(
                kind="calculation",
                id="project",
                used=payload.get("calculation_version", 1),
                current=3,
            )
        )
    if payload.get("decision_runtime", "python-v3") != "zen-v1":
        changes.append(
            dict(kind="decision_runtime", id="project", used="python-v3", current="zen-v1")
        )
    return changes + product_version_changes(session, payload) + definition_version_changes(
        session, payload
    )


def product_version_changes(session, payload):
    ids = {
        item["id"]
        for device in payload["devices"]
        for item in (device["variant_snapshot"], device["variant_snapshot"]["product"])
    }
    latest_records = {
        record.id: record for record in session.scalars(select(Entity).where(Entity.id.in_(ids)))
    }
    changes = []
    for device in payload["devices"]:
        snapshot = device["variant_snapshot"]
        for kind, old in (("variant", snapshot), ("product", snapshot["product"])):
            latest = latest_records.get(old["id"])
            if latest is None or latest.kind != kind:
                raise ValueError("所用产品或配置已不存在")
            if latest.revision != old["revision"]:
                changes.append(
                    dict(
                        kind=kind,
                        id=old["id"],
                        device_id=device["id"],
                        used=old["revision"],
                        current=latest.revision,
                    )
                )
    return changes
