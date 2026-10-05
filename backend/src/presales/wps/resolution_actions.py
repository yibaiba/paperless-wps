"""Navigation only: diagnostic actions never authorize workbook mutations."""


def action_kinds(issue):
    code = issue.get("code", "")
    if code == "workbook_row_unresolved":
        return [("confirm_identity", "确认这一行"), ("locate_row", "定位问题行")]
    if code == "typed_source_excluded":
        return [("check_source", "核对模板来源")]
    if code in {"typed_selection_stale", "role_ambiguous", "product_source_ambiguous"}:
        return [("confirm_identity", "核对产品与用途")]
    if code in {
        "typed_role_unresolved",
        "typed_no_match",
        "typed_conflict",
        "typed_evidence_required",
    }:
        return [("review_knowledge", "查看固定依据"), ("edit_business", "核对业务设置")]
    if issue.get("field") or issue.get("requirement_id"):
        return [("edit_business", "核对业务参数"), ("review_knowledge", "查看固定依据")]
    return [("review_knowledge", "查看检查依据")]


def with_resolution_actions(issues, *, request, fingerprint):
    result = []
    for issue in issues:
        if not isinstance(issue, dict):
            result.append(issue)
            continue
        actions = [
            dict(
                kind=kind,
                label=label,
                sheet=issue.get("sheet", request.active_cell.sheet),
                row=issue.get("row", request.active_cell.row),
                column=request.active_cell.column,
                requirement_id=issue.get("requirement_id"),
                device_id=issue.get("device_id"),
                expected_local_revision=request.local_revision,
                context_fingerprint=fingerprint,
                binding_id=request.binding_id,
                template_profile_revision=request.template_profile_revision,
            )
            for kind, label in action_kinds(issue)
        ]
        result.append(dict(issue, resolution_actions=actions))
    return result
