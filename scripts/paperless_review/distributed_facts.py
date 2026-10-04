"""Exact V2.2 facts; no deployment quantities or cross-generation compatibility inferred."""

from copy import deepcopy

from presales.configuration.catalog.schemas import VariantInput

from .facts import extracted, quantity, value

ACTOR = "分布式原文补齐（2026-10-04）"
MARKER = "【分布式原文补齐20261004】"
GENERIC_OS_GAP = "运行环境/安装适配条件未明确，不能根据网页访问或下载客户端推定服务器系统。"

FACTS = {
    24: (
        value("video_input_spec", "1080P@60fps", needle="输入分辨率最高支持1080P@60fps"),
        value("power_supply_spec", "DC12V", needle="电源：DC12V"),
    ),
    25: (
        value(
            "video_decode_spec",
            "1路1080p@60fps或4路1080@30fps",
            needle="支持同时1路1080p@60fps解码或4路1080@30fps解码",
        ),
        value("power_supply_spec", "DC12V", needle="电源：DC12V"),
    ),
    61: (
        value("os", ["Android"], needle="操作系统：Android", kind="enum"),
        quantity("storage", "8", "GB", needle="板载8G工业级固态存储"),
        value("power_supply_spec", "POE或DC12V", needle="支持POE与DC12V两种供电方式"),
    ),
    62: (value("os", ["Android"], needle="软件基于Android平台开发", kind="enum"),),
    63: (
        quantity("storage", "128", "GB", needle="128G工业固态硬盘"),
        value("display_inches", "32", needle="32寸原装A+级液晶面板", kind="number"),
    ),
    65: (
        value("os", ["Android"], needle="系统：Android 10", kind="enum"),
        value("os_version", ["10"], needle="系统：Android 10", kind="enum"),
        quantity("storage", "64", "GB", needle="存储空间：64GB"),
        value(
            "video_output_spec",
            "HDMI×2；仅HDMI 1明确支持4K(4096x2160)@30Hz",
            needle="视频输出：HDMI×2，HDMI 1支持4K(4096x2160)@30Hz",
        ),
    ),
    66: (value("os", ["Android"], needle="软件基于Android平台开发", kind="enum"),),
}
MODELS = {
    24: "NAS-320T",
    25: "NAS-320R",
    61: "CRIR-156R",
    62: "PCS-XF20S",
    63: "CRIR-320WT",
    65: "PCS-1640P",
    66: "PCS-HH20S",
}
OS_ROWS = {62: "信息发布软件", 65: "候会语音播报终端", 66: "候会播报软件"}
NOTES = {
    24: "当前明细输入最高1080P/60；旧模板4K描述冲突，未扩大能力。",
    25: "单路/多路解码并发与分辨率分别保留；没有把输入栏或解码能力推定为4K输出能力。",
    61: "默认存储8GB；可定制32GB不作为当前已配置容量。POE供电不代表任意交换机兼容。",
    62: "原文确认Android平台，具体系统版本、硬件适配与许可数量仍待核对。",
    63: "记录明确存储和屏幕尺寸；Intel处理器不构成Windows系统依据。",
    65: "原文确认Android10，HDMI 1的4K/30能力不扩大到所有接口；显示和扩声配套仍须另行核对。",
    66: "原文确认Android平台，具体版本、播报终端兼容及授权范围仍待核对。",
}


def source_variant(original, source):
    payload = VariantInput.model_validate(
        {k: deepcopy(v) for k, v in original.items() if k in VariantInput.model_fields}
    ).model_dump(mode="json")
    if MARKER in payload["evidence"]:
        return VariantInput.model_validate(payload).model_dump(mode="json")
    attributes = {a["key"]: a for a in payload["attributes"]}
    references = []
    for fact in FACTS[source["row"]]:
        attribute, reference = extracted(source, fact)
        old = attributes.get(fact.key)
        if old and old["value"] is not None and old != attribute:
            raise ValueError(f"已有属性与原文补齐冲突：{source['id']} {fact.key}")
        attributes[fact.key] = attribute
        references.append(reference)
    if source["row"] in OS_ROWS:
        attributes["os_source"] = dict(
            key="os_source", kind="text", unit="", value=references[0]["quote"]
        )
        gap = attributes.get("pending_questions")
        if gap and isinstance(gap["value"], str):
            attributes["pending_questions"] = dict(
                gap, value=gap["value"].replace(GENERIC_OS_GAP, "").strip()
            )
    lines = [f"{r['locator']}：{r['quote']}" for r in references]
    payload.update(
        attributes=list(attributes.values()),
        actor=ACTOR,
        evidence=payload["evidence"] + "\n" + MARKER + "\n" + "\n".join(lines),
        description=payload["description"] + "\n" + MARKER + NOTES[source["row"]],
    )
    return VariantInput.model_validate(payload).model_dump(mode="json")
