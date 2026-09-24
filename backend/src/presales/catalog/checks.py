from collections import defaultdict

from .models import CatalogIssue, SourceProduct


def evidence(product: SourceProduct, field: str) -> dict[str, str]:
    return {
        "sheet": product.sheet,
        "range": product.sources[field],
        "model": product.model,
        "value": getattr(product, field),
    }


def compare_model(products: list[SourceProduct]) -> list[CatalogIssue]:
    issues = []
    for field, kind, title in [
        ("name", "name_difference", "同型号的名称不一致"),
        ("specification", "configuration_difference", "同型号存在不同参数或配置"),
        ("note", "note_difference", "同型号的配套或适用说明不一致"),
    ]:
        variants: dict[str, SourceProduct] = {}
        for product in products:
            value = getattr(product, field).strip()
            if value:
                variants.setdefault(value, product)
        if len(variants) > 1:
            issues.append(
                CatalogIssue(
                    kind=kind,
                    title=title,
                    description=(
                        f"{products[0].model} 有 {len(variants)} 种来源内容。"
                        "可能是配置差异、表述差异或资料冲突，需要核对。"
                    ),
                    evidence=tuple(evidence(p, field) for p in variants.values()),
                )
            )
    return issues


def detect_issues(products: list[SourceProduct]) -> tuple[CatalogIssue, ...]:
    grouped = defaultdict(list)
    for product in products:
        grouped[product.model].append(product)
    issues = [issue for records in grouped.values() for issue in compare_model(records)]
    for product in products:
        if not product.name or product.name == product.brand:
            issues.append(
                CatalogIssue(
                    kind="missing_name",
                    title="产品名称缺失或字段可能错位",
                    description=f"{product.sheet} 第 {product.row} 行疑似错位，请核对原表。",
                    evidence=(evidence(product, "model"), evidence(product, "name")),
                )
            )
    return tuple(issues)
