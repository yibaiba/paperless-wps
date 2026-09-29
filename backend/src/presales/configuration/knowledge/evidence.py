from presales.storage import ProductRecord


def validate_evidence_refs(session, references):
    for reference in references:
        source = session.get(ProductRecord, reference.source_id)
        if not source:
            raise ValueError("证据引用的来源不存在")
        text = "\n".join(str(value) for value in source.payload.values())
        if reference.quote not in text:
            raise ValueError("证据摘录未在所选原始来源中找到，请核对原文")
