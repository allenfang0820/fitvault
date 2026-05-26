import logging
import math
from collections import deque

logger = logging.getLogger(__name__)


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
    # 2. HRV 恢复评分
    # =========================================================

    @staticmethod
    def score_hrv_efficiency(current_hrv, baseline_hrv):
        if not AdvancedMetricsCalc._is_valid_number(current_hrv) or current_hrv <= 0:
            return None
        if not AdvancedMetricsCalc._is_valid_number(baseline_hrv) or baseline_hrv <= 0:
            return None
        ratio = current_hrv / baseline_hrv
        if 0.9 <= ratio <= 1.2:
            return 90.0
        elif ratio > 1.2:
            return 98.0
        else:
            score = (90.0 - (1.0 - ratio) * 100)
            return round(max(20.0, score), 1)

    # =========================================================
    # 3. Aerobic Decoupling (Pa:Hr)
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

    @staticmethod
    def calculate_vam(records):
        if not records or len(records) < 2:
            return 0.0
        records = AdvancedMetricsCalc._sort_records(records)
        total_ascent = 0.0
        climb_time = 0.0
        for i in range(1, len(records)):
            curr = records[i]
            prev = records[i - 1]
            alt = curr.get('altitude')
            prev_alt = prev.get('altitude')
            dist = curr.get('distance')
            prev_dist = prev.get('distance')
            curr_time = AdvancedMetricsCalc._safe_timestamp(curr)
            prev_time = AdvancedMetricsCalc._safe_timestamp(prev)
            if not (AdvancedMetricsCalc._is_valid_number(alt)
                    and AdvancedMetricsCalc._is_valid_number(prev_alt)
                    and AdvancedMetricsCalc._is_valid_number(dist)
                    and AdvancedMetricsCalc._is_valid_number(prev_dist)
                    and curr_time
                    and prev_time):
                continue
            delta_alt = alt - prev_alt
            delta_dist = dist - prev_dist
            delta_time = (curr_time - prev_time).total_seconds()
            if delta_time <= 0 or delta_time > 300:
                continue
            if delta_dist <= 0:
                continue
            if delta_alt <= 0:
                continue
            if (delta_alt / delta_time) >= 5:
                continue
            gradient = delta_alt / delta_dist
            if gradient >= 0.03:
                total_ascent += delta_alt
                climb_time += delta_time
        if climb_time > 0:
            return round((total_ascent / climb_time) * 3600, 1)
        return 0.0

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
    def score_climbing(vam):
        if not vam:
            return 0
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
        if "cycling" in sport_type:
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
        "strength": ["recovery", "anaerobic"],
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
            "climbing": cls.score_climbing(metrics_data.get("vam")),
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
