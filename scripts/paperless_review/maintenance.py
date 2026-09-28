"""Versioned, transactional maintenance using the existing domain validation."""

from uuid import NAMESPACE_URL, uuid5

from presales.configuration.common import Entities
from presales.configuration.definitions.schemas import (
    KnowledgePackage,
    SystemDefinition,
)
from presales.configuration.definitions.service import Definitions
from presales.configuration.knowledge.routes import validate_knowledge
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.configuration.models import Entity
from presales.rules.calculation import digest
from presales.rules.repository import RuleConflict


def stable_id(key):
    return str(uuid5(NAMESPACE_URL, "presales:paperless-review-20260928:" + key))


def comparable(kind, payload):
    # Snapshots are produced by Definitions, not editable input fields.
    derived = {
        "knowledge_package": {"definition", "rules"},
        "system_definition": {"inspection_profiles"},
    }.get(kind, set())
    return {k: v for k, v in payload.items() if k not in derived}


def proposal(current, *, kind, identity, payload):
    old = current.get(identity)
    if old and old["kind"] != kind:
        raise ValueError("标识已被其他类型占用：" + identity)
    before = old["payload"] if old else None
    changed = before is None or comparable(kind, before) != payload
    revision = old["revision"] if old else 0
    return dict(
        id=identity,
        kind=kind,
        expected_revision=revision,
        before=before,
        payload=payload,
        changed=changed,
        result_revision=revision + int(changed),
    )


def apply_plan(session, plan):
    if digest(plan["changes"]) != plan["fingerprint"]:
        raise ValueError("维护预览内容已变化，请重新生成预览")
    entities = Entities(session)
    pending = []
    for item in sorted(plan["changes"], key=lambda value: value["id"]):
        record = session.get(Entity, item["id"])
        if record:
            record = entities.get(item["id"], kind=item["kind"], lock=True)
        if record and comparable(item["kind"], record.payload) == item["payload"]:
            continue
        if (record.revision if record else 0) != item["expected_revision"]:
            raise RuleConflict("维护预览版本过期：" + item["id"])
        if (record.payload if record else None) != item["before"]:
            raise RuleConflict("维护预览内容过期：" + item["id"])
        pending.append(item["id"])
    # Definitions first, then knowledge, then packages referencing the exact new revisions.
    return [save_change(session, item) for item in plan["changes"] if item["id"] in pending]


def save_change(session, item):
    options = (
        dict(entity_id=item["id"], expected_revision=item["expected_revision"])
        if item["expected_revision"]
        else dict(create_id=item["id"])
    )
    if item["kind"] == "system_definition":
        return Definitions(session).save_definition(
            SystemDefinition.model_validate(item["payload"]), **options
        )
    if item["kind"] == "knowledge_package":
        return Definitions(session).save_package(
            KnowledgePackage.model_validate(item["payload"]), **options
        )
    data = KnowledgeInput.model_validate(item["payload"])
    validate_knowledge(session, data)
    return Entities(session).save("knowledge", data, **options)
