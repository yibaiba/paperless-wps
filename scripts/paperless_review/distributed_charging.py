"""Wire documented per-cart capacities into the existing, pinned inspection service."""

from copy import deepcopy

from presales.configuration.catalog.service import CatalogService
from presales.configuration.definitions.inspection_schemas import InspectionProfile
from presales.configuration.definitions.schemas import SystemDefinition
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.rules.calculation import digest
from presales.storage import ProductRecord

from .content import ReviewSources
from .distributed import package_changes
from .distributed_sources import checked_source
from .facts import CARTS, extracted, fact_rows
from .maintenance import proposal, stable_id
from .reconciliation import MODELS, current_records, evidence_source_ids
from .specs import DISTRIBUTED, THIRD_PARTY

ACTOR = "分布式充电容量复核（2026-10-04）"
MARKER = "【分布式集中充电核对20261004】"
PROFILE_ID = stable_id("distributed-paperless.charging-capacity-inspection")
INPUT_KEY = "simultaneous_charging_count"
ROLE = "充电设备"
NOTICE = (
    "只比较明确同时充电台数与所选设备单台容量乘部署数量，不用总席位代替同时充电需求。"
    "容量通过不确认平板尺寸、接口、充电功率或USB线已包含；不自动采购或推算轮换充电。"
)


def checked_carts(sources, variants):
    references, ids = [], []
    for row in CARTS:
        identity, source = checked_source(
            sources, variants, sheet=THIRD_PARTY, row=row, model=MODELS[row]
        )
        attribute, reference = extracted(source, fact_rows()[row][0])
        current = next(
            (a for a in variants[identity]["attributes"] if a["key"] == "charging_capacity"), None
        )
        if current != attribute:
            raise ValueError(f"充电容量与来源不一致，请先核对配置：{MODELS[row]}")
        references.append(reference)
        ids.append(identity)
    return ids, references


def charging_profile(references):
    return InspectionProfile(
        name="分布式集中充电 · 同时充电台数检查",
        status="confirmed",
        selected_device_policy="required",
        metrics=[
            dict(
                key="charging_capacity",
                label="同时充电台数",
                input_key=INPUT_KEY,
                input_label="需要同时充电的终端数量",
                input_unit="台",
                unit="台",
                aggregation="sum",
                capacity_basis="unit",
                factor="1",
            )
        ],
        actor=ACTOR,
        evidence=MARKER
        + NOTICE
        + "\n"
        + "\n".join(f"{r['locator']}；来源ID {r['source_id']}：{r['quote']}" for r in references),
    ).model_dump(mode="json")


def charging_definition(original, profile):
    data = SystemDefinition.model_validate(
        {k: deepcopy(v) for k, v in original.items() if k in SystemDefinition.model_fields}
    ).model_dump(mode="json")
    if MARKER in data["evidence"]:
        return data
    if data["status"] != "draft":
        raise ValueError("系统定义已确认，请显式预览新资料版本")
    roles = [r for r in data["roles"] if r["name"] == ROLE]
    if len(roles) != 1 or roles[0]["inspection_profile"] is not None:
        raise ValueError("充电角色或已有用途检查需人工核对")
    roles[0]["inspection_profile"] = dict(id=profile["id"], revision=profile["result_revision"])
    data.update(actor=ACTOR, evidence=data["evidence"] + "\n" + MARKER + NOTICE)
    return data


def charging_candidates(original, *, ids, references):
    data = KnowledgeInput.model_validate(original).model_dump(mode="json")
    if MARKER in data["evidence"]:
        return data
    if data["status"] != "draft" or data["selector"]["variant_ids"] != [ids[2]]:
        raise ValueError("原充电候选范围或结论已变化，请先核对差异")
    # Widen only this role's draft list. Capacity is independent of compatibility.
    data["selector"]["variant_ids"] = ids
    data.update(
        name="分布式集中充电 · 五款容量候选（兼容待核对）",
        actor=ACTOR,
        evidence=data["evidence"] + "\n" + MARKER + NOTICE,
        evidence_refs=list({digest(r): r for r in [*data["evidence_refs"], *references]}.values()),
    )
    return KnowledgeInput.model_validate(data).model_dump(mode="json")


def build_charging_plan(session):
    current = current_records(session)
    variants = {v["id"]: v for v in CatalogService(session).variants()}
    sources = ReviewSources(variants.values())
    ids, references = checked_carts(sources, variants)
    definitions = [
        (i, r)
        for i, r in current.items()
        if r["kind"] == "system_definition" and r["payload"]["name"] == DISTRIBUTED
    ]
    if len(definitions) != 1:
        raise ValueError("分布式系统定义应唯一")
    identity, record = definitions[0]
    profile = proposal(
        current,
        kind="inspection_profile",
        identity=PROFILE_ID,
        payload=deepcopy(current[PROFILE_ID]["payload"])
        if PROFILE_ID in current
        else charging_profile(references),
    )
    definition = proposal(
        current,
        kind="system_definition",
        identity=identity,
        payload=charging_definition(record["payload"], profile),
    )
    rules = [
        (i, r)
        for i, r in current.items()
        if r["kind"] == "knowledge"
        and r["payload"]["kind"] == "suitability"
        and r["payload"].get("system_definition_id") == identity
        and r["payload"]["role"] == ROLE
    ]
    if len(rules) != 1:
        raise ValueError("充电候选维护关系不唯一")
    rule_id, rule = rules[0]
    changes = [
        definition,
        profile,
        proposal(
            current,
            kind="knowledge",
            identity=rule_id,
            payload=charging_candidates(rule["payload"], ids=ids, references=references),
        ),
    ]
    changes.extend(
        proposal(current, kind="variant", identity=i, payload=deepcopy(current[i]["payload"]))
        for i in ids
    )
    changes.extend(package_changes(current, changes, definition_id=identity))
    protected = {r["source_id"] for r in references}
    protected.update(i for c in changes for i in evidence_source_ids(c["payload"]))
    return dict(
        changes=changes,
        fingerprint=digest(changes),
        source_guards={i: digest(session.get(ProductRecord, i).payload) for i in protected},
    )
