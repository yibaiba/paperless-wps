"""Evidence extraction and source-backed knowledge content for this review batch."""

from presales.configuration.knowledge.schemas import KnowledgeInput

from .specs import (
    ACTOR,
    CASE_NOTES,
    DISTRIBUTED,
    EXPLICIT_QUANTITIES,
    GAPS,
    MARKER,
    SAFE,
    SYSTEMS,
    THIRD_PARTY,
    UNVERIFIED_PAIRINGS,
)


class ReviewSources:
    def __init__(self, variants):
        self.entries = {}
        for variant in variants:
            for source in variant["source_details"]:
                self.entries.setdefault((source["sheet"], source["row"]), []).append(
                    (variant["id"], source)
                )

    def get(self, sheet, row):
        entries = self.entries.get((sheet, row), [])
        if len(entries) != 1:
            raise ValueError(f"来源应唯一且已关联配置：{sheet} 第{row}行，实际{len(entries)}条")
        return entries[0]

    def evidence(self, sheet, row, *, quote=None):
        _, source = self.get(sheet, row)
        fields = ("note", "specification", "short_specification", "tender_specification")
        field = next(
            (key for key in fields if source.get(key) and (quote is None or quote in source[key])),
            None,
        )
        if field is None:
            raise ValueError(f"来源未找到预期原文：{sheet} 第{row}行 {quote}")
        text = quote or source[field].splitlines()[0]
        return dict(source_id=source["id"], locator=f"{sheet}!第{row}行/{field}", quote=text)


def authored(evidence):
    return dict(actor=ACTOR, evidence=evidence)


def reviewed_suitability(rule, sources):
    data = {**rule, "actor": ACTOR}
    data["evidence"] = (
        rule["evidence"].split(MARKER)[0].rstrip() + "\n" + MARKER + CASE_NOTES[rule["system"]]
    )
    if rule["role"] == "客户端软件":
        included = sources.evidence(
            "红盾无纸化会议系统华为版本", 12, quote="内置RS-MSC100C红盾无纸化软件"
        )
        data["evidence_refs"] = [*rule.get("evidence_refs", []), included]
        # Deduplicate on subsequent previews while preserving prior source references.
        data["evidence_refs"] = list(
            {digest_ref(ref): ref for ref in data["evidence_refs"]}.values()
        )
        data["evidence"] += (
            "红盾华为版第12行C5-V1已内置RS-MSC100C；不能因C5别名匹配而替换为裸机，"
            "也不能据此抵扣20S/30S软件。此处仅记录产品差异，不作为跨版本兼容依据。"
        )
    return KnowledgeInput.model_validate(data).model_dump(mode="json")


def digest_ref(reference):
    return reference["source_id"], reference["locator"], reference["quote"]


def reviewed_accessory(rule, sources):
    key = rule["need_key"]
    data = {**rule, "schema_version": 2, "actor": ACTOR}
    if key in EXPLICIT_QUANTITIES:
        sheet, row, quote = EXPLICIT_QUANTITIES[key]
        reference = sources.evidence(sheet, row, quote=quote)
        data.update(quantity_review="confirmed", quantity_evidence=quote, evidence_refs=[reference])
        reason = "保留原有数量公式，仅确认原文明确的计量口径；不扩大适用范围。"
    else:
        data.update(quantity_review="unreviewed", quantity_evidence="", mode=None, factor=None)
        reason = "原资料未明确完整数量口径，旧公式保留在历史修订；当前不计算采购数量。"
        if key in UNVERIFIED_PAIRINGS:
            data["status"] = "draft"
            reason += "相邻硬件/软件行仅作为配套候选，必要性、兼容性、授权范围均待确认。"
        data["name"] = rule["name"].split(" · ")[0] + " · 配套及数量复核"
    evidence = rule["evidence"].split(MARKER)[0].rstrip()
    data["evidence"] = evidence + "\n" + MARKER + reason
    if key == "distributed-paperless.tablet-hardware":
        data["evidence_refs"] = [sources.evidence(DISTRIBUTED, 33)]
        data["evidence"] += (
            "西安32套软件、30台平板，已有终端/备用授权用途待确认，不能推定一套一台。"
        )
    if key.endswith(".server-hardware"):
        variant, _ = sources.get(THIRD_PARTY, 12)
        data["target_variant_ids"] = sorted(set([*data["target_variant_ids"], variant]))
        data["evidence_refs"] = [sources.evidence(THIRD_PARTY, 12)]
        data["evidence"] += GAPS["移动部署宿主"] + "仅加入待核对候选，不确认可替代原服务器。"
    if key == "distributed-paperless.management-software":
        variant, _ = sources.get(DISTRIBUTED, 33)
        data["selector"] = {
            **data["selector"],
            "variant_ids": sorted(set([*data["selector"]["variant_ids"], variant])),
        }
        data["evidence"] += "补充西安平板方案的管理软件需求，历史一套不作为通用数量依据。"
    return KnowledgeInput.model_validate(data).model_dump(mode="json")


