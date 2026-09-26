import hashlib

ATTRIBUTE_LABELS = {
    "text": "文本",
    "enum": "枚举",
    "number": "数值",
    "quantity": "数量",
}


def variant_document(variant):
    product = variant["product"]
    lines = [
        f"产品型号：{product.get('model', '')}",
        f"产品名称：{product.get('name', '')}",
        f"产品类别：{product.get('category', '')}",
        f"品牌：{product.get('brand', '')}",
        f"具体配置：{variant.get('name', '')}",
    ]
    lines.extend(_list_lines("系列", variant.get("series")))
    lines.extend(_list_lines("功能", variant.get("functions")))
    lines.extend(_list_lines("接口", variant.get("interfaces")))
    lines.extend(_list_lines("适用系统", variant.get("systems")))
    lines.extend(_attribute_lines(variant.get("attributes", [])))
    return "\n".join(line for line in lines if not line.endswith("："))


def document_hash(document: str) -> str:
    return hashlib.sha256(document.encode("utf-8")).hexdigest()


def variant_document_record(variant):
    document = variant_document(variant)
    return dict(
        variant_id=variant["id"],
        variant_revision=variant["revision"],
        document=document,
        content_hash=document_hash(document),
    )


def _list_lines(label, values):
    return [f"{label}：{'、'.join(str(value) for value in values)}"] if values else []


def _attribute_lines(attributes):
    lines = []
    for item in sorted(attributes, key=lambda value: value["key"]):
        value = item.get("value")
        if value is None or value == [] or value == "":
            continue
        if isinstance(value, list):
            value = "、".join(str(part) for part in value)
        unit = item.get("unit") or ""
        kind = ATTRIBUTE_LABELS.get(item.get("kind"), item.get("kind", ""))
        lines.append(f"属性 {item['key']}（{kind}）：{value}{unit}")
    return lines
