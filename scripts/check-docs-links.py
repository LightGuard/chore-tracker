#!/usr/bin/env python3
"""Validate relative links and heading anchors in the contributor docs."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_GLOBS = ("README.md", "docs/**/*.md", "deploy/**/*.md")
LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
SCHEME_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)


def markdown_files() -> list[Path]:
    files: set[Path] = set()
    for pattern in MARKDOWN_GLOBS:
        files.update(ROOT.glob(pattern))
    return sorted(path for path in files if path.is_file())


def heading_slugs(path: Path) -> set[str]:
    slugs: set[str] = set()
    counts: dict[str, int] = {}
    for _, heading in HEADING_PATTERN.findall(path.read_text(encoding="utf-8")):
        text = re.sub(r"`([^`]*)`", r"\1", heading)
        text = re.sub(r"<[^>]+>", "", text)
        text = text.strip().lower()
        text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
        slug = re.sub(r"\s+", "-", text)
        if not slug:
            continue
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        slugs.add(slug if count == 0 else f"{slug}-{count}")
    return slugs


def link_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and ">" in target:
        return target[1 : target.index(">")]
    return target.split()[0]


def check_file(path: Path, slugs_cache: dict[Path, set[str]]) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    for raw in LINK_PATTERN.findall(text):
        target = link_target(raw)
        if not target or target.startswith("#") or SCHEME_PATTERN.match(target):
            continue

        path_part, _, fragment = target.partition("#")
        path_part = unquote(path_part.split("?", 1)[0])
        if not path_part:
            destination = path
        elif path_part.startswith("/"):
            destination = ROOT / path_part.lstrip("/")
        else:
            destination = (path.parent / path_part).resolve()

        try:
            destination.relative_to(ROOT.resolve())
        except ValueError:
            errors.append(
                f"{path.relative_to(ROOT)}: link escapes repository: {target}"
            )
            continue

        if not destination.exists():
            errors.append(f"{path.relative_to(ROOT)}: missing link target: {target}")
            continue

        if fragment and destination.suffix == ".md":
            slugs = slugs_cache.setdefault(destination, heading_slugs(destination))
            if fragment not in slugs:
                errors.append(
                    f"{path.relative_to(ROOT)}: missing anchor #{fragment} in "
                    f"{destination.relative_to(ROOT)}"
                )
    return errors


def main() -> int:
    files = markdown_files()
    if not files:
        print("No Markdown files found.", file=sys.stderr)
        return 1

    slugs_cache: dict[Path, set[str]] = {}
    errors: list[str] = []
    checked = 0
    for path in files:
        links = [
            link
            for link in LINK_PATTERN.findall(path.read_text(encoding="utf-8"))
            if not link_target(link).startswith("#")
            and not SCHEME_PATTERN.match(link_target(link))
        ]
        checked += len(links)
        errors.extend(check_file(path, slugs_cache))

    if errors:
        print("Documentation link check failed:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    print(
        f"Documentation link check passed: {checked} relative links in "
        f"{len(files)} Markdown files."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
