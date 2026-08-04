#!/usr/bin/env python3
"""Normalize the release tag used by package builders."""

from __future__ import annotations

import argparse
import re


_RELEASE_VERSION_PATTERN = re.compile(r"^(?:v)?(\d+\.\d+\.\d+)$")


def normalize_release_version(value: str) -> str:
    """Return a numeric ``major.minor.patch`` version from a release tag."""
    raw = str(value or "").strip()
    match = _RELEASE_VERSION_PATTERN.fullmatch(raw)
    if not match:
        raise ValueError(
            "发布 tag 必须是 v<major>.<minor>.<patch>，例如 v2.0.0；"
            f"当前值为 {raw or '<empty>'!r}"
        )
    return match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize a FitVault release tag.")
    parser.add_argument("--tag", required=True, help="Git tag, for example v2.0.0")
    args = parser.parse_args()
    print(normalize_release_version(args.tag))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