def new_rule(name, *, system, source_id, evidence, **fields):
    return KnowledgeInput.model_validate(
        dict(
            name=name,
            kind="suitability",
            status="draft",
            schema_version=2,
            selector={"variant_ids": [source_id]},
            system=system,
            role="客户端软件",
            calculation_scope=None,
            mode=None,
            factor=None,
            **authored(evidence),
        )
        | fields
    ).model_dump(mode="json")


def additions(sources):
    rules = []
    for system in SYSTEMS:
        for row, role in ((12, "移动部署宿主"), (33, "充电设备")):
            variant, _ = sources.get(THIRD_PARTY, row)
            reference = sources.evidence(THIRD_PARTY, row)
            evidence = reference["locator"] + "：" + reference["quote"] + "；" + GAPS[role]
            rules.append(
                new_rule(
                    system + " · " + role + "候选待核对",
                    system=system,
                    source_id=variant,
                    evidence=evidence,
                    role=role,
                    evidence_refs=[reference],
                )
            )
    pb20, _ = sources.get(DISTRIBUTED, 33)
    for row, need, feature in (
        (24, "video-input", "外部视频输入"),
        (25, "video-output", "视频输出到大屏"),
    ):
        target, _ = sources.get(DISTRIBUTED, row)
        rules.append(
            new_rule(
                "分布式平板方案 · " + feature + "配套待确认",
                system=DISTRIBUTED,
                source_id=pb20,
                evidence=CASE_NOTES[DISTRIBUTED] + "点位数、型号与数量口径待确认。",
                kind="accessory",
                need_key="distributed-paperless." + need,
                need_name=feature,
                target_variant_ids=[target],
                accessory_type="optional",
                calculation_scope="system",
                output_kind="hardware",
                evidence_refs=[sources.evidence(DISTRIBUTED, row)],
            )
        )
    rules.append(
        new_rule(
            "分布式平板方案 · 推荐交换机型号及数量待确认",
            system=DISTRIBUTED,
            source_id=pb20,
            evidence="原文要求搭配推荐平板和交换机；端口、PoE、上联及数量待确认。",
            kind="accessory",
            status="confirmed",
            need_key="distributed-paperless.network-switch",
            need_name="网络交换机",
            output_kind="hardware",
            evidence_refs=[sources.evidence(DISTRIBUTED, 33)],
        )
    )
    pb30, _ = sources.get(SAFE, 10)
    gl30, _ = sources.get(SAFE, 9)
    rules.append(
        new_rule(
            "安全无纸化平板方案 · 管理软件配套待确认",
            system=SAFE,
            source_id=pb30,
            evidence=CASE_NOTES[SAFE] + "同单出现不代表固定一套，服务端部署及授权计量待确认。",
            kind="accessory",
            need_key="safe-paperless.management-software",
            need_name="安全无纸化服务端软件",
            target_variant_ids=[gl30],
            output_kind="software",
            calculation_scope="system",
            evidence_refs=[sources.evidence(SAFE, 9)],
        )
    )
    return rules
