import re
from collections import defaultdict
from hashlib import sha256

from sqlalchemy import select

from presales.configuration.common import Entities
from presales.configuration.models import SourceLink
from presales.storage import CatalogImport, ProductRecord

from .schemas import SourceScopePreview, TemplateProfileWrite

SPACE = re.compile(r"\s+")


def normalize_header(value: str) -> str:
    return SPACE.sub("", value).casefold()


def header_fingerprint(values: list[str]) -> str:
    normalized = "\0".join(normalize_header(value) for value in values)
    return sha256(normalized.encode()).hexdigest()


class TemplateProfiles:
    def __init__(self, session):
        self.session = session
        self.entities = Entities(session)

    def list(self):
        return self.entities.list("wps_template_profile")

    def get(self, profile_id: str, revision: int | None = None):
        record = self.entities.get(profile_id, kind="wps_template_profile")
        if revision is None or revision == record.revision:
            return {"id": record.id, "revision": record.revision, **record.payload}
        item = next(
            (item for item in self.entities.history(profile_id) if item["revision"] == revision),
            None,
        )
        if item is None:
            raise ValueError("模板修订不存在")
        return {"id": profile_id, **item}

    def save(self, data: TemplateProfileWrite, *, actor: str):
        created_by = actor
        current = None
        if data.profile_id:
            current = self.get(data.profile_id)
            created_by = current["created_by"]
        scope = data.catalog_scope.model_dump() if data.catalog_scope else None
        if scope is None and current:
            scope = current.get("catalog_scope")
        if scope:
            self._validate_scope(scope)
        payload = {
            "schema_version": 2 if scope else 1,
            "name": data.name,
            "sheet_selector": data.sheet_selector,
            "header_row": data.header_row,
            "field_columns": data.field_columns,
            "managed_fields": data.managed_fields,
            "normalized_header_fingerprint": header_fingerprint(data.header_values),
            "created_by": created_by,
            "updated_by": actor,
            "catalog_scope": scope,
        }
        options = {}
        if data.profile_id:
            options = {"entity_id": data.profile_id, "expected_revision": data.expected_revision}
        return self.entities.save("wps_template_profile", payload, **options)

    def preview_scopes(self, data: SourceScopePreview):
        imports = {row.id: row for row in self.session.scalars(select(CatalogImport))}
        links = {
            row.source_id: row.variant_id for row in self.session.scalars(select(SourceLink))
        }
        records = self.session.scalars(select(ProductRecord)).all()
        by_scope = defaultdict(list)
        for record in records:
            if record.id in links:
                by_scope[(record.import_id, record.sheet)].append(record)
        items = [
            self._scope_preview(scope, rows, data, links, imports)
            for scope, rows in by_scope.items()
        ]
        items.sort(
            key=lambda item: (
                -item["matched_rows"], item["ambiguous_rows"], -item["linked_count"],
                item["filename"], item["sheet"],
            )
        )
        return {"items": items[:20], "total_rows": len(data.rows)}

    def _validate_scope(self, scope):
        imported = self.session.get(CatalogImport, scope["import_id"])
        if not imported or scope["sheet"] not in imported.sheets:
            raise ValueError("产品来源范围不存在，请重新选择")
        linked = self.session.scalar(
            select(SourceLink.source_id)
            .join(ProductRecord, ProductRecord.id == SourceLink.source_id)
            .where(
                ProductRecord.import_id == scope["import_id"],
                ProductRecord.sheet == scope["sheet"],
            )
            .limit(1)
        )
        if not linked:
            raise ValueError("该产品来源范围尚无已确认配置")

    @staticmethod
    def _scope_preview(scope, records, data, links, imports):
        matched, ambiguous = 0, 0
        for row in data.rows:
            variants = {
                links[record.id]
                for record in records
                if _row_matches(record, row.model, row.name)
            }
            if variants:
                matched += 1
            if len(variants) > 1:
                ambiguous += 1
        import_id, sheet = scope
        imported = imports[import_id]
        return {
            "import_id": import_id,
            "filename": imported.filename,
            "sheet": sheet,
            "matched_rows": matched,
            "ambiguous_rows": ambiguous,
            "linked_count": len(records),
        }


def _row_matches(record, model, name):
    normalized_model = model.casefold().strip()
    normalized_name = name.casefold().strip()
    if normalized_model:
        return record.model.casefold().strip() == normalized_model
    return bool(normalized_name) and record.name.casefold().strip() == normalized_name
