from presales.configuration.projects.planning.next_edits import (
    NextEditContext,
    next_edit_options,
    removal_option,
)

from .business import workbook_projection
from .edit_decision import added_purchase, decision_for, next_target
from .edit_identity import action_context, is_dismissed, with_identity
from .next_edit_projection import project_next_edit
from .templates import TemplateProfiles


def completion_preview(sync, request):
    projection = workbook_projection(sync, request)
    checked = projection["checked"]
    scope = request.scope
    system = next(
        (s for s in checked["configuration"]["systems"] if s["id"] == scope.system_id), None
    )
    if system is None or system["room_id"] != scope.room_id:
        raise ValueError("工作簿业务区与项目房间或系统不一致，请重新确认业务设置")
    if (
        not scope.start_row <= request.active_cell.row <= scope.end_row
        or request.active_cell.sheet != scope.sheet
    ):
        raise ValueError("活动单元格不属于选定业务区")
    if scope.requirement_id and not any(
        r["id"] == scope.requirement_id and r["system_id"] == scope.system_id
        for r in checked["configuration"]["requirements"]
    ):
        raise ValueError("当前行用途不属于选定系统")
    profile = TemplateProfiles(sync.session).get(
        projection["state"]["binding"].payload["template_profile_id"],
        request.template_profile_revision,
    )
    catalog_scope = profile.get("catalog_scope")
    if not catalog_scope:
        raise ValueError("请先确认模板产品来源范围")
    repository = projection["repository"]
    catalog = repository.catalog.variants()
    sources = {
        v["id"]: [
            s["id"]
            for s in v["source_details"]
            if all(s.get(key) == value for key, value in catalog_scope.items())
        ]
        for v in catalog
    }
    context = NextEditContext(
        repository=repository,
        configuration=checked["configuration"],
        proposal_id=projection["fingerprint"],
        deployment="independent",
        allowed_sources=sources,
        query=request.query,
        selected_variant_id=request.selected_variant_id or "",
        selected_source_id=request.selected_source_id or "",
        system_id=scope.system_id,
    )
    if request.intent == "remove":
        line = next(
            (
                line
                for line in request.lines
                if line.sheet == request.active_cell.sheet and line.row == request.active_cell.row
            ),
            None,
        )
        if not line or not line.device_id:
            raise ValueError("请先确认要移除的产品行身份")
        options = [removal_option(context, checked, device_id=line.device_id)]
        questions = []
    else:
        options, questions = next_edit_options(
            context,
            checked,
            system_id=scope.system_id,
            requirement_id=scope.requirement_id,
            recent_requirement_id=recent_requirement(request, checked),
        )
    items = [
        project_next_edit(option, request=request, profile=profile, projection=projection)
        for option in options
        if option["changes"]
    ]
    questions = [*questions, *(q for option in options for q in option["questions"])]
    business_context = action_context(projection, request)
    items = list(
        {
            item["id"]: with_identity(item, business_context=business_context) for item in items
        }.values()
    )
    filtered = [item for item in items if not is_dismissed(item, request.recent_edits)]
    suppressed = len(filtered) != len(items)
    items = sorted(filtered, key=lambda item: (not item["applicable"], added_purchase(item)))
    issues = [*questions, *sync._issues(checked)]
    primary, decision = decision_for(
        items, query=request.query, issues=issues, suppressed=suppressed
    )
    if primary:
        items = [primary, *[item for item in items if item["id"] != primary["id"]]]
    return dict(
        items=items,
        issues=issues,
        decision=decision,
        primary_suggestion_id=primary["id"] if primary else None,
        next_target=next_target(primary, request=request),
        context_fingerprint=projection["fingerprint"],
        versions=projection["versions"],
        local_revision=request.local_revision,
        line_bindings=projection["line_bindings"],
        configuration=checked["configuration"],
        evaluation_scope=checked["evaluation_scope"],
    )


def recent_requirement(request, checked):
    requirements = [
        r
        for r in checked["configuration"]["requirements"]
        if r["system_id"] == request.scope.system_id
    ]
    undone = {edit.operation_id for edit in request.recent_edits if edit.kind == "undo"}
    ordered = sorted(
        enumerate(request.recent_edits),
        key=lambda pair: pair[1].sequence if pair[1].sequence is not None else pair[0],
    )
    for _, edit in reversed(ordered):
        if edit.kind in {"undo", "dismiss"} or edit.operation_id in undone:
            continue
        affected = {
            change.id for change in edit.changes if change.kind in {"devices", "requirements"}
        }
        for requirement in requirements:
            if (
                affected.intersection({requirement["id"], requirement.get("device_id")})
                or edit.requirement_id == requirement["id"]
                or (edit.device_id and edit.device_id == requirement.get("device_id"))
            ):
                return requirement["id"]
    return None
