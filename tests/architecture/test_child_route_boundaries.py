"""Architecture tests for child-facing route persistence boundaries."""

from __future__ import annotations

import ast
import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "chore_tracker"
ROUTE_PATH = PACKAGE_ROOT / "api" / "routes" / "child_views.py"

FORBIDDEN_IMPORT_PREFIXES = (
    "sqlite3",
    "chore_tracker.adapters",
    "chore_tracker.config",
)
FORBIDDEN_CALLS = {
    "connect",
    "transaction",
    "execute",
    "executemany",
    "executescript",
    "cursor",
    "commit",
    "rollback",
}
SQL_STATEMENT = re.compile(
    r"^\\s*(SELECT|INSERT|UPDATE|DELETE|REPLACE|CREATE|ALTER|DROP|PRAGMA)\\b",
    re.IGNORECASE,
)


def _route_tree() -> ast.Module:
    """Parse the child-facing route module without importing application code."""
    return ast.parse(ROUTE_PATH.read_text(encoding="utf-8"), filename=str(ROUTE_PATH))


def test_child_routes_do_not_import_persistence_or_database_configuration() -> None:
    """Child-facing routes depend on application services, not concrete storage."""
    violations = []
    for node in ast.walk(_route_tree()):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module] if node.module else []
        else:
            continue

        for module in modules:
            if any(
                module == prefix or module.startswith(prefix + ".")
                for prefix in FORBIDDEN_IMPORT_PREFIXES
            ):
                violations.append(
                    f"{ROUTE_PATH.relative_to(PACKAGE_ROOT.parent)}:{node.lineno}: "
                    f"forbidden import {module!r}"
                )

    assert not violations, (
        "Child-facing routes must delegate persistence to application services "
        "and adapters:\\n- " + "\\n- ".join(violations)
    )


def test_child_routes_do_not_execute_sql_or_manage_transactions() -> None:
    """SQL execution and transaction boundaries belong outside API routes."""
    violations = []
    for node in ast.walk(_route_tree()):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in FORBIDDEN_CALLS:
                violations.append(
                    f"{ROUTE_PATH.relative_to(PACKAGE_ROOT.parent)}:{node.lineno}: "
                    f"forbidden persistence call .{node.func.attr}()"
                )

        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if SQL_STATEMENT.match(node.value):
                violations.append(
                    f"{ROUTE_PATH.relative_to(PACKAGE_ROOT.parent)}:{node.lineno}: "
                    "SQL statement embedded in API route"
                )

    assert not violations, (
        "Child-facing routes must delegate persistence to application services "
        "and adapters:\\n- " + "\\n- ".join(violations)
    )


def test_child_routes_do_not_resolve_database_paths() -> None:
    """Database configuration is resolved at the application composition boundary."""
    violations = []
    for node in ast.walk(_route_tree()):
        if isinstance(node, ast.Name) and node.id in {"get_settings", "database_path"}:
            violations.append(
                f"{ROUTE_PATH.relative_to(PACKAGE_ROOT.parent)}:{node.lineno}: "
                f"route references {node.id!r}"
            )
        elif isinstance(node, ast.Attribute) and node.attr == "database_path":
            violations.append(
                f"{ROUTE_PATH.relative_to(PACKAGE_ROOT.parent)}:{node.lineno}: "
                "route accesses database_path"
            )

    assert not violations, (
        "Child-facing routes must receive configured application services rather "
        "than resolve database settings:\\n- " + "\\n- ".join(violations)
    )
