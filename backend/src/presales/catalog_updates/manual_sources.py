"""Immutable, explicitly authored sources; these records are not Excel imports."""

from presales.configuration.common import Entities
from presales.storage import CatalogImport, ProductRecord


def create_manual_source(session, *, variant, decision, identities, update_batch_id):
    product = Entities(session).get(variant["product_id"], kind="product").payload
    batch_id, source_id = identities
    batch = CatalogImport(
        id=batch_id,
        filename="人工资料（非 Excel） · " + variant["name"],
        digest="manual:" + source_id,
        sheets=["人工资料"],
        record_count=1,
        issue_count=0,
    )
    specification = decision.manual_specification or "\n".join(
        f"{a['key']}：{a['value'] if a['value'] is not None else '未知'} {a['unit']}"
        for a in variant["attributes"]
    )
    payload = dict(
        model=product["model"],
        name=product["name"],
        brand=product["brand"],
        category=product["category"],
        sheet="人工资料",
        row=1,
        hidden=False,
        specification=specification,
        short_specification="",
        tender_specification="",
        note=decision.evidence,
        unit=decision.manual_unit,
        prices={},
        sources={},
        source_kind="manual",
        provenance=dict(
            actor=decision.actor,
            evidence=decision.evidence,
            update_batch_id=update_batch_id,
            variant_revision=variant["revision"],
        ),
    )
    session.add(batch)
    session.flush()
    session.add(
        ProductRecord(
            id=source_id,
            import_id=batch_id,
            model=product["model"],
            name=product["name"],
            sheet="人工资料",
            payload=payload,
        )
    )
    session.flush()
    return dict(id=source_id, import_id=batch_id, **payload)
