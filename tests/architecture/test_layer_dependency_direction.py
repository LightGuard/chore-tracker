"""Static architecture checks for application and persistence dependencies."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "chore_tracker"
APPLICATION_ROOT = PACKAGE_ROOT / "application"
ADAPTERS_ROOT = PACKAGE_ROOT / "adapters"

HTTP_IMPORT_PREFIXES = ("fastapi", "starlette")
API_IMPORT_PREFIX = "chore_tracker.api"
SQLITE_IMPORT_PREFIX = "sqlite3"
ADAPTER_IMPORT_PREFIX = "chore_tracker.adapters"


def _python_modules(root: Path) -> list[Path]:
    """Discover all Python modules in a layer, including future additions."""
    return sorted(root.rglob("*.py"))


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module, node.lineno


def _has_prefix(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def _violations(root: Path, forbidden_prefixes: tuple[str, ...]) -> list[str]:
    violations: list[str] = []
    for path in _python_modules(root):
        for module, line in _imports(path):
            if any(_has_prefix(module, prefix) for prefix in forbidden_prefixes):
                violations.append(
                    f"{path.relative_to(PACKAGE_ROOT.parent)}:{line}: "
                    f"module imports forbidden dependency {module!r}"
                )
    return violations


def test_application_services_are_independent_of_http_and_sqlite() -> None:
    """Application services must not know HTTP framework or concrete storage APIs."""
    modules = _python_modules(APPLICATION_ROOT)
    assert modules, (
        f"No Python modules found under application package: {APPLICATION_ROOT}"
    )

    violations = _violations(
        APPLICATION_ROOT,
        (
            *HTTP_IMPORT_PREFIXES,
            SQLITE_IMPORT_PREFIX,
            ADAPTER_IMPORT_PREFIX,
            API_IMPORT_PREFIX,
        ),
    )
    assert not violations, (
        "Application-layer dependency violations found. Application services may "
        "depend on application-owned contracts and the standard library, but not "
        "HTTP frameworks, API modules, sqlite3, or concrete adapters:\n- "
        + "\n- ".join(violations)
    )


def test_persistence_adapters_do_not_depend_on_http_or_api_layers() -> None:
    """Persistence adapters may use SQLite, but must not depend on HTTP/API code."""
    modules = _python_modules(ADAPTERS_ROOT)
    assert modules, f"No Python modules found under adapters package: {ADAPTERS_ROOT}"

    violations = _violations(ADAPTERS_ROOT, (*HTTP_IMPORT_PREFIXES, API_IMPORT_PREFIX))
    assert not violations, (
        "Persistence-layer dependency violations found. Adapters may use SQLite "
        "and database-specific types, but must not depend on HTTP frameworks or "
        "API modules:\n- " + "\n- ".join(violations)
    )
