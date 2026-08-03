from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fit_engine import FITCoreEngine  # noqa: E402
from strength_fit_parser import probe_strength_messages  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe Garmin strength FIT messages without emitting file metadata."
    )
    parser.add_argument("fit_files", nargs="+", type=Path)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    samples = []
    failed = 0
    for index, path in enumerate(args.fit_files, start=1):
        sample_id = f"sample_{index}"
        try:
            archive = FITCoreEngine.parse_fit_file_raw(path)
            probe = probe_strength_messages(archive.get("raw"))
            samples.append({"sample_id": sample_id, "ok": True, "probe": probe})
        except Exception:
            failed += 1
            samples.append(
                {"sample_id": sample_id, "ok": False, "error": "fit_parse_failed"}
            )

    payload = {"probe_version": 1, "samples": samples}
    if args.compact:
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
