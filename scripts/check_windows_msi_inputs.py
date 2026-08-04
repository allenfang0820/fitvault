#!/usr/bin/env python3
"""Fail early when Windows WiX inputs contain non-ASCII paths or XML text."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def _non_ascii(value: str) -> bool:
    return any(ord(char) > 127 for char in value)


def check_publish_tree(publish_dir: Path) -> list[str]:
    problems: list[str] = []
    if not publish_dir.is_dir():
        return [f"publish directory does not exist: {publish_dir}"]
    for root, dirs, files in os.walk(publish_dir):
        root_path = Path(root)
        for name in [*dirs, *files]:
            rel = (root_path / name).relative_to(publish_dir).as_posix()
            if _non_ascii(rel):
                problems.append(f"non-ASCII publish path: {rel}")
    return problems


def check_wix_files(wix_files: list[Path]) -> list[str]:
    problems: list[str] = []
    for wix_file in wix_files:
        if not wix_file.is_file():
            problems.append(f"WiX source does not exist: {wix_file}")
            continue
        try:
            # heat.exe may emit a UTF-8 BOM; it is an encoding marker, not
            # user-facing MSI text and must not be treated as a code-page hit.
            text = wix_file.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            problems.append(f"WiX source is not valid UTF-8: {wix_file}: {exc}")
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if _non_ascii(line):
                problems.append(f"non-ASCII WiX text: {wix_file}:{line_number}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish-dir", type=Path, required=True)
    parser.add_argument("--wix-file", type=Path, action="append", required=True)
    args = parser.parse_args()

    problems = check_publish_tree(args.publish_dir)
    problems.extend(check_wix_files(args.wix_file))
    if problems:
        print("Windows MSI input audit failed:")
        for problem in problems:
            print(f" - {problem}")
        return 1
    print("Windows MSI input audit passed: publish paths and WiX sources are ASCII-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
