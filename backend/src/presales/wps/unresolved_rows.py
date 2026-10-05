"""Preserve unresolved identities, but never treat their old quantities as current evidence."""


def projection_input(request, state):
    baseline = {d["id"] for d in state["configuration"]["devices"]}
    bound = {
        b["line_id"]: b["device_id"] for b in state["binding"].payload.get("line_bindings", [])
    }
    preserved, snapshots = set(), []
    for row in request.unresolved_rows:
        known = bound.get(row.line_id)
        if known and row.device_id != known:
            raise ValueError("未解析行不能更换原设备身份")
        if row.confirmed_line:
            snapshots.append(row.confirmed_line)
        elif row.device_id and row.device_id not in baseline:
            raise ValueError("未同步设备的未解析行缺少上次确认快照，请重新确认身份")
        if row.device_id:
            preserved.add(row.device_id)
    return request.model_copy(update={"lines": [*request.lines, *snapshots]}), preserved


def row_issues(request, checked):
    data, scope = checked["configuration"], checked["evaluation_scope"]
    systems = {s["id"] for s in data["systems"]}
    uses = {}
    for requirement in data["requirements"]:
        devices = {a["device_id"] for a in requirement.get("allocations", [])}
        if requirement.get("device_id"):
            devices.add(requirement["device_id"])
        for device in devices:
            uses.setdefault(device, set()).add(requirement["system_id"])
    issues = []
    for row in request.unresolved_rows:
        if row.system_id and row.system_id not in systems:
            raise ValueError("未解析行指定了不存在的业务系统")
        related = unresolved_related(row, scope=scope, uses=uses)
        issues.append(
            dict(
                code="workbook_row_unresolved",
                origin="business_context",
                blocking=related,
                sheet=row.sheet,
                row=row.row,
                line_id=row.line_id,
                device_id=row.device_id,
                system_id=row.system_id,
                reason_code=row.reason_code,
                message="该行身份或业务值尚未确认；请定位核对，不能按缺失产品采购"
                if related
                else "其他业务区有未解析行；本次建议不依赖该行，正式同步前仍需处理",
            )
        )
    return issues


def unresolved_related(row, *, scope, uses):
    if not row.system_id or row.system_id in scope["system"]:
        return True
    if row.device_id:
        actual = uses.get(row.device_id, set())
        return (
            not actual
            or bool(actual.intersection(scope["system"]))
            or row.device_id in scope["device"]
        )
    return False
