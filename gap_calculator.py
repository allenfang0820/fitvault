"""
GAP (Grade Adjusted Pace) — 等效坡度配速计算模块

契约依据:
  §2.1  基于 FIT records 的 altitude / distance / heart_rate / timestamp 序列
  §4.5  输出进入 ai_context 层,不直接写入 canonical DB
  §6    所有输出字段可追溯至 FIT record
  §8.1  单文件模块,不建 package

纯 Python 实现,无需新增 pip 依赖。
"""

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

# ── GAP 等效系数表 ────────────────────────────────────────────
# 坡度范围 → 等效配速系数
_GAP_COEFFICIENTS: list[tuple[float, float, float]] = [
    # (grade_min, grade_max, coefficient)
    (-float("inf"), -8.0, 0.90),   # 陡下坡
    (-8.0,        -3.0, 0.95),   # 缓下坡
    (-3.0,         3.0, 1.00),   # 平路
    (3.0,          8.0, 1.05),   # 缓上坡
    (8.0,  float("inf"), 1.15),   # 陡上坡
]


class GapCalculator:
    """基于海拔序列的等效坡度配速 (Grade Adjusted Pace) 计算器。

    输入: FIT record_mesgs 列表,每条含 altitude / distance / heart_rate / timestamp。
    输出: gap_curve / efficiency_curve / grade_curve / smoothed_altitude 等。"""

    def __init__(self, smooth_window: int = 5):
        """初始化 GAP 计算器。

        Args:
            smooth_window: 高程序列平滑窗口大小,默认 5,可配置。"""
        if smooth_window < 1:
            raise ValueError(f"smooth_window 必须 >= 1, 收到 {smooth_window}")
        if smooth_window % 2 == 0:
            # 偶数窗口调整为奇数,保证对称填充
            smooth_window += 1
            logger.debug("smooth_window 调整为奇数 %d", smooth_window)
        self.smooth_window = smooth_window

    # ── 公开入口 ───────────────────────────────────────────────

    def calculate(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """主计算入口。对 records 序列计算 GAP / 效率 / 坡度 / 平滑海拔。

        Args:
            records: FIT record_mesgs 列表,每条需含 altitude / distance /
                     heart_rate / timestamp。

        Returns:
            结果字典,包含 gap_curve / efficiency_curve / grade_curve /
            smoothed_altitude / source / gap_config。
        """
        if not records or len(records) < 2:
            logger.warning("GAP 计算需要至少 2 条 record,实际收到 %d 条", len(records) if records else 0)
            return self._empty_result("insufficient_records")

        # 1. 排序 & 提取有效记录
        valid = self._prepare_records(records)
        if len(valid) < 2:
            logger.warning("有效 record 不足 2 条,无法计算 GAP")
            return self._empty_result("insufficient_valid_records")

        # 2. 高程序列平滑
        raw_altitudes = [r["altitude"] for r in valid]
        smoothed = self._sliding_average(raw_altitudes, self.smooth_window)

        # 3. 逐段坡度 + GAP + 效率
        gap_curve: list[float | None] = [None]  # 第 0 条无前驱
        efficiency_curve: list[float | None] = [None]
        grade_curve: list[float | None] = [None]

        for i in range(1, len(valid)):
            prev = valid[i - 1]
            curr = valid[i]

            delta_h = smoothed[i] - smoothed[i - 1]
            delta_d = curr["distance"] - prev["distance"]

            if self._is_valid_number(delta_d) and delta_d > 0:
                grade_pct = (delta_h / delta_d) * 100.0
            else:
                grade_pct = 0.0
            grade_curve.append(round(grade_pct, 2))

            raw_pace = self._compute_pace(prev, curr)
            if raw_pace is not None and raw_pace > 0:
                coeff = self._lookup_coefficient(grade_pct)
                gap = raw_pace * coeff
                gap_curve.append(round(gap, 2))
            else:
                gap_curve.append(None)

            hr = curr.get("heart_rate")
            if gap_curve[-1] is not None and self._is_valid_number(hr) and hr > 0:
                efficiency_curve.append(round(gap_curve[-1] / hr, 4))
            else:
                efficiency_curve.append(None)

        return {
            "gap_curve": gap_curve,
            "efficiency_curve": efficiency_curve,
            "grade_curve": grade_curve,
            "smoothed_altitude": [round(v, 1) for v in smoothed],
            "source": "resolver",
            "gap_config": {
                "smooth_window": self.smooth_window,
                "coefficients": [
                    {"range": f"{lo}~{hi}", "coefficient": c}
                    for lo, hi, c in _GAP_COEFFICIENTS
                ],
            },
        }

    # ── 内部方法 ───────────────────────────────────────────────

    @staticmethod
    def _is_valid_number(v: Any) -> bool:
        return isinstance(v, (int, float)) and not math.isnan(v)

    @staticmethod
    def _safe_timestamp(record: dict[str, Any]) -> Any:
        return record.get("timestamp")

    def _prepare_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """排序并按字段完整性过滤 records。"""
        # 按 timestamp 排序
        sorted_records = sorted(
            records,
            key=lambda r: self._safe_timestamp(r) or 0,
        )
        valid: list[dict[str, Any]] = []
        for r in sorted_records:
            alt = r.get("altitude")
            dist = r.get("distance")
            ts = self._safe_timestamp(r)
            if (
                self._is_valid_number(alt)
                and self._is_valid_number(dist)
                and ts is not None
            ):
                valid.append({
                    "altitude": float(alt),
                    "distance": float(dist),
                    "heart_rate": r.get("heart_rate"),
                    "timestamp": ts,
                })
        return valid

    @staticmethod
    def _sliding_average(values: list[float], window: int) -> list[float]:
        """滑动平均平滑序列。边界用原值填充,保持长度一致。

        Args:
            values: 原始值序列。
            window: 窗口大小(奇数)。

        Returns:
            平滑后的序列,长度与输入一致。
        """
        n = len(values)
        if n == 0:
            return []
        half = window // 2
        result: list[float] = []
        for i in range(n):
            start = i - half
            end = i + half + 1
            # 窗口不足时用边界值填充
            win = []
            for j in range(start, end):
                if j < 0:
                    win.append(values[0])
                elif j >= n:
                    win.append(values[-1])
                else:
                    win.append(values[j])
            result.append(sum(win) / len(win))
        return result

    @staticmethod
    def _lookup_coefficient(grade_pct: float) -> float:
        """根据坡度百分比查找 GAP 等效系数。"""
        for lo, hi, coeff in _GAP_COEFFICIENTS:
            if lo <= grade_pct < hi:
                return coeff
        return 1.0  # fallback (不应到达)

    @staticmethod
    def _compute_pace(
        prev: dict[str, Any],
        curr: dict[str, Any],
    ) -> float | None:
        """根据相邻两条 record 计算原始配速 (sec/km)。

        pace = Δtime / Δdistance (unit: sec/m) → * (1000/60) for min/km
        返回 None 表示数据不足以计算配速。
        """
        delta_d = curr["distance"] - prev["distance"]
        ts_prev = GapCalculator._safe_timestamp(prev)
        ts_curr = GapCalculator._safe_timestamp(curr)

        if not (
            GapCalculator._is_valid_number(delta_d)
            and delta_d > 0.1
            and ts_prev is not None
            and ts_curr is not None
        ):
            return None

        delta_t = (ts_curr - ts_prev).total_seconds()
        if delta_t <= 0:
            return None

        # sec/m → sec/km
        pace_sec_per_km = delta_t / delta_d
        return pace_sec_per_km

    @staticmethod
    def _empty_result(reason: str) -> dict[str, Any]:
        """返回空结果(数据不足/异常时的降级输出)。"""
        return {
            "gap_curve": [],
            "efficiency_curve": [],
            "grade_curve": [],
            "smoothed_altitude": [],
            "source": "resolver",
            "gap_config": {
                "smooth_window": 0,
                "coefficients": [],
            },
            "_gap_error": reason,
        }
