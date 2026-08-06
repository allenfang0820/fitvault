#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from packaging_diagnostics import GARMIN_FIT_SDK_EXPECTED_VERSION  # noqa: E402


@dataclass(frozen=True)
class ContractTarget:
    path: str
    pattern: str
    replacement_template: str

    def replacement(self, version: str) -> str:
        return self.replacement_template.format(version=version)


TARGETS: tuple[ContractTarget, ...] = (
    ContractTarget(
        "requirements.txt",
        r"(?m)^garmin-fit-sdk==[^\s]+$",
        "garmin-fit-sdk=={version}",
    ),
    ContractTarget(
        "constraints.txt",
        r"(?m)^garmin-fit-sdk==[^\s]+$",
        "garmin-fit-sdk=={version}",
    ),
    ContractTarget(
        "docs/打包前必读.md",
        r"(?m)^- `garmin-fit-sdk == [^`]+`$",
        "- `garmin-fit-sdk == {version}`",
    ),
    ContractTarget(
        "docs/V2.0_macOS打包契约摘要.md",
        r"garmin-fit-sdk==[0-9][0-9A-Za-z.+!-]*",
        "garmin-fit-sdk=={version}",
    ),
    ContractTarget(
        "docs/V2.0_Windows打包继续审查清单.md",
        r"garmin-fit-sdk==[0-9][0-9A-Za-z.+!-]*",
        "garmin-fit-sdk=={version}",
    ),
)


def _sync_target(root: Path, target: ContractTarget, *, version: str, write: bool) -> dict[str, Any]:
    path = root / target.path
    if not path.exists():
        return {"path": target.path, "ok": False, "error": "missing"}
    original = path.read_text(encoding="utf-8")
    replacement = target.replacement(version)
    updated, count = re.subn(target.pattern, replacement, original)
    if count == 0:
        return {"path": target.path, "ok": False, "error": "pattern_not_found"}
    changed = updated != original
    if write and changed:
        path.write_text(updated, encoding="utf-8")
    return {"path": target.path, "ok": not changed, "changed": changed, "matches": count}


def sync_contract(
    root: str | Path = PROJECT_ROOT,
    *,
    version: str = GARMIN_FIT_SDK_EXPECTED_VERSION,
    write: bool = False,
) -> dict[str, Any]:
    resolved_root = Path(root)
    files = [_sync_target(resolved_root, target, version=version, write=write) for target in TARGETS]
    ok = all(item.get("ok") is True or (write and item.get("changed") is True) for item in files)
    if write:
        files = [_sync_target(resolved_root, target, version=version, write=False) for target in TARGETS]
        ok = all(item.get("ok") is True for item in files)
    return {
        "ok": ok,
        "package": "garmin-fit-sdk",
        "expected_version": version,
        "write": write,
        "files": files,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check or sync Garmin FIT SDK version contract files.")
    parser.add_argument("--root", default=str(PROJECT_ROOT), help="Project root. Defaults to this repository.")
    parser.add_argument("--version", default=GARMIN_FIT_SDK_EXPECTED_VERSION, help="Expected garmin-fit-sdk version.")
    parser.add_argument("--write", action="store_true", help="Rewrite contract files to the expected version.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = sync_contract(args.root, version=args.version, write=args.write)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        status = "ok" if result["ok"] else "mismatch"
        print(f"garmin-fit-sdk contract {status}: expected {result['expected_version']}")
        for item in result["files"]:
            marker = "ok" if item.get("ok") else "changed" if item.get("changed") else "error"
            detail = item.get("error") or f"matches={item.get('matches', 0)}"
            print(f"- {marker}: {item['path']} ({detail})")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
