from dataclasses import dataclass


@dataclass(frozen=True)
class SourceProduct:
    sheet: str
    row: int
    model: str
    name: str
    brand: str
    category: str
    specification: str
    short_specification: str
    tender_specification: str
    note: str
    unit: str
    prices: dict[str, str]
    sources: dict[str, str]
    hidden: bool


@dataclass(frozen=True)
class SourceSheet:
    name: str
    hidden: bool
    cells: dict[str, str]
    merges: tuple[str, ...]


@dataclass(frozen=True)
class CatalogIssue:
    kind: str
    title: str
    description: str
    evidence: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class ParsedCatalog:
    products: tuple[SourceProduct, ...]
    issues: tuple[CatalogIssue, ...]
    sheets: tuple[str, ...]
