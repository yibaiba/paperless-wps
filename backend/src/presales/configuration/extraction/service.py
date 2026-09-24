from pydantic import TypeAdapter
from sqlalchemy import select

from presales.catalog.repository import CatalogRepository
from presales.rules.repository import RuleConflict
from presales.storage import now

from ..catalog.schemas import LinkInput, ProductInput, VariantInput
from ..catalog.service import CatalogService
from ..common import Entities
from ..knowledge.schemas import KnowledgeInput
from ..models import ExtractionJob
from .context import selected_context, validate_scope
from .schemas import Draft, ModelOutput


def job_view(record):
    return dict(
        id=record.id,
        status=record.status,
        error=record.error,
        updated_at=record.updated_at,
        **record.payload,
    )


class ExtractionService:
    def __init__(self, session):
        self.session = session
        self.entities = Entities(session)
        self.catalog = CatalogService(session)

    def enqueue(self, data):
        segments = []
        for source_id in data.source_ids:
            product = CatalogRepository(self.session).product(source_id)
            if not product:
                raise ValueError("选择的产品来源不存在")
            segments.append(
                dict(
                    location=f"{product['sheet']} 第 {product['row']} 行",
                    source_id=source_id,
                    text=TypeAdapter(dict).dump_json(product).decode(),
                )
            )
        for material_id in data.material_ids:
            material = self.entities.get(material_id, kind="material")
            segments.extend({**s, "material_id": material_id} for s in material.payload["segments"])
        if not segments:
            raise ValueError("请选择产品来源或上传资料")
        self.catalog.validate_variant_ids(data.variant_ids)
        job = ExtractionJob(
            payload=dict(
                actor=data.actor,
                evidence=data.evidence,
                variant_ids=data.variant_ids,
                context=selected_context(self.session, data),
                segments=[dict(**s, status="queued", error="") for s in segments],
            )
        )
        self.session.add(job)
        self.session.flush()
        return job_view(job)

    def list_jobs(self):
        return [
            job_view(j)
            for j in self.session.scalars(
                select(ExtractionJob).order_by(ExtractionJob.updated_at.desc())
            )
        ]

    def retry(self, job_id):
        job = self.session.get(ExtractionJob, job_id, with_for_update=True)
        if not job or job.status not in {"failed", "interrupted"}:
            raise ValueError("仅失败或中断任务可以手动重试")
        payload = {
            **job.payload,
            "segments": [
                dict(s, status="queued", error="") if s["status"] != "completed" else s
                for s in job.payload["segments"]
            ],
        }
        job.payload, job.status, job.error = payload, "queued", ""
        job.updated_at = now()
        return job_view(job)

    def validate_draft(self, draft):
        if draft.kind == "question":
            if (
                not isinstance(draft.proposal.get("question"), str)
                or not draft.proposal["question"].strip()
            ):
                raise ValueError("待确认问题必须包含明确的问题内容")
            return draft
        if draft.target_id:
            self.entities.get(draft.target_id, kind=draft.kind)
            if draft.expected_revision < 1:
                raise ValueError("修改建议必须携带原记录版本")
        schema = {
            "product": ProductInput,
            "variant": VariantInput,
            "source_link": LinkInput,
            "knowledge": KnowledgeInput,
        }.get(draft.kind)
        if schema:
            data = schema.model_validate(draft.proposal)
            if draft.kind == "variant":
                self.entities.get(data.product_id, kind="product")
            if draft.kind == "source_link":
                self.entities.get(data.variant_id, kind="variant")
                for item in data.items:
                    if not CatalogRepository(self.session).product(item.source_id):
                        raise ValueError("草稿引用的产品来源不存在")
            if draft.kind == "knowledge":
                self.catalog.validate_variant_ids(
                    data.selector.variant_ids
                    + data.selector.exclude_variant_ids
                    + data.target_variant_ids
                )
        return draft

    def store_output(self, output, *, job_id, segment):
        result = ModelOutput.model_validate(output)
        job = self.session.get(ExtractionJob, job_id)
        for draft in result.drafts:
            if draft.quotation not in segment["text"]:
                raise ValueError("模型草稿的引文不在本段原文中，本段未确认")
            self.validate_draft(draft)
            validate_scope(draft, job.payload["context"])
            if (
                draft.kind in {"variant", "knowledge"}
                and draft.proposal.get("status", "draft") != "draft"
            ):
                raise ValueError("模型不能确认业务知识，请输出草稿状态后人工审核")
        for draft in result.drafts:
            self.entities.save(
                "draft",
                dict(
                    **draft.model_dump(mode="json"),
                    job_id=job_id,
                    location=segment["location"],
                    original=segment["text"],
                    status="pending",
                ),
            )

    def decide(self, data):
        records = [
            self.entities.get(i, kind="draft", lock=True) for i in sorted(set(data.draft_ids))
        ]
        for record in records:
            if record.payload["status"] != "pending":
                raise RuleConflict("包含已审核草稿，请刷新；本批未重复应用")
            payload = record.payload
            if data.action == "accept":
                self._accept(payload, data)
            self.entities.save(
                "draft",
                {
                    **payload,
                    "status": data.action,
                    "review_actor": data.actor,
                    "review_evidence": data.evidence,
                },
                entity_id=record.id,
                expected_revision=record.revision,
            )
        return dict(reviewed=len(records))

    def _accept(self, payload, decision):
        evidence = f"{decision.evidence}\n资料：{payload['location']}\n原文：{payload['quotation']}"
        proposal = {**payload["proposal"], "actor": decision.actor, "evidence": evidence}
        options = dict(
            entity_id=payload["target_id"], expected_revision=payload["expected_revision"]
        )
        kind = payload["kind"]
        if kind == "product":
            self.catalog.save_product(ProductInput.model_validate(proposal), **options)
        elif kind == "variant":
            self.catalog.save_variant(VariantInput.model_validate(proposal), **options)
        elif kind == "source_link":
            self.catalog.link(LinkInput.model_validate(proposal))
        elif kind == "knowledge":
            data = KnowledgeInput.model_validate(proposal)
            self.validate_draft(Draft.model_validate({k: payload[k] for k in Draft.model_fields}))
            self.entities.save("knowledge", data, **options)
        else:
            raise ValueError("待确认问题不能直接发布，请补充依据并编辑为结构化草稿")
