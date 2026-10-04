from decimal import Decimal


def conclusion(row, binding, *, context, result, missing):
    if binding["disposition"] == "not_enabled":
        system = next(
            (
                s
                for s in context["configuration"]["systems"]
                if s["id"] == binding["feature_system_id"]
            ),
            None,
        )
        if binding["feature"] not in context.get("known_features", {}).get(
            binding["feature_system_id"], set()
        ):
            return "unknown", "未在固定资料中找到此功能，请重新核对"
        if not system:
            return "unknown", "原关联的功能系统已移除，请重新核对"
        if system["id"] not in context["configuration"].get("generation", {}).get(
            "features_confirmed", []
        ):
            return "unknown", "功能选择尚未确认，不能判断未启用"
        if binding["feature"] in system["features"]:
            return "conflict", "此功能已重新启用，原未选用结论需要更新"
        if result["device_ids"] or Decimal(result["included"]) > 0:
            return "conflict", "功能关闭但关联设备或已含分配仍保留，请明确处理"
        return "not_enabled", "项目明确未启用此功能；不据此删除现有设备"
    if missing:
        return "unknown", "关联设备已删除：" + "、".join(missing)
    if any(c["status"] == "conflict" for c in result["issues"]):
        return "conflict", "关联对象存在明确业务冲突"
    if binding["disposition"] == "unresolved":
        return "unknown", binding["evidence"]
    quantity = Decimal(result["deployed"]) + Decimal(result["included"])
    if quantity == 0:
        return "unknown", "关联需求尚未生成设备或抵扣内容"
    if result["issues"]:
        return "unknown", "已关联实际对象，但仍有资料或供货等事项待确认"
    if Decimal(result["existing"]) == Decimal(result["deployed"]):
        return "satisfied", "由明确关联的客户已有设备或已含内容满足；数量差异单独列示"
    if not row["variant_ids"]:
        return "unknown", "已关联设备，但原案例具体配置尚未核对，不能仅按型号判断相同"
    if any(
        context["devices"][i]["variant_id"] not in row["variant_ids"] for i in result["device_ids"]
    ):
        return "alternative", "采用其他具体配置；按当前配置检查，原案例不证明可替代"
    return "matched", "已对应同一已核对配置；数量差异按当前需求处理，不以案例数量判错"
