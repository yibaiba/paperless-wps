from presales.storage import ProductRecord

from ..extraction.workbooks import referenced_segment


def validate_evidence_refs(session, references):
    for reference in references:
        if reference.material_id:
            segment = referenced_segment(session, reference)
            if reference.locator != segment["location"] or reference.quote not in segment["text"]:
                raise ValueError("证据摘录或位置与指定资料修订的片段不一致")
            continue
        source = session.get(ProductRecord, reference.source_id)
        if not source:
            raise ValueError("证据引用的来源不存在")
        text = "\n".join(str(value) for value in source.payload.values())
        if reference.quote not in text:
            raise ValueError("证据摘录未在所选原始来源中找到，请核对原文")
