from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError


def pdf_material(*, name, content):
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise ValueError("PDF 已加密，请提供可提取文字的文件")
        pages = [
            dict(location=f"第 {i + 1} 页", text=page.extract_text() or "")
            for i, page in enumerate(reader.pages)
        ]
    except PdfReadError as error:
        raise ValueError("PDF 文件无法解析，请检查文件是否完整") from error
    empty = [p["location"] for p in pages if not p["text"].strip()]
    if empty:
        raise ValueError(
            "以下页面未提取到文字，可能是扫描件或空白页，未执行 AI：" + "、".join(empty)
        )
    if not pages:
        raise ValueError("PDF 没有可用页面")
    return dict(name=name, format="pdf", segments=pages)


def text_material(data):
    paragraphs = [p.strip() for p in data.text.split("\n\n") if p.strip()]
    return dict(
        name=data.name,
        format="text",
        segments=[dict(location=f"段落 {i + 1}", text=p) for i, p in enumerate(paragraphs)],
    )
