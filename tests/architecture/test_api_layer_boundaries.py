"""Static architecture checks for the HTTP/API layer.

These checks intentionally inspect source rather than importing application modules,
so they remain deterministic and do not require a database.
"""

from __future__ import annotations

import ast
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2] / "src" / "chore_tracker" / "api"
FORBIDDEN_IMPORT_PREFIXES = (
    "sqlite3",
    "chore_tracker.adapters",
)
SQL_EXECUTION_METHODS = {"execute", "executemany", "executescript"}
TRANSACTION_METHODS = {"begin", "commit", "rollback"}


def _python_modules() -> list[Path]:
    """Return every Python module below the API package."""
    return sorted(API_ROOT.rglob("*.py"))


def _imported_modules(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                yield node.module, node.lineno


def _violations(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    violations: list[str] = []

    for module, line in _imported_modules(tree):
        if any(
            module == prefix or module.startswith(prefix + ".")
            for prefix in FORBIDDEN_IMPORT_PREFIXES
        ):
            violations.append(
                f"{path.relative_to(API_ROOT.parent.parent)}:{line}: "
                f"API module imports forbidden persistence dependency {module!r}"
            )

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        method = node.func.attr
        if method in SQL_EXECUTION_METHODS:
            violations.append(
                f"{path.relative_to(API_ROOT.parent.parent)}:{node.lineno}: "
                f"API module executes SQL through .{method}()"
            )
        elif method in TRANSACTION_METHODS:
            violations.append(
                f"{path.relative_to(API_ROOT.parent.parent)}:{node.lineno}: "
                f"API module manages a database transaction through .{method}()"
            )

    return violations


def test_api_modules_do_not_own_persistence_or_transactions() -> None:
    """Routes handle HTTP concerns and delegate persistence to application code."""
    modules = _python_modules()
    assert modules, f"No Python modules found under API package: {API_ROOT}"

    violations = [
        violation
        for path in modules
        for violation in _violations(path)
    ]
    assert not violations, (
        "API architecture violations found. Move persistence and transaction "
        "responsibilities out of API modules:\n- " + "\n- ".join(violations)
    )
