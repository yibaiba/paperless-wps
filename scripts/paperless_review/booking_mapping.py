"""Explicit, source-checked booking role mapping; no new compatibility conclusions."""

from copy import deepcopy
from dataclasses import dataclass

from presales.configuration.common import Entities, view
from presales.configuration.definitions.schemas import KnowledgePackage
from presales.configuration.definitions.service import Definitions
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.configuration.models import SourceLink
from presales.rules.calculation import digest
from presales.storage import ProductRecord

from .maintenance import proposal

ACTOR = "会议预约关联复核（2026-10-04）"
MARKER = "booking-role-mapping-20261004"
SYSTEM = "会议预约与信息发布系统"
NOTE = "仅将现有服务端软件适用关系关联到会议预约系统角色；环境、数量、容量和共享结论不变。"


@dataclass(frozen=True)
class MappingSelection:
    rule_id: str
    package_id: str
    source_id: str
    role_id: str = "server-software"


BUSINESS_SELECTION = MappingSelection(
    rule_id="507264c1-b7cd-4074-a8af-1928b458c09b",
    package_id="28b513aa-c06b-448d-aedd-afc5090f0733",
    source_id="facc338e-f3f8-4de3-b8a2-a696f7292cb0",
)


def mapping_payload(rule, *, definition, selection):
    data = {k: deepcopy(v) for k, v in rule.items() if k in KnowledgeInput.model_fields}
    if (data.get("identity_mapping") or {}).get("batch") == MARKER:
        return data
    role = next((r for r in definition["roles"] if r["id"] == selection.role_id), None)
    if definition["name"] != SYSTEM or not role or role["name"] != "服务端软件":
        raise ValueError("所选固定系统定义不是已核对的会议预约服务端软件角色")
    if data["kind"] != "suitability" or data["system"] not in ("会议预约", SYSTEM):
        raise ValueError("关系已不属于本次核对的会议预约适用范围")
    if data["role"] != role["name"]:
        raise ValueError("原关系角色与目标角色不一致，请重新核对")
    for key, value in (("system_definition_id", definition["id"]), ("role_id", role["id"])):
        if data.get(key) and data[key] != value:
            raise ValueError("原关系已有其他明确映射，未覆盖：" + key)
        data[key] = value
    data.update(
        actor=ACTOR,
        evidence=data["evidence"] + "\n" + NOTE,
        identity_mapping=dict(actor=ACTOR, evidence=NOTE, batch=MARKER),
    )
    return KnowledgeInput.model_validate(data).model_dump(mode="json")


def validate_source(session, selection, *, rule):
    source = session.get(ProductRecord, selection.source_id)
    link = session.get(SourceLink, selection.source_id)
    if source is None or link is None:
        raise ValueError("所选原文来源或配置归属不存在")
    if (
        source.sheet != "会议预约与信发系统"
        or source.payload.get("row") != 18
        or source.model != "CRIR-GL20S"
        or rule["selector"]["variant_ids"] != [link.variant_id]
        or rule["selector"].get("exclude_variant_ids")
    ):
        raise ValueError("所选关系与会议预约第18行具体配置不一致，请重新核对")
    if not any(r.get("source_id") == source.id for r in rule.get("evidence_refs", [])):
        raise ValueError("关系尚未明确引用所选来源，先核对原文引用")
    return source


def build_mapping_plan(session, selection=BUSINESS_SELECTION):
    entities = Entities(session)
    rule_record = entities.get(selection.rule_id, kind="knowledge")
    package_record = entities.get(selection.package_id, kind="knowledge_package")
    current = {
        r.id: dict(kind=r.kind, revision=r.revision, payload=deepcopy(r.payload))
        for r in (rule_record, package_record)
    }
    rule, package = view(rule_record), view(package_record)
    source = validate_source(session, selection, rule=rule)
    definition = Definitions(session).revision(
        package["system_definition_id"], package["definition_revision"], kind="system_definition"
    )
    payload = mapping_payload(rule, definition=definition, selection=selection)
    changes = [proposal(current, kind="knowledge", identity=rule["id"], payload=payload)]
    # Replay never adopts unrelated newer revisions or overwrites later package edits.
    if (payload.get("identity_mapping") or {}).get("batch") == MARKER and changes[0]["changed"]:
        changes.append(package_change(current, package, change=changes[0]))
    return dict(
        changes=changes,
        fingerprint=digest(changes),
        source_guards={source.id: digest(source.payload)},
    )


def package_change(current, package, *, change):
    if package["status"] != "draft":
        raise ValueError("本批只维护草稿资料包；已发布资料请使用独立升级预览")
    if change["id"] not in {m["id"] for m in package["members"]}:
        raise ValueError("所选关系不在原资料包内，未自动新增成员")
    payload = {k: deepcopy(v) for k, v in package.items() if k in KnowledgePackage.model_fields}
    payload["members"] = [
        dict(m, revision=change["result_revision"]) if m["id"] == change["id"] else m
        for m in payload["members"]
    ]
    payload.update(actor=ACTOR, evidence=payload["evidence"] + "\n" + NOTE)
    return proposal(
        current,
        kind="knowledge_package",
        identity=package["id"],
        payload=KnowledgePackage.model_validate(payload).model_dump(mode="json"),
    )
