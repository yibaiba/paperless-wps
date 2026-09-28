from sqlalchemy import select

from presales.configuration.catalog.service import CatalogService
from presales.configuration.common import Entities
from presales.configuration.definitions.service import Definitions
from presales.configuration.knowledge.evaluator import scope_matches
from presales.configuration.models import Entity, Revision
from presales.configuration.projects.calculation.inspections import effective_environment
from presales.configuration.projects.candidates import candidate_results
from presales.configuration.projects.schemas import CandidateRequest
from presales.storage import ProductRecord, Project

from .catalog_snapshot import DraftCatalog


def page(items, request):
    end = request.offset + request.limit
    return dict(
        items=items[request.offset : end],
        total=len(items),
        offset=request.offset,
        next_offset=end if end < len(items) else None,
    )


def saved_revision(repository, *, project_id, revision=None):
    if revision is None:
        return repository.get(project_id)
    record = repository.record(project_id)
    if record is None:
        raise ValueError("项目没有保存版本")
    result = Definitions(repository.session).revision(record.id, revision, kind="project")
    project = repository.session.get(Project, project_id)
    return dict(result, name=project.name)


def search_projects(session, request):
    saved = {
        r.payload["project_id"]: r
        for r in session.scalars(select(Entity).where(Entity.kind == "project"))
    }
    if request.project_id:
        record = saved.get(request.project_id)
        if record is None:
            raise ValueError("项目没有保存版本")
        revisions = session.scalars(
            select(Revision)
            .where(Revision.entity_id == record.id)
            .order_by(Revision.revision.desc())
        )
        return page(
            [
                dict(
                    project_id=request.project_id,
                    revision=r.revision,
                    created_at=r.created_at.isoformat(),
                    actor=r.payload["configuration"].get("actor"),
                    quotation_total=(r.payload.get("quotation_output") or {}).get("total"),
                )
                for r in revisions
            ],
            request,
        )
    records = session.scalars(select(Project).order_by(Project.created_at.desc(), Project.id))
    return page(
        [
            dict(id=p.id, name=p.name, revision=saved[p.id].revision if p.id in saved else 0)
            for p in records
            if request.query.casefold() in p.name.casefold()
        ],
        request,
    )


def search_catalog(session, request):
    if bool(request.draft_id) != bool(request.requirement_id):
        raise ValueError("候选查询需要同时指定草稿和角色需求 ID")
    results = []
    if request.draft_id:
        draft = Entities(session).get(request.draft_id, kind="list_draft").payload
        configuration = draft["configuration"]
        role = next(
            (r for r in configuration["requirements"] if r["id"] == request.requirement_id), None
        )
        if role is None:
            raise ValueError("角色需求不存在")
        system = next(s for s in configuration["systems"] if s["id"] == role["system_id"])
        data = CandidateRequest(
            calculation_version=configuration["calculation_version"],
            system=system["kind"],
            role=role["role"],
            environment=effective_environment(system, role)[0],
            system_definition_id=system.get("definition_id", ""),
            role_id=role.get("role_id", ""),
            knowledge_package_id=system.get("knowledge_package_id", ""),
            definition_snapshot_id=configuration.get("definition_snapshot_id"),
            knowledge_snapshot_id=configuration.get("knowledge_snapshot_id"),
            include_all=request.include_other_products,
        )
        results = candidate_results(
            data, session=session, catalog=DraftCatalog(session, draft["catalog_snapshot_id"])
        )
    else:
        results = [
            dict(variant=v, status="unassessed", evidence=[])
            for v in CatalogService(session).variants()
        ]
    filtered = [r for r in results if matches(r["variant"], request.query)]
    summaries = [
        dict(
            variant_id=r["variant"]["id"],
            name=r["variant"]["name"],
            model=r["variant"]["product"]["model"],
            revision=r["variant"]["revision"],
            status=r["status"],
            evidence=r["evidence"],
            sources=[
                dict(id=s["id"], sheet=s.get("sheet"), row=s.get("row"))
                for s in r["variant"]["source_details"]
            ],
        )
        for r in filtered
    ]
    return page(summaries, request)


def matches(variant, query):
    text = " ".join(str(v) for v in (variant["name"], variant["product"], variant["attributes"]))
    return all(term.casefold() in text.casefold() for term in query.split())


def catalog_detail(session, *, variant_id, draft_id=None):
    draft = Entities(session).get(draft_id, kind="list_draft").payload if draft_id else None
    catalog = (
        DraftCatalog(session, draft["catalog_snapshot_id"]) if draft else CatalogService(session)
    )
    variants = catalog.variants(ids=[variant_id])
    if not variants:
        raise ValueError("产品配置不存在")
    variant = variants[0]
    knowledge = Entities(session).list("knowledge")
    if draft_id:
        data = draft["configuration"]
        knowledge = data["knowledge_snapshot"]
        selected = next((d for d in data["devices"] if d["variant_id"] == variant_id), None)
        if selected:
            variant = selected["variant_snapshot"]
    sources = [session.get(ProductRecord, identity) for identity in variant["source_ids"]]
    return dict(
        variant=variant,
        sources=[dict(id=s.id, import_id=s.import_id, **s.payload) for s in sources],
        knowledge=[k for k in knowledge if scope_matches(variant, k["selector"])],
    )


def systems(session, request):
    definitions = Entities(session).list("system_definition")
    known = {d["name"] for d in definitions}
    legacy = sorted(
        {
            k["system"]
            for k in Entities(session).list("knowledge")
            if k.get("system") and k["system"] not in known
        }
    )
    return dict(
        **page(definitions, request),
        packages=[
            dict(
                id=p["id"],
                name=p["name"],
                revision=p["revision"],
                status=p["status"],
                system_definition_id=p["system_definition_id"],
            )
            for p in Entities(session).list("knowledge_package")
        ],
        unmapped_systems=[dict(name=s, status="unmapped") for s in legacy],
    )
