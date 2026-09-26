"""Source-backed attributes for general infrastructure products."""

from knowledge_seed import source
from variant_seed import VariantUpdate

SHEET = "第三方配套产品"
SYSTEM = "基础设施"


def attribute(key: str, kind: str, value, *, unit: str = "") -> dict:
    return {"key": key, "kind": kind, "value": value, "unit": unit}


def server_updates() -> tuple[VariantUpdate, ...]:
    definitions = (
        (3, "NF5280M5", "X86服务器"),
        (4, "NF5280M6", "X86服务器"),
        (5, "NF5280A6", "X86服务器"),
    )
    return tuple(
        VariantUpdate(
            ref=source(SHEET, row, model),
            systems=(SYSTEM,),
            evidence=(
                f"{SHEET} 第{row}行名称明确为服务器，参数明确为双路 X86 架构；"
                "终端范围保留为来源描述，不据此确认具体业务系统兼容或共享部署。"
            ),
            attributes=(attribute("catalog_role", "text", role),),
        )
        for row, model, role in definitions
    )


def portable_server_updates() -> tuple[VariantUpdate, ...]:
    return (
        VariantUpdate(
            ref=source(SHEET, 12, "华为 G540 I7-1260P"),
            systems=(SYSTEM,),
            evidence=(
                f"{SHEET} 第12行备注明确可作为移动式部署服务器；参数明确 Intel "
                "i7-1260P、16GB 内存、512GB SSD 和 Windows 11 Home Basic 64位。"
            ),
            attributes=(
                attribute("catalog_role", "text", "移动部署服务器"),
                attribute("deployment_form", "text", "移动式"),
                attribute("cpu_arch", "enum", ["x86"]),
                attribute("cpu_model", "text", "Intel i7-1260P"),
                attribute("cpu_cores", "number", "12"),
                attribute("memory", "quantity", "16", unit="GB"),
                attribute("memory_maximum", "quantity", "64", unit="GB"),
                attribute("storage", "quantity", "512", unit="GB"),
                attribute("os", "enum", ["Windows 11 Home Basic 64位"]),
            ),
        ),
        VariantUpdate(
            ref=source(SHEET, 13, "华为 L540-031"),
            systems=(SYSTEM,),
            evidence=(
                f"{SHEET} 第13行备注明确可作为国产化移动式部署服务器；参数明确"
                "麒麟9006C、16GB 内存、512GB 存储及 KOS/UOS 试用版。"
            ),
            attributes=(
                attribute("catalog_role", "text", "国产化移动部署服务器"),
                attribute("deployment_form", "text", "移动式"),
                attribute("cpu_model", "text", "麒麟9006C"),
                attribute("memory", "quantity", "16", unit="GB"),
                attribute("storage", "quantity", "512", unit="GB"),
                attribute("os", "enum", ["KOS试用版", "UOS试用版"]),
            ),
        ),
    )


def switch_update(
    row: int,
    model: str,
    role: str,
    *,
    ethernet_ports: int,
    optical_ports: int,
    extra_attributes: tuple[dict, ...] = (),
) -> VariantUpdate:
    return VariantUpdate(
        ref=source(SHEET, row, model),
        systems=(SYSTEM,),
        evidence=(
            f"{SHEET} 第{row}行产品名称和参数明确为{role}；端口数及供电能力"
            "按该行参数原文维护，不推导具体系统的交换机数量。"
        ),
        attributes=(
            attribute("catalog_role", "text", role),
            attribute("ethernet_port_count", "number", str(ethernet_ports)),
            attribute("optical_port_count", "number", str(optical_ports)),
            attribute("poe_support", "enum", ["是" if "PoE" in role else "否"]),
            *extra_attributes,
        ),
    )


def switch_updates() -> tuple[VariantUpdate, ...]:
    return (
        switch_update(
            23,
            "S5100-8TS-AC",
            "以太网交换机",
            ethernet_ports=8,
            optical_ports=2,
        ),
        switch_update(
            24,
            "2GF8GE-P-LI-AC",
            "PoE交换机",
            ethernet_ports=8,
            optical_ports=2,
            extra_attributes=(
                attribute("poe_port_power_maximum", "quantity", "30", unit="W"),
                attribute("poe_budget", "quantity", "130", unit="W"),
            ),
        ),
        switch_update(
            25,
            "S5530-24T4S-S",
            "以太网交换机",
            ethernet_ports=24,
            optical_ports=4,
        ),
        switch_update(
            26,
            "S5560E-24T4X-PS",
            "PoE交换机",
            ethernet_ports=24,
            optical_ports=4,
            extra_attributes=(
                attribute("poe_budget_minimum", "quantity", "400", unit="W"),
            ),
        ),
        switch_update(
            29,
            "S110-8LP2ST",
            "PoE交换机",
            ethernet_ports=9,
            optical_ports=1,
            extra_attributes=(attribute("output_power", "quantity", "54", unit="W"),),
        ),
    )


def variant_updates() -> tuple[VariantUpdate, ...]:
    return (*server_updates(), *portable_server_updates(), *switch_updates())
