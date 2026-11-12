"""Architecture rules expressed with ArchUnitPython.

The custom AST tests continue to enforce route-level SQL and transaction rules.
These tests complement them by checking package dependencies and application cycles.
"""

from __future__ import annotations

from pathlib import Path

from archunitpython import CheckOptions, assert_passes, project_files

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "chore_tracker"
API_ROOT = SOURCE_ROOT / "api"
APPLICATION_ROOT = SOURCE_ROOT / "application"
ADAPTERS_ROOT = SOURCE_ROOT / "adapters"

# Keep empty selectors from silently turning an architecture rule into a pass.
# Clear the dependency graph between rules so each assertion observes current files.
CHECK_OPTIONS = CheckOptions(
    allow_empty_tests=False,
    clear_cache=True,
    ignore_type_checking_imports=False,
)


def _layer_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def test_architecture_layer_directories_are_present() -> None:
    """Fail clearly if a package is renamed or removed without updating the rules."""
    for layer_root in (API_ROOT, APPLICATION_ROOT, ADAPTERS_ROOT):
        assert _layer_files(layer_root), (
            f"Expected Python modules under architecture layer: {layer_root}"
        )


def test_api_does_not_depend_on_persistence_adapters() -> None:
    """HTTP routes delegate use cases and must not couple directly to persistence."""
    rule = (
        project_files("src")
        .in_folder("**/api/**")
        .should_not()
        .depend_on_files()
        .in_folder("**/adapters/**")
        .because("routes delegate persistence to application services")
    )
    assert_passes(rule, CHECK_OPTIONS)


def test_application_does_not_depend_on_api() -> None:
    """Application use cases must remain independent of HTTP delivery concerns."""
    rule = (
        project_files("src")
        .in_folder("**/application/**")
        .should_not()
        .depend_on_files()
        .in_folder("**/api/**")
        .because("application code must not depend on HTTP delivery code")
    )
    assert_passes(rule, CHECK_OPTIONS)


def test_application_does_not_depend_on_adapters() -> None:
    """Application use cases must not depend on concrete persistence implementations."""
    rule = (
        project_files("src")
        .in_folder("**/application/**")
        .should_not()
        .depend_on_files()
        .in_folder("**/adapters/**")
        .because("application code must not depend on persistence implementations")
    )
    assert_passes(rule, CHECK_OPTIONS)


def test_application_does_not_import_http_or_sqlite_modules() -> None:
    """Keep HTTP frameworks and SQLite implementation details out of
    application code."""
    for forbidden_module in ("fastapi", "starlette", "sqlite3"):
        rule = (
            project_files("src")
            .in_folder("**/application/**")
            .should_not()
            .depend_on_external_modules()
            .matching(forbidden_module)
            .because(
                "application services must remain independent of HTTP frameworks "
                "and concrete SQLite APIs"
            )
        )
        assert_passes(rule, CHECK_OPTIONS)


def test_adapters_do_not_depend_on_api() -> None:
    """Infrastructure adapters must not import HTTP delivery-layer code."""
    rule = (
        project_files("src")
        .in_folder("**/adapters/**")
        .should_not()
        .depend_on_files()
        .in_folder("**/api/**")
        .because("adapters must not depend on HTTP delivery code")
    )
    assert_passes(rule, CHECK_OPTIONS)


def test_application_package_has_no_circular_dependencies() -> None:
    """Prevent application modules from forming dependency cycles."""
    rule = (
        project_files("src")
        .in_folder("**/application/**")
        .should()
        .have_no_cycles()
        .because("application dependencies must remain acyclic")
    )
    assert_passes(rule, CHECK_OPTIONS)
