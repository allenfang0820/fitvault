import logging
import math
from collections import deque

from metrics_registry import REVIEW_MODE_SPORTS

logger = logging.getLogger(__name__)


_CYCLING_SPORT_TYPES: frozenset[str] = REVIEW_MODE_SPORTS["cycling"]

_RUNNING_SPORT_TYPES: frozenset[str] = REVIEW_MODE_SPORTS["running"]

_HIKING_SPORT_TYPES: frozenset[str] = frozenset({
    "hiking",
    "walking",
    "mountaineering",
})


class AdvancedMetricsCalc:

    # =========================================================
    # 基础安全工具
    # =========================================================

    @staticmethod
    def _is_valid_number(v):
        return (
            isinstance(v, (int, float))
            and not math.isnan(v)
        )

    @staticmethod
    def _safe_timestamp(record):
        return record.get('timestamp')

    @staticmethod
    def _sort_records(records):
        return sorted(
            records,
            key=lambda x: x.get('timestamp')
        )

    # =========================================================
    # 1. Banister TRIMP
    # =========================================================

    @staticmethod
    def calculate_trimp(records, user_profile=None):
        if not records or len(records) < 2:
            return 0.0
        records = AdvancedMetricsCalc._sort_records(records)
        profile = user_profile or {}
        gender = profile.get('gender', 'male').lower()
        age = profile.get('age', 35)
        rest_hr = profile.get('resting_hr', 60)
        max_hr = profile.get('max_hr') or (208 - (0.7 * age))
        if max_hr <= rest_hr:
            return 0.0
        b = 1.92 if gender == 'male' else 1.67
        trimp_total = 0.0
        for i in range(1, len(records)):
            curr = records[i]
            prev = records[i - 1]
            hr = curr.get('heart_rate')
            prev_time = AdvancedMetricsCalc._safe_timestamp(prev)
            curr_time = AdvancedMetricsCalc._safe_timestamp(curr)
            if not (AdvancedMetricsCalc._is_valid_number(hr) and prev_time and curr_time):
                continue
            if not (30 < hr < 240):
                continue
            duration_mins = (curr_time - prev_time).total_seconds() / 60.0
            if duration_mins <= 0 or duration_mins > 5:
                continue
            if hr <= rest_hr:
                continue
            hr_reserve_ratio = ((hr - rest_hr) / (max_hr - rest_hr))
            if hr_reserve_ratio <= 0:
                continue
            trimp_total += (duration_mins * hr_reserve_ratio * 0.64 * math.exp(b * hr_reserve_ratio))
        return round(trimp_total, 1)

    # =========================================================
    # 2. Aerobic Decoupling (Pa:Hr)
    # =========================================================

    @staticmethod
    def calculate_aerobic_decoupling(records):
        if not records:
            return None
        records = AdvancedMetricsCalc._sort_records(records)
        start_time = AdvancedMetricsCalc._safe_timestamp(records[0])
        end_time = AdvancedMetricsCalc._safe_timestamp(records[-1])
        if not start_time or not end_time:
            return None
        total_duration = (end_time - start_time).total_seconds()
        if total_duration < 2400:
            return None
        valid_records = []
        for r in records:
            ts = AdvancedMetricsCalc._safe_timestamp(r)
            if not ts:
                continue
            elapsed = (ts - start_time).total_seconds()
            if 900 <= elapsed <= (total_duration - 300):
                valid_records.append(r)
        if len(valid_records) < 20:
            return None
        mid_idx = len(valid_records) // 2
        half_1 = valid_records[:mid_idx]
        half_2 = valid_records[mid_idx:]

        def get_ratio(half_data):
            hr_values = []
            spd_values = []
            for r in half_data:
                hr = r.get('heart_rate')
                spd = r.get('speed')
                if not (AdvancedMetricsCalc._is_valid_number(hr) and AdvancedMetricsCalc._is_valid_number(spd)):
                    continue
                if not (30 < hr < 240):
                    continue
                if not (0.5 < spd < 35):
                    continue
                hr_values.append(hr)
                spd_values.append(spd)
            if not hr_values or not spd_values:
                return None
            avg_hr = sum(hr_values) / len(hr_values)
            avg_spd = sum(spd_values) / len(spd_values)
            if avg_spd <= 0:
                return None
            return avg_hr / avg_spd

        r1 = get_ratio(half_1)
        r2 = get_ratio(half_2)
        if r1 and r2:
            return round(((r2 - r1) / r1) * 100, 2)
        return None

    # =========================================================
    # 4. VAM
    # =========================================================

    # =========================================================
    # 内部工具:rolling median 平滑(窗口不足时使用已有点)
    # =========================================================
    @staticmethod
    def _rolling_median(values, window=5):
        """对序列做 rolling median,边界处用边值填充保持窗口完整。

        目的:抑制城市平路/公路通勤中 1m 级海拔噪声,使 VAM 不被
        噪声误算为 720 m/h。
        边界处理:左侧不足用 values[0] 填充,右侧不足用 values[-1] 填充,
        避免窗口收缩后边界点被"拉平"导致真实爬升被低估。
        """
        n = len(values)
        if n == 0:
            return []
        half = window // 2
        result = []
        for i in range(n):
            win_vals = []
            for j in range(i - half, i + half + 1):
                if j < 0:
                    win_vals.append(values[0])
                elif j >= n:
                    win_vals.append(values[-1])
                else:
                    win_vals.append(values[j])
            win_vals = sorted(win_vals)
            m = len(win_vals)
            mid = m // 2
            if m % 2 == 1:
                result.append(win_vals[mid])
            else:
                result.append((win_vals[mid - 1] + win_vals[mid]) / 2.0)
        return result

    @staticmethod
    def calculate_vam(records):
        """计算 VAM(m/h,垂直爬升速度)。

        算法:「有效爬坡段」识别 + 段级过滤,而非逐点累计。
        1) 按 timestamp 排序
        2) 对 altitude 做 rolling median(窗口 5)平滑
        3) 识别连续上坡段;单点下降 <= 2m 容忍保留
        4) 段级过滤:累计爬升 >= 10m / 持续 >= 60s / 距离 >= 100m / 坡度 >= 3%
        5) VAM = sum(有效段爬升) / sum(有效段时间) * 3600
        6) 无有效段返回 0.0
        """
        if not records or len(records) < 2:
            return 0.0
        records = AdvancedMetricsCalc._sort_records(records)

        # 仅保留有有效 altitude 的 record(其它字段在配对时再校验)
        valid_alt_records = [
            r for r in records
            if AdvancedMetricsCalc._is_valid_number(r.get('altitude'))
        ]
        if len(valid_alt_records) < 2:
            return 0.0

        # 平滑 altitude
        altitudes = [r.get('altitude') for r in valid_alt_records]
        smoothed = AdvancedMetricsCalc._rolling_median(altitudes, window=5)

        # 段状态
        segments = []  # 候选段列表:{"ascent", "time", "distance"}
        current = None

        for i in range(1, len(valid_alt_records)):
            prev_rec = valid_alt_records[i - 1]
            curr_rec = valid_alt_records[i]
            prev_alt = smoothed[i - 1]
            curr_alt = smoothed[i]

            dist = curr_rec.get('distance')
            prev_dist = prev_rec.get('distance')
            curr_time = AdvancedMetricsCalc._safe_timestamp(curr_rec)
            prev_time = AdvancedMetricsCalc._safe_timestamp(prev_rec)

            if not (AdvancedMetricsCalc._is_valid_number(dist)
                    and AdvancedMetricsCalc._is_valid_number(prev_dist)
                    and curr_time
                    and prev_time):
                if current is not None:
                    segments.append(current)
                    current = None
                continue

            delta_alt = curr_alt - prev_alt
            delta_dist = dist - prev_dist
            delta_time = (curr_time - prev_time).total_seconds()

            # 时间断裂 / 无效距离 → 切断当前段
            if delta_time <= 0 or delta_time > 300:
                if current is not None:
                    segments.append(current)
                    current = None
                continue
            if delta_dist <= 0:
                continue

            # 异常垂直速度(>= 5 m/s)→ 视为噪声,跳过
            if (abs(delta_alt) / delta_time) >= 5:
                continue

            if delta_alt >= 0:
                # 上坡或平段 → 加入 / 延续当前段
                if current is None:
                    current = {"ascent": 0.0, "time": 0.0, "distance": 0.0}
                current["ascent"] += delta_alt
                current["time"] += delta_time
                current["distance"] += delta_dist
            else:
                # 下降
                drop = -delta_alt
                if drop <= 2.0:
                    # 单点小幅下降:保留时间/距离,容忍真实爬坡中的抖动
                    if current is not None:
                        current["time"] += delta_time
                        current["distance"] += delta_dist
                else:
                    # 明显下降 → 切断当前段
                    if current is not None:
                        segments.append(current)
                        current = None

        # 收尾最后一段
        if current is not None:
            segments.append(current)

        # 段级过滤(有效爬坡段定义)
        valid_segments = [
            s for s in segments
            if s["ascent"] >= 10.0
            and s["time"] >= 60.0
            and s["distance"] >= 100.0
            and s["distance"] > 0
            and (s["ascent"] / s["distance"]) >= 0.03
        ]

        if not valid_segments:
            return 0.0

        total_ascent = sum(s["ascent"] for s in valid_segments)
        total_time = sum(s["time"] for s in valid_segments)
        if total_time <= 0:
            return 0.0
        return round((total_ascent / total_time) * 3600, 1)

    # =========================================================
    # 5. Lactate Threshold HR
    # =========================================================

    @staticmethod
    def calculate_threshold_hr(records):
        if not records:
            return None
        records = AdvancedMetricsCalc._sort_records(records)
        window = deque()
        hr_sum = 0.0
        max_20m_avg_hr = 0.0
        for r in records:
            ts = AdvancedMetricsCalc._safe_timestamp(r)
            hr = r.get('heart_rate')
            if not ts:
                continue
            if not AdvancedMetricsCalc._is_valid_number(hr):
                continue
            if not (30 < hr < 240):
                continue
            window.append((ts, hr))
            hr_sum += hr
            while (window and (ts - window[0][0]).total_seconds() > 1200):
                _, old_hr = window.popleft()
                hr_sum -= old_hr
            if len(window) > 5:
                span = (window[-1][0] - window[0][0]).total_seconds()
                if span >= 960:
                    avg_hr = hr_sum / len(window)
                    if avg_hr > max_20m_avg_hr:
                        max_20m_avg_hr = avg_hr
        if max_20m_avg_hr > 0:
            return round(max_20m_avg_hr * 0.95, 1)
        return None

    @staticmethod
    def _profile_ftp(user_profile):
        if not isinstance(user_profile, dict):
            return None
        for key in ("ftp", "cycling_ftp", "threshold_power", "ftp_w"):
            value = user_profile.get(key)
            if AdvancedMetricsCalc._is_valid_number(value) and 50 <= float(value) <= 800:
                return float(value)
        return None

    @staticmethod
    def _profile_threshold_hr(user_profile):
        if not isinstance(user_profile, dict):
            return None
        for key in ("lactate_threshold_hr", "threshold_hr"):
            value = user_profile.get(key)
            if AdvancedMetricsCalc._is_valid_number(value) and 60 <= float(value) <= 230:
                return float(value)
        return None

    @staticmethod
    def calculate_threshold_detail(records, sport_type=None, user_profile=None):
        """Return sport-aware threshold detail while keeping threshold_hr available."""
        records = AdvancedMetricsCalc._sort_records(records or [])
        sport = str(sport_type or "").strip().lower()
        user_profile = user_profile or {}
        threshold_hr = (
            AdvancedMetricsCalc._profile_threshold_hr(user_profile)
            or AdvancedMetricsCalc.calculate_threshold_hr(records)
        )
        best_20m_hr = AdvancedMetricsCalc.calculate_threshold_hr(records)

        detail = {
            "value": threshold_hr,
            "source": "threshold_hr" if threshold_hr is not None else "none",
            "confidence": "medium" if threshold_hr is not None else "low",
            "threshold_hr": threshold_hr,
            "threshold_power": None,
            "threshold_wkg": None,
            "best_20m_power": None,
            "best_20m_hr": best_20m_hr,
        }

        if sport not in _CYCLING_SPORT_TYPES:
            return detail

        weight_kg = AdvancedMetricsCalc._profile_weight_kg(user_profile)
        profile_ftp = AdvancedMetricsCalc._profile_ftp(user_profile)
        if profile_ftp is not None:
            detail["threshold_power"] = round(profile_ftp, 1)
            if weight_kg:
                detail["threshold_wkg"] = round(profile_ftp / weight_kg, 2)
                detail["value"] = detail["threshold_wkg"]
                detail["source"] = "ftp_wkg"
            else:
                detail["value"] = detail["threshold_power"]
                detail["source"] = "ftp_w"
            detail["confidence"] = "high"
            return detail

        def power_value(record):
            power = AdvancedMetricsCalc._record_power(record)
            if power is None or power <= 0 or power > 2500:
                return None
            return power

        best_power, _ = AdvancedMetricsCalc._window_best_average(
            records,
            power_value,
            1200,
            min_coverage=0.8,
        )
        if best_power is not None:
            threshold_power = best_power * 0.95
            detail["best_20m_power"] = round(best_power, 1)
            detail["threshold_power"] = round(threshold_power, 1)
            if weight_kg:
                detail["threshold_wkg"] = round(threshold_power / weight_kg, 2)
                detail["value"] = detail["threshold_wkg"]
                detail["source"] = "ftp_wkg"
            else:
                detail["value"] = detail["threshold_power"]
                detail["source"] = "ftp_w"
            detail["confidence"] = "medium"
            return detail

        if threshold_hr is not None:
            detail["source"] = "threshold_hr"
            detail["confidence"] = "low"
        return detail

    # =========================================================
    # 6. Anaerobic Peak
    # =========================================================

    @staticmethod
    def _record_power(record):
        for key in ("power", "watts", "Power", "enhanced_power"):
            value = record.get(key)
            if AdvancedMetricsCalc._is_valid_number(value):
                return float(value)
        return None

    @staticmethod
    def _profile_weight_kg(user_profile):
        if not isinstance(user_profile, dict):
            return None
        for key in ("weight_kg", "weight", "body_weight_kg"):
            value = user_profile.get(key)
            if AdvancedMetricsCalc._is_valid_number(value) and 25 <= float(value) <= 250:
                return float(value)
        return None

    @staticmethod
    def _profile_max_hr(user_profile):
        if not isinstance(user_profile, dict):
            return None
        value = user_profile.get("max_hr")
        if AdvancedMetricsCalc._is_valid_number(value) and 80 <= float(value) <= 240:
            return float(value)
        return None

    @staticmethod
    def _window_best_average(
        records,
        value_getter,
        window_seconds,
        *,
        min_coverage=0.8,
        window_filter=None,
    ):
        """Return best average value over a time window with coverage checks."""
        window = deque()
        value_sum = 0.0
        best = None
        best_records = None
        min_span = window_seconds * min_coverage
        for record in records:
            ts = AdvancedMetricsCalc._safe_timestamp(record)
            if not ts:
                continue
            value = value_getter(record)
            if value is None:
                continue
            window.append((ts, float(value), record))
            value_sum += float(value)
            while window and (ts - window[0][0]).total_seconds() > window_seconds:
                _, old_value, _ = window.popleft()
                value_sum -= old_value
            if len(window) < 2:
                continue
            span = (window[-1][0] - window[0][0]).total_seconds()
            if span < min_span:
                continue
            records_in_window = [item[2] for item in window]
            if window_filter and not window_filter(records_in_window):
                continue
            avg_value = value_sum / len(window)
            if best is None or avg_value > best:
                best = avg_value
                best_records = records_in_window
        return best, best_records

    @staticmethod
    def _window_grade(records):
        if not records or len(records) < 2:
            return None
        first = records[0]
        last = records[-1]
        alt0 = first.get("altitude")
        alt1 = last.get("altitude")
        dist0 = first.get("distance")
        dist1 = last.get("distance")
        if not (
            AdvancedMetricsCalc._is_valid_number(alt0)
            and AdvancedMetricsCalc._is_valid_number(alt1)
            and AdvancedMetricsCalc._is_valid_number(dist0)
            and AdvancedMetricsCalc._is_valid_number(dist1)
        ):
            return None
        delta_dist = float(dist1) - float(dist0)
        if delta_dist <= 0:
            return None
        return (float(alt1) - float(alt0)) / delta_dist

    @staticmethod
    def _has_speed_spike(records, max_delta):
        prev_speed = None
        for record in records:
            speed = record.get("speed")
            if not AdvancedMetricsCalc._is_valid_number(speed):
                continue
            speed = float(speed)
            if prev_speed is not None and abs(speed - prev_speed) > max_delta:
                return True
            prev_speed = speed
        return False

    @staticmethod
    def _avg_window_hr(records):
        values = [
            float(r.get("heart_rate"))
            for r in records
            if AdvancedMetricsCalc._is_valid_number(r.get("heart_rate"))
            and 30 < float(r.get("heart_rate")) < 240
        ]
        if not values:
            return None
        return sum(values) / len(values)

    @staticmethod
    def _cycling_speed_fallback_filter(records, max_hr):
        grade = AdvancedMetricsCalc._window_grade(records)
        if grade is not None and grade < -0.02:
            return False
        if AdvancedMetricsCalc._has_speed_spike(records, 8.0):
            return False
        avg_hr = AdvancedMetricsCalc._avg_window_hr(records)
        if max_hr and avg_hr is not None and avg_hr < max_hr * 0.75:
            return False
        return True

    @staticmethod
    def _running_speed_filter(records):
        grade = AdvancedMetricsCalc._window_grade(records)
        if grade is not None and grade < -0.04:
            return False
        if AdvancedMetricsCalc._has_speed_spike(records, 4.0):
            return False
        return True

    @staticmethod
    def calculate_anaerobic_peak_detail(records, sport_type=None, user_profile=None):
        """Detailed anaerobic capability estimate.

        Cycling prefers short-duration power and only falls back to speed with
        conservative confidence. The legacy calculate_anaerobic_peak wrapper
        keeps returning a float for older callers.
        """
        if not records:
            return {
                "value": None,
                "source": "none",
                "confidence": "low",
                "best_5s_power": None,
                "best_15s_power": None,
                "best_30s_power": None,
                "best_60s_power": None,
                "best_15s_wkg": None,
                "best_30s_wkg": None,
                "best_60s_wkg": None,
                "best_30s_speed": None,
            }
        records = AdvancedMetricsCalc._sort_records(records)
        sport = str(sport_type or "").strip().lower()
        user_profile = user_profile or {}
        weight_kg = AdvancedMetricsCalc._profile_weight_kg(user_profile)
        max_hr = AdvancedMetricsCalc._profile_max_hr(user_profile)

        detail = {
            "value": None,
            "source": "none",
            "confidence": "low",
            "best_5s_power": None,
            "best_15s_power": None,
            "best_30s_power": None,
            "best_60s_power": None,
            "best_15s_wkg": None,
            "best_30s_wkg": None,
            "best_60s_wkg": None,
            "best_30s_speed": None,
        }

        if sport in _CYCLING_SPORT_TYPES:
            def power_value(record):
                power = AdvancedMetricsCalc._record_power(record)
                if power is None or power <= 0 or power > 2500:
                    return None
                return power

            for seconds, key in (
                (5, "best_5s_power"),
                (15, "best_15s_power"),
                (30, "best_30s_power"),
                (60, "best_60s_power"),
            ):
                value, _ = AdvancedMetricsCalc._window_best_average(
                    records,
                    power_value,
                    seconds,
                    min_coverage=0.8,
                )
                if value is not None:
                    detail[key] = round(value, 1)

            if detail["best_30s_power"] is not None:
                if weight_kg:
                    for seconds_key, wkg_key in (
                        ("best_15s_power", "best_15s_wkg"),
                        ("best_30s_power", "best_30s_wkg"),
                        ("best_60s_power", "best_60s_wkg"),
                    ):
                        if detail[seconds_key] is not None:
                            detail[wkg_key] = round(detail[seconds_key] / weight_kg, 2)
                    w15 = detail["best_15s_wkg"] or detail["best_30s_wkg"]
                    w30 = detail["best_30s_wkg"]
                    w60 = detail["best_60s_wkg"] or detail["best_30s_wkg"]
                    detail["value"] = round(0.5 * w15 + 0.3 * w30 + 0.2 * w60, 2)
                    detail["source"] = "power_wkg"
                    detail["confidence"] = "high"
                    return detail
                detail["value"] = round(detail["best_30s_power"], 1)
                detail["source"] = "power_w"
                detail["confidence"] = "medium"
                return detail

            def cycling_speed(record):
                speed = record.get("speed")
                if not AdvancedMetricsCalc._is_valid_number(speed):
                    return None
                speed = float(speed)
                if speed <= 0 or speed > 30:
                    return None
                return speed

            best_speed, _ = AdvancedMetricsCalc._window_best_average(
                records,
                cycling_speed,
                30,
                min_coverage=0.8,
                window_filter=lambda win: AdvancedMetricsCalc._cycling_speed_fallback_filter(win, max_hr),
            )
            if best_speed is not None:
                detail["value"] = round(best_speed, 2)
                detail["source"] = "speed_fallback"
                detail["confidence"] = "low"
                detail["best_30s_speed"] = round(best_speed, 2)
            return detail

        def running_speed(record):
            speed = record.get("speed")
            if not AdvancedMetricsCalc._is_valid_number(speed):
                return None
            speed = float(speed)
            if speed <= 0 or speed > 12:
                return None
            return speed

        best_speed, _ = AdvancedMetricsCalc._window_best_average(
            records,
            running_speed,
            30,
            min_coverage=0.8,
            window_filter=AdvancedMetricsCalc._running_speed_filter,
        )
        if best_speed is not None:
            detail["value"] = round(best_speed, 2)
            detail["source"] = "speed" if sport in ("running", "trail_running") else "speed_fallback"
            detail["confidence"] = "medium" if sport in ("running", "trail_running") else "low"
            detail["best_30s_speed"] = round(best_speed, 2)
        return detail

    @staticmethod
    def calculate_anaerobic_peak(records, sport_type=None, user_profile=None):
        detail = AdvancedMetricsCalc.calculate_anaerobic_peak_detail(records, sport_type, user_profile)
        return detail.get("value")


