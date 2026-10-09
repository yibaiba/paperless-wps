import ast
from pathlib import Path

SOURCE = Path(__file__).parents[1] / "src" / "presales"
CORE_PACKAGES = ("configuration", "quotation", "catalog_updates", "pricing")


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def package_imports(package: str) -> dict[Path, set[str]]:
    return {
        path: imported_modules(path)
        for path in (SOURCE / package).rglob("*.py")
    }


def test_core_domains_do_not_import_list_or_wps_adapters():
    violations = []
    for package in CORE_PACKAGES:
        for path, modules in package_imports(package).items():
            banned = sorted(
                module for module in modules
                if module.startswith(("presales.lists", "presales.wps"))
            )
            if banned:
                violations.append((str(path.relative_to(SOURCE)), banned))
    assert violations == []


def test_catalog_updates_does_not_call_http_route_modules():
    violations = [
        (
            str(path.relative_to(SOURCE)),
            sorted(module for module in modules if module.endswith(".routes")),
        )
        for path, modules in package_imports("catalog_updates").items()
        if any(module.endswith(".routes") for module in modules)
    ]
    assert violations == []


def test_application_primitives_do_not_depend_on_business_domains():
    allowed = {"presales.storage"}
    violations = []
    for path, modules in package_imports("application").items():
        unexpected = sorted(
            module for module in modules
            if module.startswith("presales.") and module not in allowed
        )
        if unexpected:
            violations.append((str(path.relative_to(SOURCE)), unexpected))
    assert violations == []
