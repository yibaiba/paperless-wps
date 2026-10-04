"""Review explicit quantities from the largest multi-room workbook example."""

from dataclasses import dataclass

from presales.configuration.catalog.service import CatalogService
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.rules.calculation import digest
from presales.storage import ProductRecord

from .content import ReviewSources, digest_ref
from .maintenance import proposal
from .reconciliation import current_records

SHEET = "AI智能纪要"
ACTOR = "多会议室清单数量复核（2026-10-04）"
MARKER = "【2026-10-04多会议室数量复核】"


@dataclass(frozen=True, kw_only=True)
class QuantityReview:
    parents: tuple[int, ...]
    target: int
    mode: str
    factor: str
    quantity_source: str
    quantity_key: str
    quotes: tuple[tuple[int, str], ...]
    explanation: str


QUANTITIES = {
    "eg.conference-unit-splitter": QuantityReview(
        parents=(15, 16, 17, 18, 19, 20),
        target=26,
        mode="per_capacity",
        factor="2",
        quantity_source="device_quantity",
        quantity_key="",
        quotes=((26, "一个分线盒可带两只会议话筒"),),
        explanation="每个会议系统内符合规则的单元数量合计后按两只/盒向上取整；"
        "不同会议系统不共用数量。",
    ),
    "minutes.audio-capture-box": QuantityReview(
        parents=(6,),
        target=11,
        mode="per_unit",
        factor="1",
        quantity_source="environment",
        quantity_key="audio_capture_room_count",
        quotes=((11, "内置音频采集软件，采集音频使用，按会议室数量配置"),),
        explanation="按已明确需要音频采集的会议室数量计量，不推断全部房间都启用采集。",
    ),
    "minutes.subtitle-box": QuantityReview(
        parents=(6,),
        target=12,
        mode="per_unit",
        factor="1",
        quantity_source="environment",
        quantity_key="subtitle_room_count",
        quotes=((12, "内置字幕投屏软件，字幕实时投屏使用，按会议室数量配置"),),
        explanation="按已明确启用字幕投屏的会议室数量计量，不推断全部房间都需字幕投屏。",
    ),
}


def validate_scope(rule, *, sources, review):
    expected = dict(
        status="confirmed",
        calculation_scope="system",
        mode=review.mode,
        factor=review.factor,
        quantity_source=review.quantity_source,
        quantity_key=review.quantity_key,
    )
    if any(rule.get(key) != value for key, value in expected.items()):
        raise ValueError("原有公式或确认范围已变化，请重新核对：" + rule["need_key"])
    parents = {sources.get(SHEET, row)[0] for row in review.parents}
    targets = [sources.get(SHEET, review.target)[0]]
    if set(rule["selector"]["variant_ids"]) != parents or rule["target_variant_ids"] != targets:
        raise ValueError("原有配置范围已变化，请重新核对：" + rule["need_key"])


def reviewed_quantity(rule, sources):
    review = QUANTITIES[rule["need_key"]]
    validate_scope(rule, sources=sources, review=review)
    references = [sources.evidence(SHEET, row, quote=quote) for row, quote in review.quotes]
    references = [*rule.get("evidence_refs", []), *references]
    references = list({digest_ref(ref): ref for ref in references}.values())
    evidence = rule["evidence"].split(MARKER)[0].rstrip() + "\n" + MARKER + review.explanation
    return KnowledgeInput.model_validate(
        dict(
            rule,
            actor=ACTOR,
            schema_version=2,
            quantity_review="confirmed",
            quantity_evidence="；".join(quote for _, quote in review.quotes),
            evidence=evidence,
            evidence_refs=references,
        )
    ).model_dump(mode="json")


def build_minutes_plan(session):
    current = current_records(session)
    sources = ReviewSources(CatalogService(session).variants())
    changes = []
    guards = {}
    for key in QUANTITIES:
        matches = [
            (i, r)
            for i, r in current.items()
            if r["kind"] == "knowledge" and r["payload"].get("need_key") == key
        ]
        if len(matches) != 1:
            raise ValueError("待复核关系不唯一：" + key)
        identity, record = matches[0]
        payload = reviewed_quantity(record["payload"], sources)
        changes.append(proposal(current, kind="knowledge", identity=identity, payload=payload))
        for reference in payload["evidence_refs"]:
            source = session.get(ProductRecord, reference["source_id"])
            if source is None:
                raise ValueError("复核依据不存在：" + reference["source_id"])
            guards[source.id] = digest(source.payload)
    return dict(changes=changes, fingerprint=digest(changes), source_guards=guards)
