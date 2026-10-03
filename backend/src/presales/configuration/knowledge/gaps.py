"""Field-level evidence gaps. Publication state is not completeness."""

from .combination_schemas import missing_combination


def relation_gaps(rule):
    fields = []
    if rule["status"] != "confirmed":
        fields.append(
            (
                "relation_unconfirmed",
                "status",
                "关系尚未确认" if rule["status"] == "draft" else "关系已停用",
            )
        )
    if rule["kind"] == "accessory":
        fields.extend(accessory_gaps(rule))
    if rule["kind"] == "combination":
        fields.extend(
            ("combination_incomplete", field, "组合目标或范围待确认：" + field)
            for field in missing_combination(rule)
        )
    return fields


def accessory_gaps(rule):
    fields = []
    for field, label in [("target_variant_ids", "候选配置"), ("calculation_scope", "计算范围")]:
        if not rule.get(field):
            fields.append(("accessory_incomplete", field, label))
    for field in ("mode", "factor"):
        if rule.get(field) is None:
            fields.append(("accessory_quantity_missing", field, "数量公式"))
    if rule.get("quantity_source") == "environment" and not rule.get("quantity_key"):
        fields.append(("accessory_quantity_missing", "quantity_key", "需求参数"))
    if rule.get("quantity_review") != "confirmed" or not rule.get("quantity_evidence"):
        fields.append(
            (
                "accessory_quantity_unconfirmed",
                "quantity_review",
                "数量依据尚未单独确认（旧公式不等于确认）",
            )
        )
    return fields
