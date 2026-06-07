#!/usr/bin/env python3
"""V8.11B: 为 V8.3/V8.4 之前导入的旧活动回填 hr_curve / speed_curve / cadence_curve / hr_zone_distribution。

契约:
- §2.1 全链路可追溯:曲线来源 = FIT 文件(FITCoreEngine → MetricsResolver)
- §8 canonical 只写可信数据:曲线由 Resolver 从 FIT 原始记录提取
- §6 shadow_diff 隔离:不触发 shadow_diff 审计逻辑

用法: python3 scripts/backfill_curves_v811.py
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
import time
from pathlib import Path

# 确保项目根在 sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from fit_engine import FITCoreEngine
from metrics_resolver import MetricsResolver
from profile_backend import DB_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backfill_v811")


def _safe_float(v):
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe_int(v):
    try:
        if v is None:
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def _compute_hr_zone_distribution(hr_curve: list, max_hr: float | None) -> str | None:
    """V8.4: 从 hr_curve 和 max_hr 计算 Z1-Z5 心率区间分布。"""
    if not hr_curve or not max_hr or max_hr < 30:
        return None
    z1 = z2 = z3 = z4 = z5 = 0
    for h in hr_curve:
        if h is None or h <= 0:
            continue
        ratio = float(h) / float(max_hr)
        if ratio < 0.6:
            z1 += 1
        elif ratio < 0.7:
            z2 += 1
        elif ratio < 0.8:
            z3 += 1
        elif ratio < 0.9:
            z4 += 1
        else:
            z5 += 1
    return json.dumps(
        {"Z1": z1, "Z2": z2, "Z3": z3, "Z4": z4, "Z5": z5},
        ensure_ascii=False,
    )


def backfill_activity(conn: sqlite3.Connection, activity_id: int, file_path: str) -> dict:
    """解析单个 FIT 文件并返回需要回填的曲线数据。"""
    result = {
        "hr_curve": None,
        "speed_curve": None,
        "cadence_curve": None,
        "hr_zone_distribution": None,
    }

    fp = Path(file_path).expanduser().resolve()
    if not fp.is_file():
        return result

    try:
        raw_archive = FITCoreEngine.parse_fit_file_raw(str(fp))
        resolver = MetricsResolver()
        resolved = resolver.resolve(
            raw_archive.get("raw") or {},
            raw_archive.get("meta") or {},
        )

        # hr_curve
        if resolved.get("hr_curve"):
            result["hr_curve"] = json.dumps(resolved["hr_curve"], ensure_ascii=False)

        # speed_curve
        if resolved.get("speed_curve"):
            result["speed_curve"] = json.dumps(resolved["speed_curve"], ensure_ascii=False)

        # cadence_curve (V8.3)
        if resolved.get("cadence_curve"):
            cad_vals = [c for c in resolved["cadence_curve"] if c is not None and c > 0]
            if cad_vals:
                result["cadence_curve"] = json.dumps(cad_vals, ensure_ascii=False)

        # hr_zone_distribution (V8.4)
        hr_list = resolved.get("hr_curve") or []
        max_hr_val = _safe_int(
            (raw_archive.get("meta") or {}).get("max_heart_rate")
        ) or _safe_int(
            (raw_archive.get("raw") or {}).get("max_hr")
        )
        hr_zone_json = _compute_hr_zone_distribution(hr_list, max_hr_val)
        if hr_zone_json:
            result["hr_zone_distribution"] = hr_zone_json

    except Exception as exc:
        logger.warning("  活动 %d 解析失败: %s", activity_id, exc)

    return result


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # 查找需要回填的活动
    rows = conn.execute(
        "SELECT id, filename, file_path, sport_type, max_hr FROM activities "
        "WHERE deleted_at IS NULL AND "
        "(hr_curve IS NULL OR hr_curve = '' OR hr_curve = '[]' OR "
        "speed_curve IS NULL OR speed_curve = '' OR speed_curve = '[]') "
        "ORDER BY id"
    ).fetchall()

    total = len(rows)
    logger.info("需要回填的活动数: %d", total)

    updated = 0
    failed = 0
    skipped_no_file = 0

    for idx, row in enumerate(rows):
        aid = row["id"]
        fname = row["filename"]
        fpath = row["file_path"]

        if not fpath or not Path(fpath).expanduser().resolve().is_file():
            skipped_no_file += 1
            if idx < 10 or idx % 50 == 0:
                logger.info("  [%d/%d] id=%d %s → 跳过(文件不存在)", idx + 1, total, aid, fname)
            continue

        curves = backfill_activity(conn, aid, fpath)

        # 构建 UPDATE SQL
        set_clauses = []
        params = []
        for col in ["hr_curve", "speed_curve", "cadence_curve", "hr_zone_distribution"]:
            if curves.get(col) is not None:
                set_clauses.append(f"{col} = ?")
                params.append(curves[col])

        if not set_clauses:
            failed += 1
            logger.info("  [%d/%d] id=%d %s → 无曲线数据", idx + 1, total, aid, fname)
            continue

        params.append(aid)
        sql = f"UPDATE activities SET {', '.join(set_clauses)} WHERE id = ?"
        conn.execute(sql, params)
        conn.commit()

        updated += 1
        if idx < 20 or idx % 50 == 0:
            has = []
            for c in ["hr_curve", "speed_curve", "cadence_curve", "hr_zone_distribution"]:
                if curves.get(c):
                    has.append(c)
            logger.info(
                "  [%d/%d] id=%d %s → 已回填 %s",
                idx + 1, total, aid, fname, ", ".join(has),
            )

    conn.close()
    logger.info(
        "回填完成: 更新=%d, 无数据=%d, 文件不存在=%d, 总计=%d",
        updated, failed, skipped_no_file, total,
    )


if __name__ == "__main__":
    start = time.time()
    main()
    elapsed = time.time() - start
    logger.info("耗时: %.1f 秒", elapsed)
