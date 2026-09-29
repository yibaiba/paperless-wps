from pydantic import Field

from ..common import Input, Text


class ManualEdits(Input):
    requirements: list[Text] = Field(default_factory=list)
    accessory_allocations: list[Text] = Field(default_factory=list)
    included_allocations: list[Text] = Field(default_factory=list)
