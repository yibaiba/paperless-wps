from dataclasses import asdict, dataclass
from typing import Literal


@dataclass(frozen=True)
class AttributeDefinition:
    key: str
    label: str
    kind: Literal["text", "enum", "number", "quantity"]
    units: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()


ATTRIBUTE_DEFINITIONS = (
    AttributeDefinition("cpu_arch", "CPU 架构", "enum"),
    AttributeDefinition("cpu_count", "CPU 数量", "number"),
    AttributeDefinition(
        "cores_per_cpu",
        "单 CPU 核数",
        "quantity",
        ("核",),
        ("cores_per_cpu_minimum",),
    ),
    AttributeDefinition("cores", "CPU 总核数", "quantity", ("核",), ("cpu_cores",)),
    AttributeDefinition("os", "操作系统", "enum"),
    AttributeDefinition("os_version", "系统版本", "enum"),
    AttributeDefinition("software_version", "软件版本", "text"),
    AttributeDefinition("memory", "内存", "quantity", ("GB", "MB", "TB")),
    AttributeDefinition(
        "terminal_capacity",
        "终端容量",
        "number",
        aliases=("terminal_count", "capacity"),
    ),
    AttributeDefinition("user_capacity", "用户容量", "number", aliases=("user_count",)),
    AttributeDefinition("width", "宽度", "quantity", ("mm", "cm", "m")),
    AttributeDefinition("height", "高度", "quantity", ("mm", "cm", "m")),
    AttributeDefinition("depth", "深度", "quantity", ("mm", "cm", "m")),
    AttributeDefinition("display_inches", "屏幕尺寸（英寸）", "number"),
    AttributeDefinition("server_type", "服务器类型", "enum"),
    AttributeDefinition("deployment_mode", "部署形态", "enum"),
)


def attribute_definitions():
    return [
        {
            **asdict(item),
            "units": list(item.units),
            "aliases": list(item.aliases),
        }
        for item in ATTRIBUTE_DEFINITIONS
    ]
