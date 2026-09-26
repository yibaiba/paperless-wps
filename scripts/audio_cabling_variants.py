"""Source-backed attributes for EG conference-system cabling."""

from knowledge_seed import source
from variant_seed import VariantUpdate

SHEET = "AI智能纪要"
SYSTEM = "EG系列会议系统"


def variant_updates() -> tuple[VariantUpdate, ...]:
    cables = tuple(
        VariantUpdate(
            ref=source(SHEET, row, model),
            systems=(SYSTEM,),
            evidence=f"{SHEET} 第{row}行产品名称明确线缆长度。",
            attributes=(
                {"key": "length", "kind": "quantity", "value": str(length), "unit": "m"},
                {"key": "catalog_role", "kind": "text", "value": "会议延长线", "unit": ""},
            ),
        )
        for row, model, length in (
            (21, "BE6/10", 10),
            (22, "BE6/20", 20),
            (23, "BE6/30", 30),
            (24, "BE6/50", 50),
        )
    )
    floor_box = VariantUpdate(
        ref=source(SHEET, 25, "BE-206P"),
        systems=(SYSTEM,),
        evidence=f"{SHEET} 第25行产品名称明确为6芯会议单元地插盒。",
        attributes=(
            {"key": "core_count", "kind": "number", "value": "6", "unit": ""},
            {"key": "catalog_role", "kind": "text", "value": "会议单元地插盒", "unit": ""},
        ),
    )
    return (*cables, floor_box)
