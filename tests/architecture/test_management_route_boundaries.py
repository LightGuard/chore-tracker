"""Architecture tests for family-member and chore management routes.

These routes are HTTP adapters. Persistence configuration, SQL, row mapping, and
transaction boundaries belong in application services and persistence adapters.
The checks inspect source so they do not need a running database.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "chore_tracker"
ROUTE_ROOT = PACKAGE_ROOT / "api" / "routes"
MANAGEMENT_ROUTES = ("family_members.py", "chores.py")

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


def _route_trees() -> list[tuple[Path, ast.Module]]:
    """Parse the management route modules under test."""
    parsed = []
    for filename in MANAGEMENT_ROUTES:
        path = ROUTE_ROOT / filename
        parsed.append(
            (path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        )
    return parsed


def test_management_routes_do_not_import_persistence_or_database_configuration() -> None:
    """Routes must not know about concrete persistence or database configuration."""
    violations = []
    for path, tree in _route_trees():
        for node in ast.walk(tree):
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
                        f"{path.relative_to(PACKAGE_ROOT.parent)}:{node.lineno}: "
                        f"forbidden import {module!r}"
                    )

    assert not violations, (
        "Management routes must depend on application services, not persistence "
        "adapters or database configuration:\\n- " + "\\n- ".join(violations)
    )


def test_management_routes_do_not_execute_sql_or_manage_transactions() -> None:
    """All SQL execution and transaction handling must live outside API routes."""
    violations = []
    for path, tree in _route_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in FORBIDDEN_CALLS:
                    violations.append(
                        f"{path.relative_to(PACKAGE_ROOT.parent)}:{node.lineno}: "
                        f"forbidden persistence call .{node.func.attr}()"
                    )

            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if SQL_STATEMENT.match(node.value):
                    violations.append(
                        f"{path.relative_to(PACKAGE_ROOT.parent)}:{node.lineno}: "
                        "SQL statement embedded in API route"
                    )

    assert not violations, (
        "Management routes must delegate persistence to application services "
        "and adapters:\\n- " + "\\n- ".join(violations)
    )


def test_management_routes_do_not_resolve_database_paths() -> None:
    """Database settings are resolved at the composition boundary, not in routes."""
    violations = []
    for path, tree in _route_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in {
                "get_settings",
                "database_path",
            }:
                violations.append(
                    f"{path.relative_to(PACKAGE_ROOT.parent)}:{node.lineno}: "
                    f"route references {node.id!r}"
                )
            elif isinstance(node, ast.Attribute) and node.attr == "database_path":
                violations.append(
                    f"{path.relative_to(PACKAGE_ROOT.parent)}:{node.lineno}: "
                    "route accesses database_path"
                )

    assert not violations, (
        "Management routes must receive configured application services rather "
        "than resolve database settings:\\n- " + "\\n- ".join(violations)
    )
