import re
from hashlib import sha256

from presales.configuration.common import Entities

from .schemas import TemplateProfileWrite

SPACE = re.compile(r"\s+")


def normalize_header(value: str) -> str:
    return SPACE.sub("", value).casefold()


def header_fingerprint(values: list[str]) -> str:
    normalized = "\0".join(normalize_header(value) for value in values)
    return sha256(normalized.encode()).hexdigest()


class TemplateProfiles:
    def __init__(self, session):
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
        if data.profile_id:
            current = self.get(data.profile_id)
            created_by = current["created_by"]
        payload = {
            "schema_version": 1,
            "name": data.name,
            "sheet_selector": data.sheet_selector,
            "header_row": data.header_row,
            "field_columns": data.field_columns,
            "managed_fields": data.managed_fields,
            "normalized_header_fingerprint": header_fingerprint(data.header_values),
            "created_by": created_by,
            "updated_by": actor,
        }
        options = {}
        if data.profile_id:
            options = {"entity_id": data.profile_id, "expected_revision": data.expected_revision}
        return self.entities.save("wps_template_profile", payload, **options)
