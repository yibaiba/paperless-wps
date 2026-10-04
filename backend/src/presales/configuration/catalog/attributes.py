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
    AttributeDefinition("eg_floor_box_count", "会议地插安装数量", "number"),
    AttributeDefinition("eg_extension_cable_count", "会议延长线条数", "number"),
    AttributeDefinition("audio_capture_room_count", "需要音频采集的会议室数量", "number"),
    AttributeDefinition("subtitle_room_count", "启用字幕投屏的会议室数量", "number"),
    AttributeDefinition("extra_audio_concurrency_count", "需额外购买的音频并发路数", "number"),
    AttributeDefinition("microphone_count", "本系统会议话筒数量", "number"),
    AttributeDefinition("simultaneous_charging_count", "需要同时充电的终端数量", "number"),
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
    AttributeDefinition("storage", "存储容量", "quantity", ("GB", "MB", "TB")),
    AttributeDefinition("network_mode", "网络版本", "enum"),
    AttributeDefinition("charging_capacity", "同时充电台数", "quantity", ("台",)),
    AttributeDefinition("max_tablet_inches", "适配平板最大尺寸（英寸）", "number"),
    AttributeDefinition("usb_output_spec", "单路 USB 输出规格", "text"),
    AttributeDefinition("external_dimensions", "外形尺寸及方向原文", "text"),
    AttributeDefinition("max_ap_count", "最大管理 AP 数量", "quantity", ("台",)),
    AttributeDefinition("included_ap_licenses", "已含 AP 授权数", "number"),
    AttributeDefinition("recommended_terminals_per_ap", "每台 AP 推荐终端数", "number"),
    AttributeDefinition("power", "功耗", "quantity", ("W",)),
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
