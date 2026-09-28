"""Review scope and explicit gaps; historical quotations are not compatibility approval."""

ACTOR = "资料复核（2026-09-28真实报价核对）"
MARKER = "【2026-09-28无纸化知识复核】"
DISTRIBUTED = "分布式无纸化会务系统2.0"
SAFE = "安全无纸化V3.0"
THIRD_PARTY = "第三方配套产品"
SYSTEMS = (DISTRIBUTED, SAFE)
EXTRA_ROLES = ("会议平板", "移动部署宿主", "无线网络", "充电设备")
FEATURES = {
    "信号输入控制器": "外部视频输入",
    "信号输出控制器": "视频输出到大屏",
    "充电设备": "集中充电",
    "无线网络": "无线接入",
    "投屏终端": "投屏",
    "投屏客户端软件": "投屏",
    "投票终端": "独立投票",
    "投票客户端软件": "独立投票",
    "会议室授权": "多会议室管理",
    "人脸识别功能": "人脸识别签到",
    "人脸识别授权": "人脸识别签到",
}
GAPS = {
    "服务端": "软件实际部署设备、操作系统及版本、终端容量、CPU/内存需求和共用依据待确认。",
    "服务端软件": "按项目、系统还是部署实例授权待确认；浏览器访问不能证明服务端操作系统。",
    "客户端软件": "授权计量及客户端环境待确认；软件套数不能自动等同本次采购平板数。",
    "移动部署宿主": "目录G540为i7/16GB，雅安旧单为i5/8GB；移动部署备注不证明该软件兼容。",
    "会议平板": "代际、操作系统、裸机或内置软件、已有终端及新增供货数量待确认。",
    "无线网络": "指定AP推荐比例不能扩大到所有型号；现场覆盖、并发、上联和供电待确认。",
    "充电设备": "容量按所选型号区分；同时充电数、平板尺寸、充电接口及功率待确认。",
}
CASE_NOTES = {
    DISTRIBUTED: (
        "西安市应急局32套无纸化会议系统报价清单2025.10.14 .xlsx，Sheet1："
        "C8:E15记录1516N/GL20S/PB20S及外采设备；E10为32套软件、E13为30台平板，"
        "差额用途未说明；J11:J12合并的选配同时覆盖NAS-320T/R。"
        "D9/D10对应当前目录H21/H33招标参数。历史共现不确认通用兼容、数量或采购责任。"
    ),
    SAFE: (
        "雅安市应急管理局12套安全无纸化报价清单2.15.xlsx，平板无纸化C8:J12："
        "G540 -042、GL30S、PB30S、C5和AP同单列出，服务软件实际部署位置未写明。"
        "D10的44项参数与当前分布式目录F33/F32规范化文本对应，型号仍保留PB30S，"
        "历史版本或参数引用待确认。C5仅有6+128 WiFi，不能确定代际。"
    ),
}

# Adjacent hardware/software rows establish review candidates, not a verified 1:1 licence rule.
UNVERIFIED_PAIRINGS = {
    "distributed-paperless.desktop-client-software",
    "distributed-paperless.streaming-software",
    "distributed-paperless.info-display-software",
    "distributed-paperless.service-terminal-software",
    "safe-paperless.cast-software",
    "safe-paperless.vote-software",
}
EXPLICIT_QUANTITIES = {
    "distributed-paperless.room-license": (DISTRIBUTED, 22, "按会议室数量收取"),
    "distributed-paperless.face-terminal-license": (DISTRIBUTED, 7, "每个签到终端需发放一个授权"),
}


def system_for_rule(rule):
    if rule.get("system") in SYSTEMS:
        return rule["system"]
    key = rule.get("need_key", "")
    if key.startswith("distributed-paperless."):
        return DISTRIBUTED
    if key.startswith("safe-paperless."):
        return SAFE
    return None
