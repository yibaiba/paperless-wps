"""All configuration editors use the same technical-change review policy."""

from presales.catalog_updates.impacts import affected

from ..common import Entities
from .schemas import VariantInput

TECHNICAL_FIELDS = (
    "product_id",
    "attributes",
    "series",
    "functions",
    "interfaces",
    "systems",
    "capability_ids",
    "included_items",
)


def technical_values(value):
    normalized = VariantInput.model_validate(
        {k: v for k, v in value.items() if k in VariantInput.model_fields}
    ).model_dump(mode="json")
    return {
        key: sorted(normalized[key], key=lambda item: str(item))
        if isinstance(normalized[key], list)
        else normalized[key]
        for key in TECHNICAL_FIELDS
    }


def with_revision_review(session, *, previous, incoming):
    values = incoming.model_dump(mode="json")
    if technical_values(previous) == technical_values(values):
        # Pending review is cleared by reviewed knowledge revisions, never by an
        # editor's omitted/default field or an older copy of the review metadata.
        reviews = [*values["review_requirements"], *previous.get("review_requirements", [])]
        values["review_requirements"] = list({item["id"]: item for item in reviews}.values())
        return VariantInput.model_validate(values)
    entities = Entities(session)
    product = entities.get(values["product_id"], kind="product").payload
    revised = dict(previous, **values, product=product)
    before, after = affected(session, previous), affected(session, revised)
    impact = dict(before)
    for key in ("rules", "packages", "projects"):
        impact[key] = list({item["id"]: item for item in [*before[key], *after[key]]}.values())
    reviews = [*previous.get("review_requirements", []), *impact["rules"]]
    values["review_requirements"] = list({item["id"]: item for item in reviews}.values()) or [
        dict(id="configuration_changed", name="参数变更待复核")
    ]
    entities.save(
        "catalog_impact",
        dict(
            **impact,
            actor=incoming.actor,
            evidence=incoming.evidence,
            changed_revision=previous["revision"] + 1,
        ),
    )
    return VariantInput.model_validate(values)
