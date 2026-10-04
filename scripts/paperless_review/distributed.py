"""A narrow, repeatable review batch; source rows and published history remain intact."""

from copy import deepcopy

from presales.configuration.catalog.service import CatalogService
from presales.configuration.definitions.schemas import KnowledgePackage, SystemDefinition
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.rules.calculation import digest
from presales.storage import ProductRecord

from .content import ReviewSources
from .distributed_specs import ACTOR, BY_NAME, DISTRIBUTED, MARKER, NOTICE, annotate, draft_quantity
from .maintenance import proposal, stable_id
from .reconciliation import current_records, evidence_source_ids


def definition_payload(original, sources):
    data = {k: deepcopy(v) for k, v in original.items() if k in SystemDefinition.model_fields}
    if MARKER in data["evidence"]:
        return SystemDefinition.model_validate(data).model_dump(mode="json")
    if data["status"] != "draft":
        raise ValueError("当前定义已确认，请通过资料升级核对本批角色变化")
    for role in data["roles"]:
        spec = BY_NAME.get(role["name"])
        if spec is None:
            continue
        references = [sources.evidence(DISTRIBUTED, spec.row)] if spec.row else []
        if role["feature"] and role["feature"] != spec.feature:
            raise ValueError("角色已有不同功能分支，请核对：" + role["name"])
        role.update(feature=spec.feature, output_kind=spec.kind)
        if role.get("quantity_basis") is None:
            role["quantity_basis"] = draft_quantity(spec, references)
    data.update(actor=ACTOR, evidence=annotate(data["evidence"], NOTICE))
    return SystemDefinition.model_validate(data).model_dump(mode="json")


def rule_payload(original, *, definition):
    data = {k: deepcopy(v) for k, v in original.items() if k in KnowledgeInput.model_fields}
    if MARKER in data["evidence"]:
        return KnowledgeInput.model_validate(data).model_dump(mode="json")
    roles = {r["name"]: r for r in definition["roles"]}
    # Map existing text semantics explicitly; do not infer IDs from product model names.
    if data.get("system") == DISTRIBUTED and data.get("role") in roles:
        role = roles[data["role"]]
        for key, value in (("system_definition_id", definition["id"]), ("role_id", role["id"])):
            if data.get(key) and data[key] != value:
                raise ValueError("已有关系标识与文字映射冲突：" + data["name"])
            data[key] = value
    key = data.get("need_key", "")
    spec = ACCESSORY_INPUTS.get(key)
    if spec and data.get("quantity_review") != "confirmed":
        data.update(
            quantity_source="environment",
            quantity_key=spec.input_key,
            calculation_scope="system",
            mode=None,
            factor=None,
        )
    data.update(actor=ACTOR, evidence=annotate(data["evidence"], NOTICE))
    return KnowledgeInput.model_validate(data).model_dump(mode="json")


ACCESSORY_INPUTS = {
    "distributed-paperless.management-software": BY_NAME["服务端软件"],
    "distributed-paperless.server-hardware": BY_NAME["服务端"],
    "distributed-paperless.tablet-hardware": BY_NAME["会议平板"],
    "distributed-paperless.info-display-software": BY_NAME["信息发布软件"],
    "distributed-paperless.service-terminal-software": BY_NAME["会议服务软件"],
    "distributed-paperless.video-input": BY_NAME["信号输入控制器"],
    "distributed-paperless.video-output": BY_NAME["信号输出控制器"],
}


def broadcast_needs(definition, sources):
    variant, _ = sources.get(DISTRIBUTED, 65)
    evidence = sources.evidence(DISTRIBUTED, 65, quote="必搭配显示和扩声设备使用")
    role = next(r for r in definition["roles"] if r["name"] == "候会语音播报终端")
    return [
        KnowledgeInput.model_validate(
            dict(
                schema_version=2,
                name="候会播报 · " + label + "配套（型号数量待核对）",
                kind="accessory",
                status="confirmed",
                selector=dict(variant_ids=[variant]),
                system=DISTRIBUTED,
                system_definition_id=definition["id"],
                role=role["name"],
                role_id=role["id"],
                need_key="distributed-paperless.broadcast-" + key,
                need_name=label,
                target_variant_ids=[],
                mode=None,
                factor=None,
                calculation_scope=None,
                output_kind="hardware",
                actor=ACTOR,
                evidence="原文明确需要此类配套；型号、数量和已有设备复用仍待确认。",
                evidence_refs=[evidence],
            )
        ).model_dump(mode="json")
        for key, label in (("display", "显示设备"), ("audio", "扩声设备"))
    ]


def build_distributed_plan(session):
    current = current_records(session)
    sources = ReviewSources(CatalogService(session).variants())
    definitions = [
        (i, r)
        for i, r in current.items()
        if r["kind"] == "system_definition" and r["payload"]["name"] == DISTRIBUTED
    ]
    if len(definitions) != 1:
        raise ValueError("分布式 2.0 系统定义不唯一")
    identity, record = definitions[0]
    payload = definition_payload(record["payload"], sources)
    changes = [proposal(current, kind="system_definition", identity=identity, payload=payload)]
    definition = dict(id=identity, **payload)
    for rule_id, record in current.items():
        rule = record["payload"]
        if record["kind"] != "knowledge" or not (
            rule.get("system") == DISTRIBUTED
            or rule.get("system_definition_id") == identity
            or rule.get("need_key", "").startswith("distributed-paperless.")
        ):
            continue
        if rule.get("need_key", "").startswith("distributed-paperless.broadcast-"):
            continue
        updated = rule_payload(rule, definition=definition)
        changes.append(proposal(current, kind="knowledge", identity=rule_id, payload=updated))
    for rule in broadcast_needs(definition, sources):
        key = stable_id(rule["need_key"])
        # A later maintainer change must survive re-running this one-time source batch.
        payload = current[key]["payload"] if key in current else rule
        changes.append(proposal(current, kind="knowledge", identity=key, payload=payload))
    changes.extend(package_changes(current, changes, definition_id=identity))
    source_ids = {i for c in changes for i in evidence_source_ids(c["payload"])}
    return dict(
        changes=changes,
        fingerprint=digest(changes),
        source_guards={i: digest(session.get(ProductRecord, i).payload) for i in source_ids},
    )


def package_changes(current, changes, *, definition_id):
    result = []
    definition = changes[0]
    for identity, record in current.items():
        original = record["payload"]
        if (
            record["kind"] != "knowledge_package"
            or original.get("system_definition_id") != definition_id
        ):
            continue
        if original["status"] != "draft":
            continue  # Fixed published packages are never changed by this draft maintenance.
        payload = {
            k: deepcopy(v) for k, v in original.items() if k in KnowledgePackage.model_fields
        }
        members = {m["id"]: m for m in payload["members"]}
        members.update(
            {
                c["id"]: dict(id=c["id"], revision=c["result_revision"])
                for c in changes
                if c["kind"] == "knowledge"
            }
        )
        payload.update(
            definition_revision=definition["result_revision"],
            members=list(members.values()),
            actor=ACTOR,
            evidence=annotate(payload["evidence"], NOTICE),
        )
        result.append(
            proposal(
                current,
                kind="knowledge_package",
                identity=identity,
                payload=KnowledgePackage.model_validate(payload).model_dump(mode="json"),
            )
        )
    return result
