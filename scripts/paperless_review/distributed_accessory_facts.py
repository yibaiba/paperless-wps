"""Product limits and bundled features, distinct from purchase quantities."""

from copy import deepcopy

from presales.configuration.catalog.schemas import VariantInput

from .facts import extracted, quantity, value
from .maintenance import stable_id

ACTOR = "分布式配套原文复核（2026-10-04）"
MARKER = "【分布式配套原文复核20261004】"
LIFT_QUOTE = "必配升降话筒单元模块和会议主机"
STANDALONE_QUOTE = "须搭配升降器使用，无法独立使用"
BANNER_QUOTE = "会议标语功能系统标配支持，无需额外购置会议标语硬件终端和软件"
CAPACITY_QUOTE = "最多支持12个主席和100个代表单元，其中每路最多30个代表单元"
MODELS = {
    21: "PCS-GL20S",
    58: "ACS-320M",
    59: "PCS-310C",
    60: "PCS-310D",
    **{
        row: "IPH-S" + size + suffix
        for row, (size, suffix) in enumerate(
            ((size, suffix) for suffix in ("AM", "BM") for size in ("156", "173", "185", "215")),
            start=42,
        )
    },
}
FACTS = {
    21: (value("included_feature_description", BANNER_QUOTE, needle=BANNER_QUOTE),),
    58: (
        quantity("microphone_chair_capacity", "12", "个", needle=CAPACITY_QUOTE),
        quantity("microphone_delegate_capacity", "100", "个", needle=CAPACITY_QUOTE),
        value("microphone_wiring_spec", "每路最多30个代表单元", needle=CAPACITY_QUOTE),
        value("microphone_line_ports", "4路线路接口：RJ45", needle="4路线路接口 ：RJ45"),
        value(
            "microphone_cascade_spec",
            "多台主机级联可接512个单元",
            needle="多台主机级联可接512个单元",
        ),
        value(
            "microphone_speaking_spec",
            "同时发言代表单元1—9位",
            needle="同时发言的代表单元可以在 1-9 位之间任意设置",
        ),
    ),
}
NOTES = {
    21: "标语是已含功能事实，不生成独立SKU或采购量；没有可抵扣的具体配置映射。",
    58: "单机主席/代表容量分开记录；每路30不等于整机120，级联512不等于单机容量。"
    "1—9是同时发言数，不是接入数。线路分配、级联拓扑及适配仍须核对，不推算主机采购台数。",
}


def accessory_variant(original, source):
    data = VariantInput.model_validate(
        {k: deepcopy(v) for k, v in original.items() if k in VariantInput.model_fields}
    ).model_dump(mode="json")
    if MARKER in data["evidence"]:
        return data
    attributes = {a["key"]: a for a in data["attributes"]}
    refs = []
    for fact in FACTS[source["row"]]:
        attribute, reference = extracted(source, fact)
        previous = attributes.get(fact.key)
        if previous and previous["value"] is not None and previous != attribute:
            raise ValueError("已有参数与原文冲突：" + fact.key)
        attributes[fact.key] = attribute
        refs.append(reference)
    if source["row"] == 21:
        # A function is not an identified SKU: no quantity or automatic credit.
        item = dict(
            id=stable_id("distributed-paperless.included-banner"),
            name="会议标语功能（系统标配）",
            kind="software",
            status="draft",
            quantity=None,
            variant_id=None,
            need_keys=[],
            evidence=NOTES[21],
            evidence_refs=refs,
        )
        if any(i["id"] == item["id"] for i in data["included_items"]):
            raise ValueError("标语包含项已有维护记录，请核对后再应用")
        data["included_items"].append(item)
    data.update(
        attributes=list(attributes.values()),
        actor=ACTOR,
        description=data["description"] + "\n" + MARKER + NOTES[source["row"]],
        evidence=data["evidence"]
        + "\n"
        + MARKER
        + "\n"
        + "\n".join(f"{r['locator']}：{r['quote']}" for r in refs),
    )
    return VariantInput.model_validate(data).model_dump(mode="json")
