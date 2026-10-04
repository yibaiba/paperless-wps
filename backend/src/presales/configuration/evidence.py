"""Compatible references to product rows or immutable material segments."""

from pydantic import Field, model_serializer, model_validator

from .common import Input, Text


class EvidenceReference(Input):
    source_id: Text | None = None
    material_id: Text | None = None
    material_revision: int | None = Field(default=None, ge=1)
    segment_id: Text | None = None
    locator: Text
    quote: Text

    @model_validator(mode="after")
    def reference_identity(self):
        material_fields = (self.material_id, self.material_revision, self.segment_id)
        if self.source_id:
            if any(value is not None for value in material_fields):
                raise ValueError("产品来源引用不能同时指定资料片段")
        elif not all(value is not None for value in material_fields):
            raise ValueError("资料引用需要资料 ID、固定修订和片段 ID")
        return self

    @model_serializer(mode="wrap")
    def existing_wire_shape(self, handler):
        return {key: value for key, value in handler(self).items() if value is not None}
