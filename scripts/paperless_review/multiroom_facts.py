"""Record inclusions and version warnings without inventing replacement products."""

from presales.catalog_updates.batches import Batches
from presales.catalog_updates.schemas import CreateBatch, Decision, EditBatch, RowEdit
from presales.configuration.catalog.schemas import VariantInput
from presales.configuration.catalog.service import CatalogService
from presales.configuration.common import Entities

from .multiroom import ACTOR, NOTICE, identity, reference, variant_at


def maintain_facts(session, *, document, variants):
    saved = []
    for row, name, kind, case_row in [
        (15, "随附 2.1 米 6 芯话筒线", "accessory", 154),
        (11, "内置音频采集软件", "software", 158),
        (12, "内置字幕投屏软件", "software", 159),
    ]:
        variant = variant_at(variants, "AI智能纪要", row)
        old = Entities(session).get(variant["id"], kind="variant")
        item_id = identity("included:" + str(row))
        if any(i["id"] == item_id for i in old.payload.get("included_items", [])):
            continue
        item = dict(
            id=item_id,
            name=name,
            kind=kind,
            status="draft",
            quantity=None,
            variant_id=None,
            need_keys=[],
            evidence=NOTICE
            + "包含事实有原文，独立配置与需求映射尚未确认，不自动抵扣。",
            evidence_refs=[reference(document, f"D{case_row}")],
        )
        payload = {
            **old.payload,
            "included_items": [*old.payload.get("included_items", []), item],
            "actor": ACTOR,
        }
        saved.append(
            CatalogService(session).save_variant(
                VariantInput.model_validate(payload),
                entity_id=old.id,
                expected_revision=old.revision,
            )
        )
    affected = [
        v
        for v in variants
        if any(s["sheet"] == "第三方配套产品" for s in v["source_details"])
        and any(word in v["product"]["name"] for word in ("充电", "平板"))
    ]
    if not affected:
        raise ValueError("找不到需要核对版本说明的平板/充电配置")
    evidence = (
        NOTICE
        + "\n"
        + "\n".join(
            reference(document, cell, sheet="版本更新说明")["quote"]
            for cell in ("D5", "D8")
        )
    )
    batches = Batches(session)
    batch = batches.create(
        CreateBatch(
            name="V2.2 平板代际与充电设备变更核对",
            variant_ids=[v["id"] for v in affected],
            actor=ACTOR,
            evidence=evidence,
            operation_id="multiroom-v22-product-review:" + document["digest"],
        )
    )
    if all(r.get("decision") is None for r in batch["rows"]):
        batches.edit(
            batch["id"],
            EditBatch(
                expected_revision=batch["revision"],
                operation_id="multiroom-v22-product-defer:" + document["digest"],
                edits=[
                    RowEdit(
                        row_id=r["id"],
                        decision=Decision(
                            action="defer",
                            actor=ACTOR,
                            evidence=evidence
                            + "旧 C5 没有当前配置；传输充电柜与新增传输软件不可混同，"
                            "不应用供货状态。",
                        ),
                    )
                    for r in batch["rows"]
                ],
            ),
        )
    return dict(
        inclusions=[v["id"] for v in saved], product_update_batch_id=batch["id"]
    )
