"""Versioned, transactional maintenance using the existing domain validation."""

from uuid import NAMESPACE_URL, uuid5

from presales.configuration.catalog.schemas import VariantInput
from presales.configuration.catalog.service import CatalogService
from presales.configuration.common import Entities
from presales.configuration.definitions.inspection_schemas import InspectionProfile
from presales.configuration.definitions.schemas import (
    KnowledgePackage,
    SystemDefinition,
)
from presales.configuration.definitions.service import Definitions
from presales.configuration.knowledge.routes import validate_knowledge
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.configuration.models import Entity, SourceLink
from presales.rules.calculation import digest
from presales.rules.repository import RuleConflict
from presales.storage import ProductRecord


def stable_id(key):
    return str(uuid5(NAMESPACE_URL, "presales:paperless-review-20260928:" + key))


def comparable(kind, payload):
    # Snapshots are produced by Definitions, not editable input fields.
    derived = {
        "knowledge_package": {"definition", "rules"},
        "system_definition": {"inspection_profiles"},
    }.get(kind, set())
    if kind == "variant":
        # The catalogue service records affected knowledge after a technical edit.
        payload = VariantInput.model_validate(payload).model_dump(mode="json")
        derived = {"review_requirements"}
    return {k: v for k, v in payload.items() if k not in derived}


def proposal(current, *, kind, identity, payload):
    old = current.get(identity)
    if old and old["kind"] != kind:
        raise ValueError("标识已被其他类型占用：" + identity)
    before = old["payload"] if old else None
    changed = before is None or comparable(kind, before) != comparable(kind, payload)
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
    for identity, fingerprint in plan.get("source_guards", {}).items():
        source = session.get(ProductRecord, identity)
        if source is None or digest(source.payload) != fingerprint:
            raise RuleConflict("维护依据已变化，请重新核对来源：" + identity)
    for identity, variant_id in sorted(plan.get("source_link_guards", {}).items()):
        link = session.get(SourceLink, identity, populate_existing=True, with_for_update=True)
        if link is None or link.variant_id != variant_id:
            raise RuleConflict("来源配置归属已变化，请重新核对：" + identity)
    entities = Entities(session)
    pending = []
    for item in sorted(plan["changes"], key=lambda value: value["id"]):
        record = session.get(Entity, item["id"])
        if record:
            record = entities.get(item["id"], kind=item["kind"], lock=True)
        if record and comparable(item["kind"], record.payload) == comparable(
            item["kind"], item["payload"]
        ):
            continue
        if (record.revision if record else 0) != item["expected_revision"]:
            raise RuleConflict("维护预览版本过期：" + item["id"])
        if (record.payload if record else None) != item["before"]:
            raise RuleConflict("维护预览内容过期：" + item["id"])
        pending.append(item["id"])
    # Profiles must exist before definitions pin them; retain the batch's remaining order.
    ordered = sorted(plan["changes"], key=lambda item: item["kind"] != "inspection_profile")
    return [save_change(session, item) for item in ordered if item["id"] in pending]


def save_change(session, item):
    options = (
        dict(entity_id=item["id"], expected_revision=item["expected_revision"])
        if item["expected_revision"]
        else dict(create_id=item["id"])
    )
    if item["kind"] == "inspection_profile":
        return Entities(session).save(
            "inspection_profile", InspectionProfile.model_validate(item["payload"]), **options
        )
    if item["kind"] == "variant":
        return CatalogService(session).save_variant(
            VariantInput.model_validate(item["payload"]), **options
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
