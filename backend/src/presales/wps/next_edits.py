from presales.configuration.projects.planning.next_edits import NextEditContext, next_edit_options

from .business import workbook_projection
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
    catalog = sync.lists.repository.catalog.variants()
    sources = {
        v["id"]: [
            s["id"]
            for s in v["source_details"]
            if all(s.get(key) == value for key, value in catalog_scope.items())
        ]
        for v in catalog
    }
    context = NextEditContext(
        repository=sync.lists.repository,
        configuration=checked["configuration"],
        proposal_id=projection["fingerprint"],
        deployment="independent",
        allowed_sources=sources,
        query=request.query,
        selected_variant_id=request.selected_variant_id or "",
        selected_source_id=request.selected_source_id or "",
    )
    options, questions = next_edit_options(
        context, checked, system_id=scope.system_id, requirement_id=scope.requirement_id
    )
    items = [
        project_next_edit(option, request=request, profile=profile, projection=projection)
        for option in options
        if option["changes"]
    ]
    dismissed = {e.suggestion_id for e in request.recent_edits if e.kind in ("undo", "dismiss")}
    items = [item for item in items if item["id"] not in dismissed]
    return dict(
        items=items,
        issues=[*questions, *sync._issues(checked)],
        context_fingerprint=projection["fingerprint"],
        versions=projection["versions"],
        local_revision=request.local_revision,
        line_bindings=projection["line_bindings"],
        configuration=checked["configuration"],
    )
