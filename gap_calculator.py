"""
GAP (Grade Adjusted Pace) — 等效坡度配速计算模块

契约依据:
  §2.1  基于 FIT records 的 altitude / distance / heart_rate / timestamp 序列
  §4.5  输出进入 ai_context 层,不直接写入 canonical DB
  §6    所有输出字段可追溯至 FIT record
  §8.1  单文件模块,不建 package

依赖:
  numpy + scipy(Butterworth 零相位低通滤波,消除滑动平均引入的相位滞后)
"""

import logging
import math
from typing import Any, Optional

logger = logging.getLogger(__name__)
_NUMERIC_DEPS: Optional[tuple[Any, Any, Any]] = None


def _numeric_deps() -> tuple[Any, Any, Any]:
    global _NUMERIC_DEPS
    if _NUMERIC_DEPS is None:
        import numpy as np
        from scipy.signal import butter, filtfilt

        _NUMERIC_DEPS = (np, butter, filtfilt)
    return _NUMERIC_DEPS

# ── 非线性 GAP 模型:Minnetti 能量消耗多项式拟合 ──────────────
# 已废弃阶梯式 _GAP_COEFFICIENTS,改用 _calculate_gap_speed_non_linear


class GapCalculator:
    """基于海拔序列的等效坡度配速 (Grade Adjusted Pace) 计算器。

    输入: FIT record_mesgs 列表,每条含 altitude / distance / heart_rate / timestamp。
    输出: gap_curve / efficiency_curve / grade_curve / smoothed_altitude 等。"""

    def __init__(self) -> None:
        """初始化 GAP 计算器(无状态,旧 smooth_window 已废弃,改用 Butterworth)。"""
        pass

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

        # 2. 高程序列平滑(Butterworth 零相位低通滤波)
        raw_altitudes = [r["altitude"] for r in valid]
        smoothed = self._butter_lowpass_filter(raw_altitudes)

        # 3. 提取距离与速度曲线
        distance_curve = [r["distance"] for r in valid]
        speed_curve: list[float] = []
        for i in range(len(valid)):
            if i == 0:
                speed_curve.append(0.0)
                continue
            prev = valid[i - 1]
            curr = valid[i]
            delta_d = curr["distance"] - prev["distance"]
            ts_prev = self._safe_timestamp(prev)
            ts_curr = self._safe_timestamp(curr)
            if (
                self._is_valid_number(delta_d)
                and delta_d > 0
                and ts_prev is not None
                and ts_curr is not None
            ):
                delta_t = (ts_curr - ts_prev).total_seconds()
                if delta_t > 0:
                    speed_curve.append(delta_d / delta_t)
                else:
                    speed_curve.append(0.0)
            else:
                speed_curve.append(0.0)

        # 4. 计算整条轨迹的坡度序列(_calculate_grade_pct 来自任务 1.1)
        grade_pcts = GapCalculator._calculate_grade_pct(distance_curve, smoothed)
        grade_curve = [round(v, 2) for v in grade_pcts]

        # 5. 非线性 GAP 速度计算
        gap_curve: list[float] = []
        if len(grade_pcts) == len(speed_curve):
            for speed, grade in zip(speed_curve, grade_pcts):
                gap_speed = GapCalculator._calculate_gap_speed_non_linear(speed, grade)
                gap_curve.append(round(gap_speed, 3))
        else:
            gap_curve = [round(v, 3) for v in speed_curve]

        # 6. 提取心率曲线
        hr_curve: list[float] = [
            float(r.get("heart_rate", 0) or 0) for r in valid
        ]

        # 7. 效率曲线: EI = GAP_Speed(m/s) / HR(bpm)
        efficiency_curve: list[float] = []
        if len(gap_curve) == len(hr_curve):
            for gap_spd, hr in zip(gap_curve, hr_curve):
                if hr > 0 and gap_spd > 0:
                    ei = gap_spd / hr
                    efficiency_curve.append(round(ei, 5))
                else:
                    efficiency_curve.append(0.0)
        else:
            efficiency_curve = [0.0] * len(hr_curve)

        return {
            "gap_curve": gap_curve,
            "efficiency_curve": efficiency_curve,
            "grade_curve": grade_curve,
            "smoothed_altitude": [round(v, 1) for v in smoothed],
            "source": "resolver",
            "gap_config": {
                "filter": {
                    "type": "butterworth",
                    "cutoff": 0.05,
                    "fs": 1.0,
                    "order": 2,
                },
                "model": "minetti_non_linear",
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
    def _butter_lowpass_filter(
        data: list[float],
        cutoff: float = 0.05,
        fs: float = 1.0,
        order: int = 2,
    ) -> list[float]:
        """使用巴特沃斯低通滤波器平滑海拔数据(零相位滞后)。

        使用 scipy.signal.filtfilt 进行零相位前向+反向滤波,
        避免滑动平均在坡度点处引入的相位滞后。

        Args:
            data: 原始海拔序列(等间隔采样)。
            cutoff: 归一化截止频率(相对于 Nyquist 频率)。
            fs: 采样频率(默认 1.0 Hz,对应秒级 record)。
            order: 滤波器阶数(默认 2 阶)。

        Returns:
            平滑后的序列,长度与输入一致;数据不足时返回原序列。
        """
        if not data or len(data) < 10:
            return data

        np, butter, filtfilt = _numeric_deps()
        arr = np.asarray(data, dtype=float)
        nyq = 0.5 * fs
        normal_cutoff = cutoff / nyq
        b, a = butter(order, normal_cutoff, btype="low", analog=False)
        smoothed = filtfilt(b, a, arr)
        return smoothed.tolist()

    @staticmethod
    def _calculate_grade_pct(
        distance_series: list[float],
        smoothed_alt_series: list[float],
    ) -> list[float]:
        """计算点对点的坡度百分比 (%)

        基于 Butterworth 平滑后的海拔计算逐段坡度,
        避免 delta_dist <= 0 时触发除零异常(兜底 1e-5)。

        Args:
            distance_series: 距离序列(单位 m,单调递增)。
            smoothed_alt_series: 平滑后海拔序列(单位 m)。

        Returns:
            坡度百分比列表(长度与输入一致),输入不合法时返回空列表。
        """
        if (
            not distance_series
            or not smoothed_alt_series
            or len(distance_series) != len(smoothed_alt_series)
        ):
            return []

        np, _, _ = _numeric_deps()
        dist_arr = np.asarray(distance_series, dtype=float)
        alt_arr = np.asarray(smoothed_alt_series, dtype=float)

        # 第一点无前驱,用 prepend 自身,使其坡度为 0
        delta_alt = np.diff(alt_arr, prepend=alt_arr[0])
        delta_dist = np.diff(dist_arr, prepend=dist_arr[0])

        # 防止除零异常,最小距离差设为极小值
        delta_dist[delta_dist <= 0] = 1e-5

        grade_pct = (delta_alt / delta_dist) * 100.0
        return grade_pct.tolist()

    @staticmethod
    def _calculate_gap_speed_non_linear(raw_speed_m_s: float, grade_pct: float) -> float:
        """
        基于 Minetti 能量消耗方程多项式拟合的非线性 GAP 速度计算
        grade_pct: 坡度百分比 (例如上坡 10% 传入 10.0，下坡 -12% 传入 -12.0)
        返回: 等效平地速度 (m/s)
        """
        if grade_pct == 0.0 or raw_speed_m_s <= 0:
            return raw_speed_m_s

        x = grade_pct / 100.0

        if x > 0:
            # 上坡阶段：能耗随坡度增加呈现显著非线性陡增
            c_factor = 1.0 + (x * 4.5) + ((x ** 2) * 12.0)
        else:
            # 下坡阶段
            if x >= -0.10:
                # -10% 以内缓下坡：重力做正功，最为省力
                c_factor = 1.0 + (x * 2.5)
            else:
                # 突破 -10% 陡下坡：离心收缩导致刹车能耗重新上升
                c_factor = 0.75 + (abs(x + 0.10) * 3.5)

        # 兜底限制：等效速度系数不应低于 0.5，避免极端下坡算出不合理低速
        c_factor = max(0.5, c_factor)

        return raw_speed_m_s * c_factor

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
                "filter": {
                    "type": "butterworth",
                    "cutoff": 0.05,
                    "fs": 1.0,
                    "order": 2,
                },
                "model": "minetti_non_linear",
            },
            "_gap_error": reason,
        }
