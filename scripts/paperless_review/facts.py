"""Curated source facts; quantities here describe products, never project purchases."""

from dataclasses import dataclass
from unicodedata import category

from presales.configuration.catalog.schemas import Attribute

SHEET = "第三方配套产品"
ACTOR = "导入清单复核（2026-10-04）"
MARKER = "【2026-10-04源表事实整理】"


@dataclass(frozen=True)
class Fact:
    key: str
    kind: str
    value: object
    unit: str
    needle: str
    field: str = "specification"


def quantity(key, value, unit, *, needle):
    return Fact(key, "quantity", value, unit, needle)


def value(key, content, *, needle, kind="text", field="specification"):
    return Fact(key, kind, content, "", needle, field)


TABLETS = {
    14: (
        quantity("memory", "8", "GB", needle="运行内存:8GB"),
        quantity("storage", "128", "GB", needle="存储容量:128GB"),
        value("os", None, needle="国产操作系统", kind="enum"),
        value("display_inches", "11", needle="11英寸", kind="number"),
    ),
    15: (
        quantity("memory", "8", "GB", needle="8GB 运行内存"),
        quantity("storage", "256", "GB", needle="256GB 机身存储"),
        value("os", ["鸿蒙"], needle="HarmonyOS 4.2", kind="enum"),
        value("os_version", ["4.2"], needle="HarmonyOS 4.2", kind="enum"),
        value("display_inches", "11.5", needle="11.5 英寸", kind="number"),
        quantity("height", "260.88", "mm", needle="260.88 mm（高）"),
        quantity("width", "176.82", "mm", needle="176.82 mm（宽）"),
        quantity("depth", "6.85", "mm", needle="6.85 mm（厚）"),
        value("network_mode", ["Wi-Fi"], needle="不支持蜂窝网络", kind="enum"),
    ),
    16: (
        quantity("memory", "8", "GB", needle="8GB RAM"),
        quantity("storage", "256", "GB", needle="256GB ROM"),
        value("os", ["鸿蒙"], needle="HarmonyOS 4.2 / 4.3", kind="enum"),
        value("os_version", None, needle="HarmonyOS 4.2 / 4.3", kind="enum"),
        value("display_inches", "11.5", needle="11.5 英寸", kind="number"),
        quantity("height", "260.88", "mm", needle="260.88 mm（高）"),
        quantity("width", "176.82", "mm", needle="176.82 mm（宽）"),
        quantity("depth", "6.85", "mm", needle="6.85 mm（厚）"),
        value("network_mode", ["蜂窝网络"], needle="支持蜂窝网络", kind="enum"),
    ),
    17: (
        quantity("memory", "8", "GB", needle="内存容量：8GB"),
        quantity("storage", "256", "GB", needle="硬盘容量：256GB"),
        value("os", ["鸿蒙"], needle="HarmonyOS 2.0", kind="enum"),
        value("os_version", ["2.0"], needle="HarmonyOS 2.0", kind="enum"),
        value("display_inches", "12", needle="12.0英寸", kind="number"),
    ),
}
NETWORK = {
    20: (
        value(
            "recommended_terminals_per_ap",
            "30",
            needle="配单比例推荐1:30",
            kind="number",
            field="note",
        ),
    ),
    21: (
        quantity("max_ap_count", "64", "台", needle="最大可管理AP数目64个"),
        value(
            "included_ap_licenses",
            "64",
            needle="包含了64个授权",
            kind="number",
            field="note",
        ),
    ),
    22: (
        quantity("max_ap_count", "256", "台", needle="最大可管理AP数目256个"),
        value(
            "included_ap_licenses",
            None,
            needle="包含了128个授权",
            kind="number",
            field="note",
        ),
    ),
    27: (
        value(
            "recommended_terminals_per_ap",
            "30",
            needle="配单比例推荐1:30",
            kind="number",
            field="note",
        ),
        quantity("power", "21.2", "W", needle="最大功耗21.2W"),
    ),
    28: (Fact("max_ap_count", "quantity", "128", "台", "最多可以接入128台AP", "note"),),
}
CARTS = {
    31: (60, "700*530*950mm"),
    32: (18, "640*360*370mm"),
    33: (36, "710*430*890mm"),
    34: (54, "740*460*1080mm"),
    35: (64, "670*460*1250mm"),
}
NOTES = {
    14: "原文仅写国产操作系统，未推断为鸿蒙或确定版本。",
    15: "仅记录明确预装 4.2；可能升级 4.3 与推测 CPU 型号不作为已确认配置。",
    16: "原文并列 4.2 / 4.3，具体交付系统版本未知。",
    21: "备注与参数均列 64 个授权；未明确与本库其他授权 SKU 的抵扣映射。",
    22: (
        "授权原文有差异：备注包含128个授权，参数要求实配256个；"
        "最大管理容量256与已含授权不是同一指标，已含数量暂未知。"
    ),
    27: (
        "支持 Leader AP；是否选 AC、授权是否已包含及需补数量依部署方式确认。"
        "推荐1:30不是硬性最大并发容量。"
    ),
    28: "默认管理128个AP不等于已证实包含128份 L-WAC-S-1AP；须核对默认权益和额外授权。",
}


def fact_rows():
    rows = {**TABLETS, **NETWORK}
    for row, (capacity, dimensions) in CARTS.items():
        facts = [
            quantity(
                "charging_capacity",
                str(capacity),
                "台",
                needle=f"支持{capacity}台平板电脑同时充电",
            )
        ]
        facts.append(value("external_dimensions", None, needle=dimensions))
        if row >= 32:
            facts.append(value("usb_output_spec", "5V,2A", needle="额定输出电压电流5V,2A"))
        if row == 33:
            facts.append(value("max_tablet_inches", "12.9", needle="尺寸≤12.9寸", kind="number"))
        rows[row] = tuple(facts)
    return rows


def quote_line(source, fact):
    # Source cells contain zero-width format characters; retain the original evidence line.
    lines = str(source.get(fact.field, "")).splitlines()
    found = next(
        (line for line in lines if fact.needle in "".join(c for c in line if category(c) != "Cf")),
        None,
    )
    if found is None:
        raise ValueError(f"来源不包含预期事实：{source['sheet']}!{source['row']} {fact.key}")
    return found


def extracted(source, fact):
    quote = quote_line(source, fact)
    content = quote if fact.key == "external_dimensions" else fact.value
    attribute = Attribute(key=fact.key, kind=fact.kind, value=content, unit=fact.unit)
    reference = dict(
        source_id=source["id"],
        locator=f"{source['sheet']}!第{source['row']}行/{fact.field}",
        quote=quote,
    )
    return attribute.model_dump(mode="json"), reference
