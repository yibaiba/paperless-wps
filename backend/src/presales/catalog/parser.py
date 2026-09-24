from .checks import detect_issues
from .models import ParsedCatalog, SourceProduct, SourceSheet
from .xlsx_reader import read_workbook, split_cell

HEADERS = {
    "产品型号": "model",
    "产品名称": "name",
    "品牌": "brand",
    "产品类别": "category",
    "性能描述(完整参数）": "specification",
    "性能描述(简易参数）": "short_specification",
    "招标参数(标底参数）": "tender_specification",
    "备注": "note",
    "单位": "unit",
}
PRICE_HEADERS = {
    "出厂指导价",
    "甲方指导价",
    "总包指导价",
    "项目参考价格",
    "市场参考报价",
    "最低客户报价",
}


def locate_header(sheet: SourceSheet) -> tuple[int, dict[str, str]] | None:
    rows: dict[int, dict[str, str]] = {}
    for address, value in sheet.cells.items():
        column, row = split_cell(address)
        if value in HEADERS or value in PRICE_HEADERS:
            rows.setdefault(row, {})[column] = value
    for row, labels in sorted(rows.items()):
        if {"产品型号", "产品名称", "性能描述(完整参数）"}.issubset(labels.values()):
            return row, labels
    return None


def column_index(column: str) -> int:
    result = 0
    for character in column:
        result = result * 26 + ord(character) - ord("A") + 1
    return result


def merged_value(
    sheet: SourceSheet, address: str, *, include_horizontal: bool = False
) -> tuple[str, str]:
    column, row = split_cell(address)
    for merged in sheet.merges:
        start, end = merged.split(":")
        start_col, start_row = split_cell(start)
        end_col, end_row = split_cell(end)
        in_column = start_col == end_col == column
        if include_horizontal:
            in_column = column_index(start_col) <= column_index(column) <= column_index(end_col)
        if in_column and start_row <= row <= end_row:
            return sheet.cells.get(start, ""), merged
    return sheet.cells.get(address, ""), address


def parse_product(sheet: SourceSheet, row: int, labels: dict[str, str]) -> SourceProduct | None:
    fields = {field: "" for field in HEADERS.values()}
    sources, prices = {}, {}
    for column, label in labels.items():
        value, source = merged_value(
            sheet, f"{column}{row}", include_horizontal=label in PRICE_HEADERS
        )
        if label in PRICE_HEADERS:
            prices[label] = value
            sources[f"price:{label}"] = source
        elif not fields[HEADERS[label]]:
            fields[HEADERS[label]] = value
            sources[HEADERS[label]] = source
    if not fields["model"] or fields["model"] == "产品型号":
        return None
    return SourceProduct(
        sheet=sheet.name,
        row=row,
        hidden=sheet.hidden,
        prices=prices,
        sources=sources,
        **fields,
    )


def parse_catalog(content: bytes) -> ParsedCatalog:
    sheets = read_workbook(content)
    products = []
    for sheet in sheets:
        header = locate_header(sheet)
        if header is None:
            continue
        header_row, labels = header
        rows = sorted({split_cell(address)[1] for address in sheet.cells})
        products.extend(
            product
            for row in rows
            if row > header_row
            if (product := parse_product(sheet, row, labels)) is not None
        )
    if not products:
        raise ValueError("未找到产品表头，需要产品型号、产品名称和性能描述(完整参数）列")
    return ParsedCatalog(
        products=tuple(products),
        issues=detect_issues(products),
        sheets=tuple(sheet.name for sheet in sheets),
    )
