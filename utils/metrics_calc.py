import logging
import math
from collections import deque

logger = logging.getLogger(__name__)


_CYCLING_SPORT_TYPES: frozenset[str] = frozenset({
    "cycling",
    "road_cycling",
    "mountain_biking",
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

    # =========================================================
    # 6. Anaerobic Peak
    # =========================================================

    @staticmethod
    def calculate_anaerobic_peak(records):
        if not records:
            return None
        records = AdvancedMetricsCalc._sort_records(records)
        window = deque()
        spd_sum = 0.0
        max_30s_avg_spd = 0.0
        for r in records:
            ts = AdvancedMetricsCalc._safe_timestamp(r)
            spd = r.get('speed')
            if not ts:
                continue
            if not AdvancedMetricsCalc._is_valid_number(spd):
                continue
            if not (0 <= spd <= 35):
                continue
            window.append((ts, spd))
            spd_sum += spd
            while (window and (ts - window[0][0]).total_seconds() > 30):
                _, old_spd = window.popleft()
                spd_sum -= old_spd
            if len(window) > 3:
                span = (window[-1][0] - window[0][0]).total_seconds()
                if span >= 24:
                    avg_spd = spd_sum / len(window)
                    if avg_spd > max_30s_avg_spd:
                        max_30s_avg_spd = avg_spd
        if max_30s_avg_spd > 0:
            return round(max_30s_avg_spd, 2)
        return None


class RadarScoreEngine:
    @staticmethod
    def score_endurance(trimp):
        if not trimp:
            return 0
        if trimp < 30:
            return 20
        if trimp < 80:
            return 50
        if trimp < 150:
            return 75
        return 95

    @staticmethod
    def score_recovery(hrv_score):
        return min(max(int(hrv_score or 0), 0), 100)

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
            if vam < 100:
                return 20
            if vam < 250:
                return 50
            if vam < 500:
                return 75
            return 95
        if sport_type == "hiking":
            if vam < 100:
                return 20
            if vam < 200:
                return 50
            if vam < 400:
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
    def score_threshold(threshold_hr, max_hr):
        if not threshold_hr or not max_hr:
            return 0
        ratio = threshold_hr / max_hr
        if ratio < 0.75:
            return 40
        if ratio < 0.82:
            return 65
        if ratio < 0.88:
            return 82
        return 95

    @staticmethod
    def score_anaerobic(peak_speed, sport_type="running"):
        if not peak_speed:
            return 0
        if sport_type in _CYCLING_SPORT_TYPES:
            if peak_speed < 8:
                return 20
            if peak_speed < 12:
                return 50
            if peak_speed < 16:
                return 75
            return 95
        else:
            if peak_speed < 3:
                return 20
            if peak_speed < 5:
                return 50
            if peak_speed < 7:
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

    @classmethod
    def build_radar_profile(cls, sport_type, metrics_data, user_profile=None):
        schema = cls.RADAR_SCHEMAS.get(sport_type, cls.RADAR_SCHEMAS["running"])
        max_hr = user_profile.get("max_hr", 190) if user_profile else 190

        scores = {
            "endurance": cls.score_endurance(metrics_data.get("trimp")),
            "recovery": cls.score_recovery(metrics_data.get("hrv")),
            "stability": cls.score_stability(metrics_data.get("decoupling")),
            "climbing": cls.score_climbing(metrics_data.get("vam"), sport_type),
            "threshold": cls.score_threshold(metrics_data.get("threshold_hr"), max_hr),
            "anaerobic": cls.score_anaerobic(metrics_data.get("anaerobic_peak"), sport_type),
        }

        dimensions = []
        for key in schema:
            dimensions.append({
                "key": key,
                "label": cls.LABELS.get(key, key),
                "score": scores.get(key, 0),
            })

        return {"type": sport_type, "dimensions": dimensions}
