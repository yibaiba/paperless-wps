from collections import defaultdict

from sqlalchemy import select

from presales.configuration.catalog.matching import (
    MATCH_FIELDS,
    canonical,
    difference_fields,
    record_view,
)
from presales.configuration.catalog.service import CatalogService
from presales.storage import CatalogImport, ProductRecord

TECHNICAL = {
    "specification",
    "short_specification",
    "tender_specification",
    "unit",
    "brand",
    "model",
}


def classify(differences):
    fields = set(differences)
    if not fields:
        return "unchanged"
    if fields <= {"prices"}:
        return "prices"
    return "specification" if fields & TECHNICAL else "information"


def source_view(record):
    return dict(id=record.id, import_id=record.import_id, **record_view(record))


def candidates(source, *, variants, records):
    results = []
    for variant in variants:
        old = [records[s] for s in variant["source_ids"] if s in records]
        if not old:
            continue
        compared = [(difference_fields(source, record_view(r)), r) for r in old]
        differences, closest = min(compared, key=lambda pair: len(pair[0]))
        results.append(
            dict(
                variant_id=variant["id"],
                variant_revision=variant["revision"],
                name=variant["name"],
                classification=classify(differences),
                baseline_conflict=len(
                    {canonical({k: r.payload.get(k) for k in MATCH_FIELDS}) for r in old}
                )
                > 1,
                baselines=[dict(source=source_view(r), differences=d) for d, r in compared],
                differences=[
                    dict(
                        field=f,
                        before=closest.payload.get(f),
                        after=source.get(f),
                        before_cells=closest.payload.get("sources", {}),
                        after_cells=source.get("sources", {}),
                    )
                    for f in differences
                ],
                baseline=source_view(closest),
            )
        )
    return results


def build_rows(session, request):
    variants = CatalogService(session).variants()
    if request.variant_ids:
        selected = set(request.variant_ids)
        if selected - {v["id"] for v in variants}:
            raise ValueError("所选配置不存在")
        variants = [v for v in variants if v["id"] in selected]
    if not request.import_id:
        return [
            dict(
                id=v["id"],
                source=None,
                classification="manual",
                candidates=[],
                variant_id=v["id"],
                state="pending",
                decision=None,
            )
            for v in variants
        ]
    for identity in (request.import_id, request.baseline_import_id):
        if identity and session.get(CatalogImport, identity) is None:
            raise ValueError("对比工作簿不存在")
    if request.import_id == request.baseline_import_id:
        raise ValueError("新版与对比基准不能是同一次导入")
    baseline_query = select(ProductRecord)
    if request.baseline_import_id:
        baseline_query = baseline_query.where(ProductRecord.import_id == request.baseline_import_id)
    else:
        baseline_query = baseline_query.where(ProductRecord.import_id != request.import_id)
    records = {r.id: r for r in session.scalars(baseline_query)}
    by_model = defaultdict(list)
    for variant in variants:
        by_model[variant["product"]["model"]].append(variant)
    rows = []
    for record in session.scalars(
        select(ProductRecord).where(ProductRecord.import_id == request.import_id)
    ):
        if request.sheets and record.sheet not in request.sheets:
            continue
        options = candidates(record_view(record), variants=by_model[record.model], records=records)
        if request.variant_ids and not options:
            continue
        category = (
            "unmatched"
            if len(options) > 1 or any(c["baseline_conflict"] for c in options)
            else options[0]["classification"]
            if options
            else "new"
        )
        rows.append(
            dict(
                id=record.id,
                source=source_view(record),
                candidates=options,
                classification=category,
                variant_id="",
                state="pending",
                decision=None,
            )
        )
    return rows
