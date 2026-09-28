from collections import Counter
from decimal import Decimal


def project_readiness(data, checks, suggestions):
    stages = [
        requirement_stage(data),
        selection_stage(data),
        accessory_stage(suggestions),
        verification_stage(checks),
    ]
    output = output_stage(stages)
    stages.append(output)
    return {
        "status": output["status"],
        "ready_for_draft": bool(data.get("devices")),
        "ready_for_confirmed_output": output["status"] == "pass",
        "counts": {
            "rooms": len(data.get("rooms", [])),
            "systems": len(data.get("systems", [])),
            "requirements": len(data.get("requirements", [])),
            "selected_requirements": sum(
                bool(item.get("device_id")) for item in data.get("requirements", [])
            ),
            "devices": len(data.get("devices", [])),
            "conflicts": sum(item.get("status") == "conflict" for item in checks),
            "unknowns": sum(item.get("status") == "unknown" for item in checks),
            "open_accessories": sum(accessory_is_open(item) for item in suggestions),
            "accessory_unknowns": sum(item.get("status") == "unknown" for item in suggestions),
            "accessory_conflicts": sum(item.get("status") == "conflict" for item in suggestions),
        },
        "pending_by_kind": dict(
            Counter(item["kind"] for item in checks if item.get("status") == "unknown")
        ),
        "stages": stages,
    }


def requirement_stage(data):
    rooms = data.get("rooms", [])
    systems = data.get("systems", [])
    requirements = data.get("requirements", [])
    missing = []
    if not rooms:
        missing.append("房间")
    if not systems:
        missing.append("系统版本")
    if not requirements:
        missing.append("角色需求")
    return stage(
        "requirements",
        "项目需求",
        "unknown" if missing else "pass",
        "缺少" + "、".join(missing) if missing else f"已建立 {len(requirements)} 个角色需求",
    )


def selection_stage(data):
    requirements = data.get("requirements", [])
    if not requirements:
        return stage("selection", "产品选型", "unknown", "尚未建立角色需求")
    missing = [item for item in requirements if not item.get("device_id")]
    return stage(
        "selection",
        "产品选型",
        "unknown" if missing else "pass",
        f"还有 {len(missing)} 个角色未选择产品" if missing else "全部角色已关联实际配置",
    )


def accessory_stage(suggestions):
    conflicts = [item for item in suggestions if item.get("status") == "conflict"]
    unknown = [item for item in suggestions if item.get("status") == "unknown"]
    missing = [item for item in suggestions if accessory_is_open(item)]
    if conflicts:
        return stage("accessories", "配套与缺件", "conflict", f"有 {len(conflicts)} 项配套冲突")
    if unknown:
        return stage("accessories", "配套与缺件", "unknown", f"有 {len(unknown)} 项配套资料不足")
    if missing:
        return stage("accessories", "配套与缺件", "unknown", f"还有 {len(missing)} 项配套未应用")
    message = "没有待补配套" if not suggestions else "配套需求均已满足"
    return stage("accessories", "配套与缺件", "pass", message)


def verification_stage(checks):
    conflicts = [item for item in checks if item.get("status") == "conflict"]
    unknown = [item for item in checks if item.get("status") == "unknown"]
    if conflicts:
        return stage("verification", "方案校验", "conflict", f"有 {len(conflicts)} 项明确冲突")
    if unknown:
        return stage("verification", "方案校验", "unknown", f"有 {len(unknown)} 项资料不足")
    if not checks:
        return stage("verification", "方案校验", "unknown", "尚未形成可校验的选型")
    return stage("verification", "方案校验", "pass", "已知兼容、共享和容量检查均通过")


def output_stage(stages):
    statuses = {item["status"] for item in stages}
    if "conflict" in statuses:
        return stage("output", "清单与输出", "conflict", "解决明确冲突后才能形成确认版输出")
    if statuses == {"pass"}:
        return stage("output", "清单与输出", "pass", "可以形成确认版清单和方案输出")
    return stage("output", "清单与输出", "unknown", "可以保存草稿，确认资料缺口后再形成确认版")


def accessory_is_open(item):
    missing = item.get("missing")
    if item.get("status") != "pass" or missing is None:
        return False
    return Decimal(str(missing)) > 0


def stage(key, label, status, message):
    return {"key": key, "label": label, "status": status, "message": message}
