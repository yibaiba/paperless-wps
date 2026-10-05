from pydantic import Field

from ..common import Text
from .schemas import CheckRequest


class PreviewRequest(CheckRequest):
    expected_revision: int = Field(ge=0)
    cleanup_allocations: bool = False


class ApplyPreview(PreviewRequest):
    fingerprint: Text
