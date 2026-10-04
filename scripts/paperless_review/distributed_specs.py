"""Prospective inputs are separate from approved quantity and compatibility rules."""

from dataclasses import dataclass

from .specs import DISTRIBUTED as DISTRIBUTED

ACTOR = "分布式 2.0 闭环整理（2026-10-04）"
MARKER = "【分布式独立流程核对】"
NOTICE = "依据 V2.2 当前产品明细整理；功能、数量与推荐范围待核对，不自动发布。"


@dataclass(frozen=True)
class RoleSpec:
    name: str
    row: int | None
    feature: str
    input_key: str
    label: str
    kind: str = "hardware"


ROLES = (
    RoleSpec("服务端", 17, "", "paperless_server_count", "无纸化服务器部署台数"),
    RoleSpec(
        "服务端软件", 21, "", "paperless_management_count", "会议管理软件许可套数", "software"
    ),
    RoleSpec("会议平板", None, "平板参会", "paperless_tablet_count", "实际使用的会议平板台数"),
    RoleSpec(
        "客户端软件",
        33,
        "平板参会",
        "paperless_tablet_license_count",
        "平板客户端软件许可套数",
        "software",
    ),
    RoleSpec(
        "信号输入控制器", 24, "外部视频输入", "paperless_video_input_count", "外部视频输入点位数"
    ),
    RoleSpec(
        "信号输出控制器", 25, "视频输出到大屏", "paperless_video_output_count", "视频输出点位数"
    ),
    RoleSpec(
        "信息发布终端", 61, "会议信息发布", "paperless_info_terminal_count", "信息发布终端台数"
    ),
    RoleSpec(
        "信息发布软件",
        62,
        "会议信息发布",
        "paperless_info_license_count",
        "信息发布软件许可套数",
        "software",
    ),
    RoleSpec(
        "会议服务终端", 63, "会议服务", "paperless_service_terminal_count", "会议服务终端台数"
    ),
    RoleSpec(
        "会议服务软件",
        64,
        "会议服务",
        "paperless_service_license_count",
        "会议服务软件许可套数",
        "software",
    ),
    RoleSpec(
        "候会语音播报终端", 65, "候会播报", "paperless_broadcast_terminal_count", "候会播报终端台数"
    ),
    RoleSpec(
        "候会播报软件",
        66,
        "候会播报",
        "paperless_broadcast_license_count",
        "候会播报软件许可套数",
        "software",
    ),
)
CASE_ROLES = {row: spec.name for row, spec in zip(range(141, 153), ROLES, strict=True)}
BY_NAME = {spec.name: spec for spec in ROLES}
FEATURES = tuple(dict.fromkeys(spec.feature for spec in ROLES if spec.feature))


def selected_roles(definition, names):
    roles = {r["name"]: r for r in definition["roles"]}
    missing = set(names) - roles.keys()
    if missing:
        raise ValueError("资料定义缺少角色：" + "、".join(sorted(missing)))
    return [roles[name] for name in names]


def annotate(original, note):
    if MARKER in original:
        return original
    return original.rstrip() + "\n" + MARKER + note


def draft_quantity(spec, references):
    return dict(
        status="draft",
        scope="system",
        input_key=spec.input_key,
        mode=None,
        factor=None,
        actor=ACTOR,
        evidence=spec.label + "需明确计量口径；不从席位或历史案例默认一比一。",
        evidence_refs=references,
    )