class RadarScoreEngine:
    @staticmethod
    def _score_by_thresholds(value, thresholds):
        if not value:
            return 0
        low, mid, high = thresholds
        if value < low:
            return 20
        if value < mid:
            return 50
        if value < high:
            return 75
        return 95

    @classmethod
    def score_endurance(cls, trimp, sport_type=None):
        if not trimp:
            return 0
        if sport_type in _RUNNING_SPORT_TYPES:
            return cls._score_by_thresholds(trimp, (20, 45, 70))
        if sport_type in _CYCLING_SPORT_TYPES:
            return cls._score_by_thresholds(trimp, (30, 80, 130))
        if sport_type in _HIKING_SPORT_TYPES:
            return cls._score_by_thresholds(trimp, (10, 25, 45))
        return cls._score_by_thresholds(trimp, (30, 80, 150))

    @staticmethod
    def _score_training_consistency(training_days_28d):
        days = int(training_days_28d or 0)
        if days < 4:
            return 20
        if days <= 8:
            return 50
        if days <= 14:
            return 75
        return 95

    @staticmethod
    def _endurance_confidence(sample_count):
        count = int(sample_count or 0)
        if count >= 12:
            return "high"
        if count >= 6:
            return "medium"
        return "low"

    @classmethod
    def score_endurance_detail(cls, ctl, sport_type=None, training_days_28d=0, sample_count=0):
        ctl_score = cls.score_endurance(ctl, sport_type)
        consistency_score = cls._score_training_consistency(training_days_28d) if sample_count else 0
        score = round(0.75 * ctl_score + 0.25 * consistency_score) if sample_count else 0
        return {
            "score": score,
            "ctl_score": ctl_score,
            "consistency_score": consistency_score,
            "training_days_28d": int(training_days_28d or 0),
            "sample_count": int(sample_count or 0),
            "confidence": cls._endurance_confidence(sample_count),
            "source": "ctl_42d_plus_28d_consistency" if sample_count else "no_valid_trimp",
        }

    @staticmethod
    def score_recovery(hrv_score):
        return min(max(int(hrv_score or 0), 0), 100)

    @staticmethod
    def _first_number(data, keys):
        if not isinstance(data, dict):
            return None
        for key in keys:
            value = data.get(key)
            if isinstance(value, (int, float)) and not math.isnan(value):
                return float(value)
        return None

    @staticmethod
    def _recovery_hrv_score(ratio):
        if ratio >= 1.0:
            return 95
        if ratio >= 0.95:
            return 80
        if ratio >= 0.90:
            return 65
        if ratio >= 0.80:
            return 45
        return 25

    @staticmethod
    def _recovery_tsb_score(tsb, atl=None):
        if tsb >= 5:
            score = 85
        elif tsb >= -10:
            score = 75
        elif tsb >= -25:
            score = 55
        else:
            score = 35
        if atl is not None and atl > 100 and tsb < -10:
            score = max(25, score - 10)
        return score

    @staticmethod
    def _recovery_sleep_score(hours):
        if hours >= 7.0:
            return 90
        if hours >= 6.0:
            return 75
        if hours >= 5.0:
            return 55
        return 35

    @staticmethod
    def _recovery_resting_hr_score(delta):
        if delta <= 0:
            return 90
        if delta <= 3:
            return 75
        if delta <= 6:
            return 55
        return 35

    @staticmethod
    def score_recovery_detail(profile_data=None, load_data=None):
        """Return recovery score from relative recovery signals, not HRV absolute value."""
        profile_data = profile_data if isinstance(profile_data, dict) else {}
        load_data = load_data if isinstance(load_data, dict) else {}
        reasons = []

        hrv_baseline = RadarScoreEngine._first_number(
            profile_data,
            ("hrv_baseline", "baseline_hrv", "hrv_baseline_ms"),
        )
        recent_hrv = RadarScoreEngine._first_number(
            profile_data,
            ("hrv_7d_avg", "recent_hrv", "last_7d_hrv", "hrv_current"),
        )
        resting_hr = RadarScoreEngine._first_number(profile_data, ("resting_hr", "rest_hr"))
        recent_resting_hr = RadarScoreEngine._first_number(
            profile_data,
            ("recent_resting_hr", "resting_hr_7d_avg"),
        )
        sleep_hours = RadarScoreEngine._first_number(
            profile_data,
            ("avg_sleep_hours", "sleep_hours", "sleep_7d_avg"),
        )
        tsb = RadarScoreEngine._first_number(load_data, ("tsb",))
        atl = RadarScoreEngine._first_number(load_data, ("atl",))

        parts = []
        hrv_ratio = None
        source = "fallback"

        if hrv_baseline and hrv_baseline > 0 and recent_hrv and recent_hrv > 0:
            hrv_ratio = recent_hrv / hrv_baseline
            parts.append(("hrv", RadarScoreEngine._recovery_hrv_score(hrv_ratio), 0.40))
            source = "hrv_trend"
        elif hrv_baseline and hrv_baseline > 0:
            reasons.append("缺少近期 HRV,无法判断相对恢复状态")
            source = "baseline_only"
        else:
            reasons.append("缺少 HRV 基线")

        if tsb is not None:
            parts.append(("tsb", RadarScoreEngine._recovery_tsb_score(tsb, atl), 0.30 if hrv_ratio else 0.45))
        else:
            reasons.append("缺少 TSB 训练压力")

        if sleep_hours is not None and sleep_hours > 0:
            parts.append(("sleep", RadarScoreEngine._recovery_sleep_score(sleep_hours), 0.20 if hrv_ratio else 0.35))
        else:
            reasons.append("缺少近期睡眠")

        resting_hr_delta = None
        if resting_hr is not None and recent_resting_hr is not None:
            resting_hr_delta = recent_resting_hr - resting_hr
            parts.append(("resting_hr", RadarScoreEngine._recovery_resting_hr_score(resting_hr_delta), 0.10 if hrv_ratio else 0.20))
        else:
            reasons.append("缺少近期静息心率对比")

        if not parts:
            if source == "baseline_only":
                score = 60
            else:
                score = 0
            confidence = "low"
        else:
            total_weight = sum(weight for _, _, weight in parts)
            score = round(sum(value * weight for _, value, weight in parts) / total_weight)
            if hrv_ratio and len(parts) >= 3:
                confidence = "high"
            elif hrv_ratio or len(parts) >= 2:
                confidence = "medium"
            else:
                confidence = "low"
            if source in ("fallback", "baseline_only"):
                source = "load_balance" if tsb is not None else "fallback"

        if source == "baseline_only" and not parts:
            score = 60
            confidence = "low"

        return {
            "score": int(min(max(score, 0), 100)),
            "source": source,
            "confidence": confidence,
            "hrv_ratio": round(hrv_ratio, 3) if hrv_ratio is not None else None,
            "tsb": tsb,
            "atl": atl,
            "sleep_hours": sleep_hours,
            "resting_hr_delta": round(resting_hr_delta, 1) if resting_hr_delta is not None else None,
            "reasons": reasons,
        }

    @staticmethod
    def score_stability(decoupling):
        if decoupling is None:
            return 0
        if decoupling < 5:
            return 95
        if decoupling < 10:
            return 75
        if decoupling < 15:
            return 55
        return 30

    @staticmethod
    def score_climbing(vam, sport_type=None):
        """爬升维度评分。sport_type 为 None 时保持原行为(跨运动统一阈值),
        提供 sport_type 时 cycling/hiking 走专属阈值。
        """
        if not vam:
            return 0
        if sport_type in _CYCLING_SPORT_TYPES:
            if vam < 300:
                return 20
            if vam < 600:
                return 50
            if vam < 900:
                return 75
            return 95
        if sport_type in ("hiking", "mountaineering"):
            if vam < 150:
                return 20
            if vam < 300:
                return 50
            if vam < 500:
                return 75
            return 95
        if vam < 300:
            return 20
        if vam < 600:
            return 50
        if vam < 900:
            return 75
        return 95

    @staticmethod
    def score_threshold(value, max_hr=None, sport_type=None, source=None, confidence=None):
        if not value:
            return 0
        if sport_type in _CYCLING_SPORT_TYPES:
            if source == "ftp_wkg":
                if value < 2.0:
                    return 40
                if value < 2.8:
                    return 65
                if value < 3.6:
                    return 82
                return 95
            if source == "ftp_w":
                if value < 150:
                    return 40
                if value < 220:
                    return 65
                return 82
            cap = 82 if source == "threshold_hr" or confidence == "low" else 95
        else:
            cap = 95
        if not max_hr:
            return 0
        ratio = value / max_hr
        if ratio < 0.75:
            return 40
        if ratio < 0.82:
            return 65
        if ratio < 0.88:
            return 82
        return min(95, cap)

    @staticmethod
    def score_anaerobic(peak_value, sport_type="running", source=None, confidence=None):
        if not peak_value:
            return 0
        if sport_type in _CYCLING_SPORT_TYPES:
            if source == "power_wkg":
                if peak_value < 5.0:
                    return 20
                if peak_value < 7.5:
                    return 50
                if peak_value < 10.0:
                    return 75
                return 95
            if source == "power_w":
                if peak_value < 400:
                    return 20
                if peak_value < 650:
                    return 50
                return 75
            score_cap = 75 if source == "speed_fallback" or confidence == "low" else 95
            if peak_value < 8:
                return 20
            if peak_value < 12:
                return 50
            if peak_value < 16:
                return 75
            return min(95, score_cap)
        if peak_value < 4.0:
            return 20
        if peak_value < 5.0:
            return 50
        if peak_value < 5.8:
            return 75
        return 95

    RADAR_SCHEMAS = {
        "running": ["endurance", "recovery", "stability", "threshold", "climbing", "anaerobic"],
        "trail_running": ["endurance", "recovery", "stability", "climbing", "anaerobic"],
        "cycling": ["endurance", "recovery", "stability", "threshold", "climbing", "anaerobic"],
        "hiking": ["endurance", "recovery", "climbing"],
        "swimming": ["endurance", "recovery", "threshold"],
    }

    LABELS = {
        "endurance": "耐力",
        "recovery": "恢复",
        "stability": "心肺稳定",
        "threshold": "阈值",
        "climbing": "爬升",
        "anaerobic": "无氧爆发",
    }

    @staticmethod
    def _optional_int(value):
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_confidence(value):
        token = str(value or "").strip().lower()
        return token if token in {"high", "medium", "low"} else None

    @staticmethod
    def _append_low_confidence_note(reason, confidence):
        if confidence != "low":
            return reason
        note = "样本不足或数据来源较弱，分数仅供参考"
        if reason:
            return f"{reason}；{note}"
        return note

    @staticmethod
    def _optional_float(value):
        if value is None:
            return None
        try:
            value = float(value)
            if math.isnan(value):
                return None
            return value
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _score_cycling_climb_scale(gain_p90, distance_p90):
        """Scale score follows the same idea as climb categorization: real climbs need size.

        Strava-style climb categories use distance and grade; with activity-level data we use
        gain and distance as a conservative proxy, avoiding VAM-only 95 scores from short efforts.
        """
        gain = float(gain_p90 or 0)
        distance = float(distance_p90 or 0)
        if gain <= 0 or distance <= 0:
            return 0
        grade = gain / max(distance * 1000.0, 1.0)
        climb_score = distance * 1000.0 * grade
        if gain >= 1000 and distance >= 40:
            return 95
        if gain >= 500 and distance >= 8:
            return 82
        if gain >= 250 and distance >= 5:
            return 70
        if gain >= 100 and distance >= 3:
            return 55
        if gain >= 50 and distance >= 1:
            return 40
        return 25 if climb_score > 0 else 0

    @staticmethod
    def _score_cycling_climb_consistency(sample_count):
        count = int(sample_count or 0)
        if count >= 6:
            return 95
        if count >= 3:
            return 65
        if count >= 1:
            return 40
        return 0

    @classmethod
    def score_cycling_climbing_detail(cls, metrics_data):
        """Composite cycling climbing score.

        Contract: VAM remains the performance signal, but final cycling climbing score is capped
        by sample count and data richness. This keeps VAM useful without letting a few short climbs
        imply a near-perfect all-round climbing profile.
        """
        metrics_data = metrics_data if isinstance(metrics_data, dict) else {}
        vam = cls._optional_float(metrics_data.get("climbing_vam_p90"))
        if vam is None:
            vam = cls._optional_float(metrics_data.get("vam"))
        sample_count = int(metrics_data.get("climbing_sample_count") or 0)
        gain_p90 = cls._optional_float(metrics_data.get("climbing_gain_p90"))
        distance_p90 = cls._optional_float(metrics_data.get("climbing_distance_p90"))
        duration_p90 = cls._optional_float(metrics_data.get("climbing_duration_p90"))
        power_count = int(metrics_data.get("climbing_power_available_count") or 0)
        power_available = power_count > 0

        if not vam or sample_count <= 0:
            return {
                "score": 0,
                "confidence": "low",
                "source": "cycling_climb_composite",
                "reason": "无有效骑行爬坡样本",
                "score_cap": 0,
                "components": {
                    "performance": 0,
                    "scale": 0,
                    "consistency": 0,
                    "data_quality": 0,
                },
            }

        performance_score = cls.score_climbing(vam, "cycling")
        scale_score = cls._score_cycling_climb_scale(gain_p90, distance_p90)
        consistency_score = cls._score_cycling_climb_consistency(sample_count)
        data_quality_score = 85 if power_available else 55
        if duration_p90 and duration_p90 >= 300:
            data_quality_score = min(95, data_quality_score + 10)

        score = round(
            performance_score * 0.45
            + scale_score * 0.25
            + consistency_score * 0.20
            + data_quality_score * 0.10
        )

        score_cap = 95
        cap_reasons = []
        if sample_count <= 2:
            score_cap = min(score_cap, 75)
            cap_reasons.append("有效爬坡样本不足3个,最高75")
        elif sample_count <= 5:
            score_cap = min(score_cap, 85)
            cap_reasons.append("有效爬坡样本3-5个,最高85")
        if not power_available:
            score_cap = min(score_cap, 85)
            cap_reasons.append("缺少爬坡功率/Wkg,仅VAM fallback最高85")
        if duration_p90 and duration_p90 < 300:
            score_cap = min(score_cap, 80)
            cap_reasons.append("多数爬坡持续时间不足5分钟,最高80")

        final_score = int(min(max(score, 0), score_cap))
        if sample_count >= 6 and power_available:
            confidence = "high"
        elif sample_count >= 3:
            confidence = "medium"
        else:
            confidence = "low"
        if not power_available and confidence == "high":
            confidence = "medium"

        parts = [
            f"VAM(每小时爬升速度) P90 {round(vam, 1)} m/h",
            f"有效VAM样本{sample_count}个",
            f"表现分{performance_score}",
            f"规模分{scale_score}",
            f"稳定分{consistency_score}",
            "使用功率字段" if power_available else "缺少爬坡功率/Wkg,采用VAM fallback",
        ]
        activity_count = int(metrics_data.get("climbing_activity_count_90d") or 0)
        elevation_count = int(metrics_data.get("climbing_elevation_activity_count_90d") or 0)
        if activity_count or elevation_count:
            parts.insert(
                1,
                f"90天骑行{activity_count}条/有爬升活动{elevation_count}条",
            )
        if cap_reasons:
            parts.append("；".join(cap_reasons))
        return {
            "score": final_score,
            "confidence": confidence,
            "source": "cycling_climb_composite",
            "reason": "，".join(parts),
            "score_cap": score_cap,
            "components": {
                "performance": performance_score,
                "scale": scale_score,
                "consistency": consistency_score,
                "data_quality": data_quality_score,
            },
        }

    @classmethod
    def _dimension_meta(cls, key, metrics_data):
        confidence = None
        sample_count = None
        source = None
        reason = ""

        if key == "endurance":
            confidence = cls._normalize_confidence(metrics_data.get("endurance_confidence"))
            sample_count = cls._optional_int(metrics_data.get("endurance_sample_count"))
            source = metrics_data.get("endurance_source")
            ctl_score = metrics_data.get("endurance_ctl_score")
            consistency_score = metrics_data.get("endurance_consistency_score")
            training_days = metrics_data.get("endurance_training_days_28d")
            parts = []
            if ctl_score is not None:
                parts.append(f"CTL分{ctl_score}")
            if consistency_score is not None:
                parts.append(f"连续性分{consistency_score}")
            if training_days is not None:
                parts.append(f"28天训练{training_days}天")
            reason = "，".join(parts)
        elif key == "recovery":
            confidence = cls._normalize_confidence(metrics_data.get("recovery_confidence"))
            source = metrics_data.get("recovery_source")
            reasons = metrics_data.get("recovery_reasons") or []
            if isinstance(reasons, (list, tuple)):
                reason = "；".join(str(item) for item in reasons if item)
            elif reasons:
                reason = str(reasons)
        elif key == "stability":
            confidence = cls._normalize_confidence(metrics_data.get("stability_confidence"))
            sample_count = cls._optional_int(metrics_data.get("stability_sample_count"))
            source = "pa_hr_decoupling_filtered"
        elif key == "climbing":
            confidence = cls._normalize_confidence(metrics_data.get("climbing_confidence"))
            sample_count = cls._optional_int(metrics_data.get("climbing_sample_count"))
            source = metrics_data.get("climbing_source") or "valid_climb_vam_p90"
            reason = str(metrics_data.get("climbing_reason") or "")
        elif key == "threshold":
            confidence = cls._normalize_confidence(metrics_data.get("threshold_confidence"))
            sample_count = cls._optional_int(metrics_data.get("threshold_sample_count"))
            source = metrics_data.get("threshold_source")
        elif key == "anaerobic":
            confidence = cls._normalize_confidence(
                metrics_data.get("anaerobic_peak_confidence") or metrics_data.get("anaerobic_confidence")
            )
            sample_count = cls._optional_int(metrics_data.get("anaerobic_sample_count"))
            source = metrics_data.get("anaerobic_peak_source")

        source = str(source) if source is not None else None
        reason = cls._append_low_confidence_note(reason, confidence)
        return {
            "confidence": confidence,
            "sample_count": sample_count,
            "source": source,
            "reason": reason or "",
        }

    @classmethod
    def build_radar_profile(cls, sport_type, metrics_data, user_profile=None):
        schema = cls.RADAR_SCHEMAS.get(sport_type, cls.RADAR_SCHEMAS["running"])
        max_hr = user_profile.get("max_hr", 190) if user_profile else 190
        threshold_source = metrics_data.get("threshold_source")
        threshold_value = metrics_data.get("threshold_hr")
        if threshold_source == "ftp_wkg" and metrics_data.get("threshold_wkg") is not None:
            threshold_value = metrics_data.get("threshold_wkg")
        elif threshold_source == "ftp_w" and metrics_data.get("threshold_power") is not None:
            threshold_value = metrics_data.get("threshold_power")

        endurance_score = metrics_data.get("endurance_score")
        if endurance_score is None:
            endurance_score = cls.score_endurance(metrics_data.get("trimp"), sport_type)
        cycling_climbing_detail = None
        if sport_type in _CYCLING_SPORT_TYPES:
            cycling_climbing_detail = cls.score_cycling_climbing_detail(metrics_data)
            metrics_data = dict(metrics_data)
            metrics_data["climbing_confidence"] = cycling_climbing_detail.get("confidence")
            metrics_data["climbing_source"] = cycling_climbing_detail.get("source")
            metrics_data["climbing_reason"] = cycling_climbing_detail.get("reason")
            metrics_data["climbing_score_cap"] = cycling_climbing_detail.get("score_cap")
            metrics_data["climbing_score_components"] = cycling_climbing_detail.get("components")

        scores = {
            "endurance": endurance_score,
            "recovery": cls.score_recovery(
                metrics_data.get("recovery_score")
                if metrics_data.get("recovery_score") is not None
                else metrics_data.get("hrv")
            ),
            "stability": cls.score_stability(metrics_data.get("decoupling")),
            "climbing": (
                cycling_climbing_detail.get("score")
                if cycling_climbing_detail is not None
                else cls.score_climbing(metrics_data.get("vam"), sport_type)
            ),
            "threshold": cls.score_threshold(
                threshold_value,
                max_hr,
                sport_type,
                threshold_source,
                metrics_data.get("threshold_confidence"),
            ),
            "anaerobic": cls.score_anaerobic(
                metrics_data.get("anaerobic_peak"),
                sport_type,
                metrics_data.get("anaerobic_peak_source"),
                metrics_data.get("anaerobic_peak_confidence") or metrics_data.get("anaerobic_confidence"),
            ),
        }

        dimensions = []
        for key in schema:
            dimension = {
                "key": key,
                "label": cls.LABELS.get(key, key),
                "score": scores.get(key, 0),
            }
            dimension.update(cls._dimension_meta(key, metrics_data))
            if key == "climbing" and cycling_climbing_detail is not None:
                dimension["score_cap"] = cycling_climbing_detail.get("score_cap")
                dimension["score_components"] = cycling_climbing_detail.get("components")
            dimensions.append(dimension)

        return {"type": sport_type, "dimensions": dimensions}
