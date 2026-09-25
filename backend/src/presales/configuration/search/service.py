from collections.abc import Iterable

from sqlalchemy import select

from presales.storage import now

from ..catalog.service import CatalogService
from ..models import SearchDocument, SearchIndexJob
from .documents import variant_document_record

SEMANTIC_RECALL_LIMIT = 50


def job_view(record):
    return dict(
        id=record.id,
        status=record.status,
        error=record.error,
        updated_at=record.updated_at,
        **record.payload,
    )


class SearchIndexService:
    def __init__(self, session, settings_store):
        self.session = session
        self.settings_store = settings_store

    def status(self):
        settings = self.settings_store.read()
        variants = self._confirmed_variants()
        records = {
            record.variant_id: record
            for record in self.session.scalars(select(SearchDocument))
        }
        counts = dict(total=len(variants), indexed=0, stale=0, pending=0, failed=0)
        for variant in variants:
            document = variant_document_record(variant)
            state = self._document_status(records.get(variant["id"]), document, settings)
            counts[state] += 1
        return dict(
            **counts,
            configured=settings is not None,
            model=settings.embedding_model if settings else "",
            dimensions=settings.embedding_dimensions if settings else None,
        )

    def enqueue(self):
        settings = self._require_settings()
        active = self.session.scalar(
            select(SearchIndexJob.id).where(SearchIndexJob.status.in_({"queued", "running"}))
        )
        if active:
            raise ValueError("已有智能索引任务正在排队或执行")
        total = len(self._confirmed_variants())
        if total == 0:
            raise ValueError("尚无已确认产品配置，不能建立智能索引")
        job = SearchIndexJob(
            payload=dict(
                total=total,
                completed=0,
                skipped=0,
                embedding_model=settings.embedding_model,
                reranker_model=settings.reranker_model,
                embedding_dimensions=settings.embedding_dimensions,
            )
        )
        self.session.add(job)
        self.session.flush()
        return job_view(job)

    def jobs(self):
        rows = self.session.scalars(
            select(SearchIndexJob).order_by(SearchIndexJob.updated_at.desc())
        )
        return [job_view(row) for row in rows]

    def retry(self, job_id):
        job = self.session.get(SearchIndexJob, job_id, with_for_update=True)
        if not job or job.status not in {"failed", "interrupted"}:
            raise ValueError("仅失败或中断的智能索引任务可以重试")
        job.status, job.error = "queued", ""
        job.updated_at = now()
        job.payload = {**job.payload, "completed": 0, "skipped": 0}
        return job_view(job)

    def _confirmed_variants(self):
        return [
            variant
            for variant in CatalogService(self.session).variants()
            if variant["status"] == "confirmed"
        ]

    def _require_settings(self):
        settings = self.settings_store.read()
        if settings is None:
            raise ValueError("尚未配置智能检索模型")
        return settings

    @staticmethod
    def _document_status(record, document, settings):
        if record is None:
            return "pending"
        if settings is None:
            return "stale"
        same_version = (
            record.content_hash == document["content_hash"]
            and record.embedding_model == settings.embedding_model
            and record.embedding_dimensions == settings.embedding_dimensions
        )
        if not same_version:
            return "stale"
        if record.error:
            return "failed"
        return "indexed" if record.embedding is not None else "pending"


class SearchIndexer:
    def __init__(self, session_factory, settings_store, provider_factory):
        self.session_factory = session_factory
        self.settings_store = settings_store
        self.provider_factory = provider_factory

    def process(self, job_id):
        settings = self._settings_for_job(job_id)
        with self.session_factory() as session:
            variants = [
                variant
                for variant in CatalogService(session).variants()
                if variant["status"] == "confirmed"
            ]
        records = [variant_document_record(variant) for variant in variants]
        for batch in _batches(records, settings.batch_size):
            self._process_batch(job_id, batch, settings)
        with self.session_factory() as session:
            job = session.get(SearchIndexJob, job_id)
            job.status, job.updated_at = "completed", now()
            session.commit()

    def _settings_for_job(self, job_id):
        settings = self.settings_store.read()
        if settings is None:
            raise ValueError("智能检索设置已被删除，索引任务无法继续")
        with self.session_factory() as session:
            job = session.get(SearchIndexJob, job_id)
            expected = job.payload["embedding_model"]
        if expected != settings.embedding_model:
            raise ValueError("索引任务使用的模型配置已变化，请重新创建任务")
        return settings

    def _process_batch(self, job_id, batch, settings):
        with self.session_factory() as session:
            existing = {
                item.variant_id: item
                for item in session.scalars(
                    select(SearchDocument).where(
                        SearchDocument.variant_id.in_([item["variant_id"] for item in batch])
                    )
                )
            }
            pending = [
                item
                for item in batch
                if not _is_current(existing.get(item["variant_id"]), item, settings)
            ]
        try:
            vectors = (
                self.provider_factory().embeddings([item["document"] for item in pending])
                if pending
                else []
            )
        except Exception as error:
            self._record_failures(pending, settings, error=error)
            raise
        with self.session_factory() as session:
            for item, vector in zip(pending, vectors, strict=True):
                record = session.get(SearchDocument, item["variant_id"]) or SearchDocument(
                    variant_id=item["variant_id"]
                )
                record.variant_revision = item["variant_revision"]
                record.content_hash = item["content_hash"]
                record.document = item["document"]
                record.embedding_model = settings.embedding_model
                record.embedding_dimensions = settings.embedding_dimensions
                record.embedding = vector
                record.error = ""
                record.updated_at = now()
                session.add(record)
            job = session.get(SearchIndexJob, job_id)
            job.payload = {
                **job.payload,
                "completed": job.payload["completed"] + len(pending),
                "skipped": job.payload["skipped"] + len(batch) - len(pending),
            }
            job.updated_at = now()
            session.commit()

    def _record_failures(self, pending, settings, *, error):
        message = str(error) if type(error) is ValueError else type(error).__name__
        with self.session_factory() as session:
            for item in pending:
                record = session.get(SearchDocument, item["variant_id"]) or SearchDocument(
                    variant_id=item["variant_id"]
                )
                record.variant_revision = item["variant_revision"]
                record.content_hash = item["content_hash"]
                record.document = item["document"]
                record.embedding_model = settings.embedding_model
                record.embedding_dimensions = settings.embedding_dimensions
                record.embedding = None
                record.error = message
                record.updated_at = now()
                session.add(record)
            session.commit()


class SemanticCandidateSearch:
    def __init__(self, session, settings_store, provider_factory):
        self.session = session
        self.settings_store = settings_store
        self.provider_factory = provider_factory

    def search(self, query, variants, *, limit):
        if self.session.bind.dialect.name != "postgresql":
            raise ValueError("智能查找需要 PostgreSQL pgvector，当前数据库不支持")
        settings = self.settings_store.read()
        if settings is None:
            raise ValueError("尚未配置智能检索模型")
        query_vector = self.provider_factory().embeddings([query])[0]
        current = {item["variant_id"]: item for item in map(variant_document_record, variants)}
        rows = self._nearest(query_vector, settings, list(current))
        rows = [row for row in rows if current[row.variant_id]["content_hash"] == row.content_hash]
        if not rows:
            raise ValueError("没有可用的最新产品索引，请先在产品整理中建立索引")
        scores = self.provider_factory().rerank(query, [row.document for row in rows])
        ranked = sorted(zip(rows, scores, strict=True), key=lambda item: item[1], reverse=True)
        return [
            dict(
                variant_id=row.variant_id,
                rank=index,
                score=score,
                embedding_model=settings.embedding_model,
                reranker_model=settings.reranker_model,
                document_revision=row.variant_revision,
            )
            for index, (row, score) in enumerate(ranked[:limit], start=1)
        ]

    def _nearest(self, query_vector, settings, variant_ids):
        distance = SearchDocument.embedding.cosine_distance(query_vector)
        statement = (
            select(SearchDocument)
            .where(
                SearchDocument.variant_id.in_(variant_ids),
                SearchDocument.embedding_model == settings.embedding_model,
                SearchDocument.embedding_dimensions == settings.embedding_dimensions,
                SearchDocument.embedding.is_not(None),
                SearchDocument.error == "",
            )
            .order_by(distance)
            .limit(SEMANTIC_RECALL_LIMIT)
        )
        return list(self.session.scalars(statement))


def _is_current(record, item, settings):
    return bool(
        record
        and not record.error
        and record.content_hash == item["content_hash"]
        and record.embedding_model == settings.embedding_model
        and record.embedding_dimensions == settings.embedding_dimensions
        and record.embedding is not None
    )


def _batches(items: list[dict], size: int) -> Iterable[list[dict]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]
