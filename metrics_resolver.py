from __future__ import annotations

import copy
import json
import math
from typing import Any

from metrics_registry import METRICS_REGISTRY, SPORT_ALIASES, SPORT_DISPLAY_NAMES
# V7.1 Resolver 接入 GapCalculator 引擎(任务 1.1-1.3 已定型,API 稳定)
from gap_calculator import GapCalculator

# === V7.8 sport 隔离:能力路由注册表 ===
# 见 docs/physiology_reference.md §指标 4 Capability Routing
# 字段定义(只增不改,见 reference §四 1.3 退出机制):
#   uses_altitude: 海拔是否构成主要环境压力(陆上有氧)
#   uses_heat:     是否进入"热应激"判定(池水温度恒定故 False)
#   uses_power:    是否进入功率分支(骑行/滑雪)
#   uses_swolf:    是否进入 SWOLF 分支(游泳)
#   uses_cadence:  是否采集步频/踏频数据
# 严禁硬 sport 字符串排除:必须通过 capability 决定指标启用
_SPORT_CAPABILITY_REGISTRY: dict[str, dict[str, bool]] = {
    "running": {
        "uses_altitude": True,
        "uses_heat": True,
        "uses_power": False,
        "uses_swolf": False,
        "uses_cadence": True,
    },
    "trail_running": {
        "uses_altitude": True,
        "uses_heat": True,
        "uses_power": False,
        "uses_swolf": False,
        "uses_cadence": True,
    },
    "hiking": {
        "uses_altitude": True,
        "uses_heat": True,
        "uses_power": False,
        "uses_swolf": False,
        "uses_cadence": False,
    },
    "swimming": {
        "uses_altitude": False,  # 池内/水面海拔无意义
        "uses_heat": False,      # 池温恒定
        "uses_power": False,
        "uses_swolf": True,
        "uses_cadence": False,
    },
    "open_water": {
        "uses_altitude": False,
        "uses_heat": True,       # 水温低,应激大
        "uses_power": False,
        "uses_swolf": True,
        "uses_cadence": False,
    },
    "cycling": {
        "uses_altitude": False,  # 公路骑行海拔非主因
        "uses_heat": True,
        "uses_power": True,
        "uses_swolf": False,
        "uses_cadence": False,
    },
    "mountain_biking": {
        "uses_altitude": True,   # 爬升是核心
        "uses_heat": True,
        "uses_power": True,
        "uses_swolf": False,
        "uses_cadence": False,
    },
    "skiing": {
        "uses_altitude": True,
        "uses_heat": True,
        "uses_power": True,
        "uses_swolf": False,
        "uses_cadence": False,
    },
    "default": {
        "uses_altitude": True,
        "uses_heat": True,
        "uses_power": False,
        "uses_swolf": False,
        "uses_cadence": False,
    },
}


def _classify_sport_dimension(sport_type: str | None) -> dict[str, bool]:
    """V7.8:按 sport_type 查 _SPORT_CAPABILITY_REGISTRY。

    §2.1 全链路可追溯:sport 源头 = session_mesgs.sport → SPORT_ALIASES → 本函数。
    未知 sport 走 default(最保守,全部 False)。
    严禁抛 KeyError(见 reference §6 风险说明 降级路径)。
    """
    token = str(sport_type or "").strip().lower()
    return _SPORT_CAPABILITY_REGISTRY.get(token, _SPORT_CAPABILITY_REGISTRY["default"])


# ── V4.0 核心数据契约 (防腐层) ──
ACTIVITY_SCHEMA = {
    "sport": "running",
    "total_distance": 0.0,
    "total_calories": 0.0,
    "decoupling_rate": 0.0,

    # 核心时序曲线 (保留旧命名以兼容下游单测与 UI)
    "distance_curve": [],
    "speed_curve": [],
    "gap_curve": [],
    "hr_curve": [],
    "altitude_curve": [],
    "lat_curve": [],
    "lon_curve": [],
    "efficiency_curve": [],

    # V4.0 高阶分析引擎输出
    "fatigue_zones": [],
    "insight_events": [],
    "context_tags": {},

    # V_ENV.1.3:Environment Challenge 4 子块派生(climb/altitude/heat/technical_terrain)
    # §调研报告 §3/§4;不入 AI snapshot,不进 ai_snapshots 表
    "environment_challenge": {},
}

SEMICIRCLE_SCALE = 180.0 / (1 << 31)
MAX_CURVE_POINTS = 200

_GARMIN_DEVICE_NAME_DICT: dict[int, str] | None = None


def _garmin_device_name_dict() -> dict[int, str]:
    global _GARMIN_DEVICE_NAME_DICT
    if _GARMIN_DEVICE_NAME_DICT is None:
        try:
            from garmin_fit_sdk import profile as garmin_fit_profile

            raw_garmin_product = garmin_fit_profile.Profile["types"]["garmin_product"]
        except (ImportError, KeyError, TypeError):
            raw_garmin_product = {}
        _GARMIN_DEVICE_NAME_DICT = {int(k): str(v) for k, v in raw_garmin_product.items()}
    return _GARMIN_DEVICE_NAME_DICT

_DEVICE_DISPLAY_OVERLAY: dict[int, str] = {
    3910: "Fenix 7X (APAC)",
    4536: "Fenix 8",
    4759: "Instinct 3 Solar 50mm",
    4775: "Tactix 8 AMOLED",
}


class MetricsResolver:
    """Metrics Runtime v1.1 语义计算大脑 —— 四路严格解耦分发"""

    def resolve(self, raw: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
        session = self._first(raw.get("session_mesgs"))
        laps = raw.get("lap_mesgs") or []
        records = raw.get("record_mesgs") or []

        sm = self._build_storage_model(session, laps, raw, meta)
        vm = self._build_view_model(sm, session, meta)
        ap = self._build_analysis_pack(laps, records)
        ac = self._build_ai_context(sm, session, records)

        # === V7.1 Resolver 接入 GapCalculator(§2.1 全链路 / §8 canonical 只读)===
        # 契约依据:
        #   - §2.1 字段全链路可追溯:GAP 曲线源头 = records(FIT SDK) → GapCalculator → ai_context
        #   - §8 canonical DB 原则:GAP 输出仅进入 *_curve 字段,严禁持久化到 activities 表
        #   - §11 Resolver 入口零二次处理:直接透传 calculate() 输出,禁止 trim/归零/clamp
        gap_result = GapCalculator().calculate(records)
        gap_curve_out: list[float] = gap_result.get("gap_curve", []) or []
        efficiency_curve_out: list[float] = gap_result.get("efficiency_curve", []) or []
        grade_curve_out: list[float] = gap_result.get("grade_curve", []) or []

        # === V4.0 管线整合与截断 (防腐层) ===
        final_data = copy.deepcopy(ACTIVITY_SCHEMA)

        # 提取标量字段
        sport_type = sm.get("sport_type", "running")
        profile_max_hr = self._num(meta.get("profile_max_hr")) if isinstance(meta, dict) else 0.0
        if profile_max_hr > 0:
            sm["profile_max_hr"] = profile_max_hr
        profile_resting_hr = self._num(meta.get("profile_resting_hr")) if isinstance(meta, dict) else 0.0
        if profile_resting_hr > 0:
            sm["profile_resting_hr"] = profile_resting_hr
        profile_weight_kg = self._num(meta.get("profile_weight_kg")) if isinstance(meta, dict) else 0.0
        profile_vo2max = self._num(meta.get("profile_vo2max")) if isinstance(meta, dict) else 0.0
        lactate_threshold_hr = self._num(meta.get("lactate_threshold_hr")) if isinstance(meta, dict) else 0.0
        total_distance = float(sm.get("distance_m", 0))
        total_calories = float(sm.get("calories", 0))
        decoupling_rate = 0.0  # 待后续引擎计算(GapCalculator 串联后)

        # 提取时序曲线(来自 analysis_pack)
        distance_curve = ap.get("distance_curve", [])
        speed_curve = ap.get("speed_curve", [])
        hr_curve = ap.get("hr_curve", [])
        altitude_curve = ap.get("altitude_curve", [])
        lat_curve = ap.get("lat_curve", [])
        lon_curve = ap.get("lon_curve", [])
        gap_curve: list[float] = gap_curve_out         # V7.1: GapCalculator 真实输出
        efficiency_curve: list[float] = efficiency_curve_out  # V7.1: GapCalculator 真实输出
        # grade_curve_out 暂未进入 ACTIVITY_SCHEMA(白名单稳定,后续字段版本化扩展)

        # 1. 触发 Bonk 状态机(2.2 基建)
        insight_events = MetricsResolver._detect_bonk_event(
            distance_curve=distance_curve,
            ei_curve=efficiency_curve,
            total_calories=total_calories,
            sport_type=sport_type,
            time_curve=ap.get("time_curve", []),
            hr_curve=hr_curve,
            speed_curve=speed_curve,
            cadence_curve=ap.get("cadence_curve", []) or [],
            weight_kg=profile_weight_kg or None,
            avg_hr=sm.get("avg_hr"),
            profile_max_hr=sm.get("profile_max_hr"),
            profile_resting_hr=sm.get("profile_resting_hr"),
            lactate_threshold_hr=lactate_threshold_hr or None,
            vo2max=profile_vo2max or None,
        )

        # 触发 Layer 2 疲劳预警带计算(V4.0 从 main.py 下沉)
        fatigue_zones = MetricsResolver._calculate_fatigue_zones(
            distance_curve=distance_curve,
            ei_curve=efficiency_curve,
            sport_type=sport_type,
            avg_hr=sm.get("avg_hr"),
            profile_max_hr=sm.get("profile_max_hr"),
            profile_resting_hr=sm.get("profile_resting_hr"),
        )

        # 2. 映射至 Schema
        final_data["sport"] = sport_type
        final_data["total_distance"] = total_distance
        final_data["total_calories"] = total_calories
        final_data["decoupling_rate"] = decoupling_rate

        final_data["distance_curve"] = distance_curve
        final_data["speed_curve"] = speed_curve
        final_data["gap_curve"] = gap_curve
        final_data["grade_curve"] = grade_curve_out
        final_data["hr_curve"] = hr_curve
        final_data["altitude_curve"] = altitude_curve
        final_data["lat_curve"] = lat_curve
        final_data["lon_curve"] = lon_curve
        final_data["efficiency_curve"] = efficiency_curve
        # V8.3: cadence_curve 暴露到 final_data,供 main.py 持久化
        final_data["cadence_curve"] = ap.get("cadence_curve", []) or []

        final_data["insight_events"] = insight_events
        final_data["fatigue_zones"] = fatigue_zones  # V4.0: 从 main.py 下沉的 Layer 2 疲劳预警带

        # === V4.0 环境标签生成 (供 LLM 防幻觉使用) ===
        # 从 FIT session 提取平均温度(多数 Garmin 设备提供)
        weather = {}
        if isinstance(raw, dict):
            weather = self._decode_weather_json(raw.get("weather_json")) or raw.get("weather") or {}
        if not isinstance(weather, dict):
            weather = {}
        meta_weather = meta.get("weather") if isinstance(meta, dict) else {}
        if isinstance(meta_weather, dict):
            weather = {**weather, **meta_weather}
        avg_temp = (
            self._temperature_num(self._extract(session, "avg_temperature"))
            or self._temperature_num(self._extract(session, "temperature"))
            or self._temperature_num(weather.get("temperature_c"))
            or self._temperature_num(weather.get("temperature"))
            or self._temperature_num(weather.get("avg_temperature"))
        )

        max_alt = max((a for a in altitude_curve if a is not None), default=0.0) if altitude_curve else 0.0

        context_tags: dict[str, str] = {}

        # === V7.8:context_tags 注入改为 capability 路由(指标 4)===
        # 见 docs/physiology_reference.md §指标 4
        # 严禁硬 sport 字符串排除,必须通过 capability 决定是否注入
        dimension = _classify_sport_dimension(sport_type)

        # 1. 热应激标签判定(V7.8:仅对 uses_heat=True 的 sport 注入)
        if dimension["uses_heat"] and avg_temp is not None and avg_temp > 0:
            if avg_temp >= 30.0:
                context_tags["热应激 (Heat Stress)"] = f"Extreme (极端，{avg_temp:.1f}°C) - 极其严峻的散热压力，必定引发严重的心率血管漂移，不要因此批评用户耐力。"
            elif avg_temp >= 25.0:
                context_tags["热应激 (Heat Stress)"] = f"High (高，{avg_temp:.1f}°C) - 会导致散热受阻，后半程心率显著偏高属正常生理代偿。"
            elif avg_temp >= 20.0:
                context_tags["热应激 (Heat Stress)"] = f"Moderate (中度，{avg_temp:.1f}°C) - 轻微影响心率稳定性。"

        # 2. 海拔缺氧标签判定(V7.8:仅对 uses_altitude=True 的 sport 注入)
        if dimension["uses_altitude"]:
            if max_alt >= 2500:
                context_tags["海拔缺氧 (Altitude Hypoxia)"] = f"High (高海拔，{int(max_alt)}m) - 严重缺氧环境，维持同等配速时心率基线会大幅代偿上升。"
            elif max_alt >= 1500:
                context_tags["海拔缺氧 (Altitude Hypoxia)"] = f"Moderate (中海拔，{int(max_alt)}m) - 轻度缺氧，同样的等效速度下心率会略高。"

        # 3. V7.8 指标 1:糖原耗竭风险标签(全 sport 注入,但仅 risk_level != unknown)
        glycogen_risk = MetricsResolver._assess_glycogen_depletion_risk(
            total_calories=total_calories,
            sport_type=sport_type,
        )
        if glycogen_risk["risk_level"] in ("moderate", "high"):
            context_tags["糖原耗竭风险 (Glycogen Depletion Risk)"] = (
                f"{glycogen_risk['risk_level'].upper()} "
                f"(zone {glycogen_risk['zone'][0]:.0f}-{glycogen_risk['zone'][1]:.0f} kcal) - "
                f"本次 kcal={glycogen_risk['kcal']:.0f}"
            )

        # 4. V7.8 指标 2:心肺负荷标签(全 sport 注入,但仅 cardio != unknown)
        cardio_max_hr = sm.get("profile_max_hr")
        cardio = MetricsResolver._classify_cardio_load(
            avg_hr=sm.get("avg_hr"),
            max_hr=cardio_max_hr,
            resting_hr=sm.get("profile_resting_hr"),
            sport_type=sport_type,
            avg_power_w=sm.get("avg_power_w"),
        )
        if cardio in ("high", "extreme"):
            avg_hr_val = self._num(sm.get("avg_hr"))
            max_hr_val = self._num(cardio_max_hr)
            resting_hr_val = self._num(sm.get("profile_resting_hr"))
            hrr_denominator = max_hr_val - resting_hr_val
            ratio_pct = ((avg_hr_val - resting_hr_val) / hrr_denominator * 100.0) if hrr_denominator > 0 else 0.0
            context_tags["心肺负荷 (Cardio Load)"] = (
                f"{cardio} (HRR={(ratio_pct):.0f}%, avg_hr={avg_hr_val:.0f}, resting_hr={resting_hr_val:.0f}, profile_max_hr={max_hr_val:.0f})"
            )

        # 5. V7.8 指标 3:功率变异性标签(仅 uses_power sport;power_stream 暂传 None → unavailable)
        # V7.13 升级:从 records 提 power 数组后,真正计算 VI
        if dimension["uses_power"]:
            vi_result = MetricsResolver._classify_vi(
                power_stream=None,
                sport_type=sport_type,
                duration_min=float(sm.get("duration_sec", 0)) / 60.0,
            )
            if vi_result["confidence"] != "unavailable":
                context_tags["功率变异性 (Variability Index)"] = (
                    f"VI={vi_result['vi']}, level={vi_result['level']}, "
                    f"confidence={vi_result['confidence']}"
                )

        final_data["context_tags"] = context_tags

        # === V_ENV.1.3:Environment Challenge 派生块(Phase 1 MVP)===
        # 数据流:sm.total_ascent/distance_km/max_altitude_m + raw/meta.weather.humidity
        #        + session.avg_temperature → 4 子块摘要
        # 契约依据:fit-arch-contrac §2.1 字段可追溯 + §五 AI 边界(不进 AI Snapshot)
        # §六 审计字段隔离:本块不读 §六 audit 字段,不写 §六 审计字段
        # Phase 1 不实现 GPS curvature(technical_terrain.available=False)
        final_data["environment_challenge"] = _build_environment_challenge_block(
            sm=sm,
            sport_type=sport_type,
            avg_temp=avg_temp,
            raw=raw,
            meta=meta,
        )

        return final_data

    # ── storage_model ──────────────────────────────────────────

    def _build_storage_model(
        self, session: dict[str, Any], laps: list[dict[str, Any]],
        raw: dict[str, Any], meta: dict[str, Any],
    ) -> dict[str, Any]:
        sm_meta = METRICS_REGISTRY["session_meta"]
        sport_raw = self._extract(session, sm_meta["sport"]["source"]) or "Workout"
        sport_type = self._normalize_sport(sport_raw)

        sm: dict[str, Any] = {
            "title": SPORT_DISPLAY_NAMES.get(sport_type, sport_raw or "Workout"),
            "sport": sport_type,
            "device_name": self._resolve_device_name(raw, meta),
            "distance_m": int(self._num(self._extract(session, "total_distance"))),
            "distance_km": round(self._num(self._extract(session, "total_distance")) / 1000.0, 2),
            "duration_sec": int(self._num(self._extract(session, "total_timer_time"))),
            "moving_time_sec": int(self._num(self._extract(session, "total_moving_time"))),
            "avg_hr": int(self._num(self._extract(session, "avg_heart_rate"))),
            "max_hr": int(self._num(self._extract(session, "max_heart_rate"))),
            "calories": int(self._num(self._extract(session, "total_calories"))),
            "elevation_gain_m": int(self._num(self._extract(session, "total_ascent"))),
            "elevation_loss_m": int(self._num(self._extract(session, "total_descent"))),
            "max_altitude_m": int(self._num(self._extract(session, "max_altitude"))),
            "avg_power_w": int(self._num(self._extract(session, "avg_power"))),
            "normalized_power_w": int(self._num(self._extract(session, "normalized_power"))),
            "max_power_w": int(self._num(self._extract(session, "max_power"))),
            "training_load": int(self._num(self._extract(session, "training_load"))),
            "avg_speed_mps": round(self._num(self._extract(session, "avg_speed")), 2),
            "start_time": self._extract(session, sm_meta["start_time"]["source"]),
            "start_lat": self._semicircle_to_deg(
                self._extract(session, sm_meta["start_position_lat"]["source"])
            ),
            "start_lon": self._semicircle_to_deg(
                self._extract(session, sm_meta["start_position_long"]["source"])
            ),
            "sport_type": sport_type,
            "sub_sport_type": self._normalize_sport(
                self._extract(session, sm_meta["sub_sport"]["source"])
            ),
            "avg_pace_sec": 0,
            "avg_pace": 0,
            "date_label": "",
            "gain_m": int(self._num(self._extract(session, "total_ascent"))),
            "max_alt_m": int(self._num(self._extract(session, "max_altitude"))),
            "total_ascent": int(self._num(self._extract(session, "total_ascent"))),
        }

        raw_start = sm["start_time"]
        sm["date_label"] = self._fmt_date_label(raw_start)

        distance_m = sm["distance_m"]
        if distance_m <= 5000:
            sm["distance_display"] = f"{int(distance_m)}m"
        else:
            sm["distance_display"] = f"{round(distance_m / 1000.0, 2):.2f}km"

        sm["region"] = ""

        avg_speed = sm["avg_speed_mps"]
        sub_sport = sm["sub_sport_type"]
        dur_sec = sm["duration_sec"]

        if sub_sport == "lap_swimming":
            num_lengths = self._num(self._extract(session, "num_lengths"))
            pool_length = self._num(self._extract(session, "pool_length")) or 25.0
            swim_distance_m = num_lengths * pool_length if num_lengths > 0 else 0.0
            sec_per_100m = (dur_sec / swim_distance_m * 100.0) if swim_distance_m > 0 and dur_sec > 0 else 0.0
            sm["avg_pace_sec"] = round(sec_per_100m, 1)
        elif sub_sport == "open_water":
            enhanced_speed = self._num(self._extract(session, "enhanced_avg_speed"))
            sec_per_100m = (1000.0 / enhanced_speed / 10.0) if enhanced_speed and enhanced_speed > 0 else 0.0
            sm["avg_pace_sec"] = round(sec_per_100m, 1)
        else:
            sm["avg_pace_sec"] = round(1000.0 / avg_speed) if avg_speed > 0 else 0

        sm["avg_pace"] = sm["avg_pace_sec"]

        dist_km = sm["distance_km"]
        if sub_sport not in ("lap_swimming", "open_water"):
            sm["avg_pace"] = round(dur_sec / dist_km, 2) if dist_km > 0 and dur_sec > 0 else 0

        pace_unit = "/km"
        if sub_sport in ("lap_swimming", "open_water"):
            pace_unit = "/100m"
        sm["avg_pace_display"] = self._fmt_pace(sm["avg_pace_sec"], pace_unit)

        # SWOLF: 平均泳池效率指数
        # Tier 1 — session 层 avg_swolf 字符串键
        raw_swolf = self._extract(session, "avg_swolf")
        # Tier 2 — Garmin SDK 会将 avg_swolf 存储为 session 层数值键 80
        if raw_swolf is None:
            raw_swolf = session.get(80)
        if raw_swolf is not None and float(raw_swolf) > 0:
            sm["swolf"] = int(round(float(raw_swolf)))
        else:
            # Tier 3 — 从各趟 lap 逐趟计算 SWOLF 后取均值（天然排除休息时段）
            swolf_values = []
            for lap in laps:
                lap_len = self._num(lap.get("num_lengths"))
                lap_strokes = self._num(
                    lap.get("total_strokes") or lap.get("total_cycles")
                )
                lap_timer = self._num(lap.get("total_timer_time"))
                if lap_len > 0 and lap_strokes > 0:
                    # total_timer_time 单位兼容（秒或毫秒）
                    lap_dur = lap_timer / 1000.0 if lap_timer > 86400 else lap_timer
                    lap_swolf = int(round(lap_strokes / lap_len + lap_dur / lap_len))
                    swolf_values.append(lap_swolf)
            if swolf_values:
                sm["swolf"] = int(round(sum(swolf_values) / len(swolf_values)))
            else:
                # Tier 4 — session 层聚合兜底（含休息时段的失真值，仅作最后回退）
                num_lengths = self._num(self._extract(session, "num_lengths"))
                total_strokes = self._num(
                    self._extract(session, "total_strokes")
                    or self._extract(session, "total_cycles")
                )
                total_timer = self._num(self._extract(session, "total_timer_time"))
                dur_sec = total_timer / 1000.0 if total_timer > 86400 else total_timer
                if num_lengths > 0:
                    sm["swolf"] = int(round(total_strokes / num_lengths + dur_sec / num_lengths))
                else:
                    sm["swolf"] = 0

        sm["source"] = "resolver"
        return sm

    # ── view_model ─────────────────────────────────────────────

    def _build_view_model(
        self, sm: dict[str, Any], session: dict[str, Any], meta: dict[str, Any]
    ) -> dict[str, str]:
        device_name = (meta.get("device") or {}).get("name") or "Unknown"
        sport_display = SPORT_DISPLAY_NAMES.get(
            sm.get("sport_type") or "unknown", "Unknown"
        )
        return {
            "distance_display": sm.get("distance_display") or self._fmt_distance(sm.get("distance_km")),
            "duration_display": self._fmt_duration(sm.get("duration_sec")),
            "avg_pace_display": sm.get("avg_pace_display") or self._fmt_pace(sm.get("avg_pace")),
            "avg_hr_display": f"{sm.get('avg_hr') or '--'} bpm",
            "max_hr_display": f"{sm.get('max_hr') or '--'} bpm",
            "gain_display": self._fmt_elevation(sm.get("elevation_gain_m")),
            "max_alt_display": self._fmt_elevation(sm.get("max_altitude_m")),
            "calories_display": f"{sm.get('calories') or '--'} kcal",
            "sport_display": sport_display,
            "device": device_name,
            "title": sm.get("title", "Workout"),
        }

    # ── analysis_pack ─────────────────────────────────────────

    def _build_analysis_pack(
        self, laps: list[dict[str, Any]], records: list[dict[str, Any]]
    ) -> dict[str, Any]:
        pack: dict[str, Any] = {
            "source": "resolver",
            "laps": self._normalize_laps(laps),
            "hr_curve": [],
            "pace_curve": [],
            "altitude_curve": [],
            "speed_curve": [],
            "distance_curve": [],
            "lat_curve": [],
            "lon_curve": [],
            "cadence_curve": [],  # V8.3: 步频时序,供 V7.12 Cadence Stability 算法
            "time_curve": [],
        }
        if not records:
            return pack

        step = max(1, len(records) // MAX_CURVE_POINTS)
        sampled = records[::step] if step > 1 else records
        start_ts = self._record_value(sampled[0], "timestamp") if sampled else None

        for rec in sampled:
            ts = self._record_value(rec, "timestamp")
            hr = self._num(self._record_value(rec, "heart_rate", "hr"))
            speed = self._num(self._record_value(rec, "speed", "enhanced_speed"))  # V8.11: FIT 多数设备用 enhanced_speed
            alt = self._num(self._record_value(rec, "altitude", "alt", "enhanced_altitude"))
            dist = self._num(self._record_value(rec, "distance", "dist"))
            lat = self._num(self._record_value(rec, "lat", "position_lat"))
            lon = self._num(self._record_value(rec, "lon", "position_long"))
            cad = self._num(self._record_value(rec, "cadence"))  # V8.3

            pack["hr_curve"].append(hr if hr else None)
            pack["speed_curve"].append(round(speed, 2) if speed else None)
            pack["altitude_curve"].append(round(alt, 1) if alt else None)
            pack["distance_curve"].append(round(dist, 1) if dist is not None else None)
            pack["lat_curve"].append(round(lat, 6) if lat else None)
            pack["lon_curve"].append(round(lon, 6) if lon else None)
            pack["cadence_curve"].append(int(cad) if cad and cad > 0 else None)  # V8.3
            if start_ts is not None and ts is not None and hasattr(ts, "__sub__"):
                try:
                    pack["time_curve"].append(round((ts - start_ts).total_seconds(), 3))
                except Exception:
                    pack["time_curve"].append(None)
            else:
                pack["time_curve"].append(None)

            if speed and speed > 0.1:
                pace_min_per_km = 16.6667 / speed
                pack["pace_curve"].append(round(pace_min_per_km, 2))
            else:
                pack["pace_curve"].append(None)

        return pack

    # ── ai_context ─────────────────────────────────────────────

    def _build_ai_context(
        self, sm: dict[str, Any], session: dict[str, Any], records: list[dict[str, Any]]
    ) -> dict[str, Any]:
        structured = dict(sm)
        structured.pop("start_time", None)
        structured["avg_hr_bpm"] = structured.pop("avg_hr", None)
        structured["max_hr_bpm"] = structured.pop("max_hr", None)
        structured["avg_pace_sec_per_km"] = structured.pop("avg_pace", None)

        pace_values = []
        hr_values = []
        for rec in records:
            spd = self._num(self._record_value(rec, "speed", "enhanced_speed"))  # V8.11
            hr = self._num(self._record_value(rec, "heart_rate", "hr"))
            if spd and spd > 0.1:
                pace_values.append(16.6667 / spd)
            if hr:
                hr_values.append(hr)

        pace_variance = round(float(self._stddev(pace_values)), 2) if len(pace_values) >= 2 else None
        structured["pace_variance"] = pace_variance

        semantic = {
            "cardio_load": self._classify_cardio_load(
                sm.get("avg_hr"),
                sm.get("profile_max_hr"),
                resting_hr=sm.get("profile_resting_hr"),
            ),
            "pace_stability": self._classify_pace_stability(pace_values),
            "elevation_profile": self._classify_elevation(sm.get("elevation_gain_m"), sm.get("distance_km")),
        }

        return {
            "source": "resolver",
            "structured_metrics": structured,
            "semantic_signals": semantic,
        }

    # ── helpers ────────────────────────────────────────────────

    @staticmethod
    def _first(messages: Any) -> dict[str, Any]:
        if isinstance(messages, list) and messages:
            first = messages[0]
            return dict(first) if isinstance(first, dict) else {}
        return {}

    @staticmethod
    def _extract(session: dict[str, Any], key: str) -> Any:
        value = session.get(key)
        if isinstance(value, str):
            return value.replace("\x00", "").strip()
        return value

    @staticmethod
    def _num(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _optional_num(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _temperature_num(value: Any) -> float | None:
        num = MetricsResolver._optional_num(value)
        if num is None:
            return None
        return num if -60.0 <= num <= 70.0 else None

    @staticmethod
    def _record_value(record: Any, *keys: str) -> Any:
        if not isinstance(record, dict):
            return None
        raw = record.get("raw")
        geo = record.get("geo")
        sources = [record]
        if isinstance(raw, dict):
            sources.append(raw)
        if isinstance(geo, dict):
            sources.append(geo)
        for key in keys:
            for source in sources:
                value = source.get(key)
                if value is not None:
                    return value
        return None

    @staticmethod
    def _safe_int_none(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    # ══════════════════════════════════════════════════════════════════
    # V4.0 治理: AI Snapshot 契约层下沉
    # §V4.0 防腐层契约:本节从 main.py 整体迁移,纯计算,无 IO
    # 严禁在 main.py 中重新实现 _build_ai_snapshot_block / _validate_ai_snapshot 等方法
    # 注意: SQLite 查询(IO)仍保留在 main.py._build_ai_snapshot,仅 dict 转换/格式化/校验下沉
    # ══════════════════════════════════════════════════════════════════

    # AI Snapshot 禁止字段(防污染护栏)
    _AI_SNAPSHOT_FORBIDDEN_FIELDS: frozenset[str] = frozenset({
        "slope_pct", "pace_calc", "frontend_distance", "ui_only_metric",
        "reasoning_chain", "fatigue_model", "per_point_slope", "derived_grade",
    })

    # AI Snapshot 允许字段数上限(CONTRACT §6, 报告 canonical + 坡度 v2 后从 35 调整到 39)
    _AI_SNAPSHOT_MAX_KEYS: int = 39

    # AI Snapshot 允许字段白名单
    _AI_SNAPSHOT_FIELD_WHITELIST: frozenset[str] = frozenset({
        "activity_id", "sport_type", "sub_sport_type",
        "distance_km", "distance_display",
        "duration_sec", "duration",
        "avg_pace", "avg_pace_display", "pace_unit",
        "avg_hr", "max_hr",
        "calories",
        "elevation_gain_m", "gain_m",
        "max_alt_m",
        "avg_cadence",
        "normalized_power",
        "swolf",
        "tss",
        "start_time", "start_time_utc",
        "start_lat", "start_lon",
        "region",
        "file_path", "filename",
        "source",
        # 以下为可选字段(可能为 None)
        "resting_hr", "hrv_baseline", "vo2max",
        "weight", "height_cm",
        "pb_5km", "pb_10km", "pb_half_marathon", "pb_full_marathon",
        "lactate_threshold_hr", "lactate_threshold_pace",
        "ftp_watts",
        "avg_sleep_hours",
        "longest_hike_km", "longest_run_km", "longest_cycle_km",
        "swimming_100m_pb", "longest_swim_distance_m",
        "race_predict_5k", "race_predict_10k", "race_predict_half", "race_predict_full",
        # v2 新增:运动生理 / 曲线 / 设备上下文
        "hr_decoupling", "hr_curve", "speed_curve", "device_name",
        # v3 新增:报告 canonical 派生指标
        "min_alt_m", "total_descent_m", "up_count", "down_count",
        "max_single_climb_m", "difficulty_score", "report_metrics_version",
        # v4 新增:报告坡度 v2 指标
        "avg_grade_pct", "max_slope_pct", "min_slope_pct", "uphill_pct", "downhill_pct",
    })

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        """安全转 float:None/异常返回 None(任务 4 V4-0 治理下沉工具)"""
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _validate_ai_snapshot(snapshot: dict[str, Any]) -> None:
        """AI Snapshot Contract Guard — 防污染护栏(V4.0 治理下沉)

        校验内容:
          1. 不含 FORBIDDEN_SNAPSHOT_FIELDS
          2. keys ≤ _AI_SNAPSHOT_MAX_KEYS
          3. 所有 keys 必须在白名单内
          4. 报告 canonical 字段范围校验(total_descent_m ≥ 0, difficulty_score 0-10)
        """
        for f in MetricsResolver._AI_SNAPSHOT_FORBIDDEN_FIELDS:
            assert f not in snapshot, f"AI Snapshot pollution detected: {f}"
        assert len(snapshot.keys()) <= MetricsResolver._AI_SNAPSHOT_MAX_KEYS, (
            f"AI Snapshot keys exceeded: {len(snapshot.keys())} > {MetricsResolver._AI_SNAPSHOT_MAX_KEYS}"
        )
        for k in snapshot.keys():
            if k not in MetricsResolver._AI_SNAPSHOT_FIELD_WHITELIST:
                raise AssertionError(f"AI Snapshot unauthorized field: {k}")
        # 报告 canonical 字段范围校验
        _td = snapshot.get("total_descent_m")
        if _td is not None:
            assert _td >= 0, f"total_descent_m must be >= 0, got {_td}"
        _ds = snapshot.get("difficulty_score")
        if _ds is not None:
            assert 0 <= _ds <= 10, f"difficulty_score out of range [0,10]: {_ds}"

    @staticmethod
    def _debug_ai_snapshot(snapshot: dict[str, Any]) -> None:
        """开发模式:输出 snapshot 结构校验(V4.0 治理下沉)

        §V4.0 防腐层契约:本方法从 main.py 整体迁移,纯文本输出
        严禁在 main.py 中重新实现
        """
        import sys
        keys = list(snapshot.keys())
        nested = [k for k, v in snapshot.items() if isinstance(v, (list, dict))]
        print(
            f"[AI SNAPSHOT CONTRACT] keys={keys} count={len(keys)} nested={nested or 'none'}",
            file=sys.stderr,
            flush=True,
        )

    # ══════════════════════════════════════════════════════════════════
    # V4.0 治理: _build_activity_canonical 业务计算下沉(轨迹报告)
    # §V4.0 防腐层契约:本节从 main.py 整体迁移,纯计算,无 IO
    # 严禁在 main.py 中重新实现该方法
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def _safe_int_zero(value: Any) -> int:
        """安全转 int:None/异常返回 0(V4-5 治理下沉工具,与 main.py _safe_int 语义一致)"""
        if value is None:
            return 0
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _safe_float_zero(value: Any) -> float:
        """安全转 float:None/异常返回 0.0(V4-5 治理下沉工具)"""
        if value is None:
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _decode_weather_json(value: Any) -> dict[str, Any] | None:
        """解码 weather_json 字段(V4-5 治理下沉工具)

        §V4.0 防腐层契约:从 main.py 整体迁移,纯 dict/JSON 转换,无 IO
        接受 str / dict / None 入参,返回 dict 或 None
        """
        if not value:
            return None
        if isinstance(value, dict):
            return value
        import json
        try:
            obj = json.loads(str(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return obj if isinstance(obj, dict) else None

    @staticmethod
    def _build_activity_canonical(r: dict[str, Any]) -> dict[str, Any]:
        """轨迹报告 activity_canonical 组装器(V4.0 治理下沉)

        §V4.0 防腐层契约:本方法从 main.py 整体迁移,纯计算,无 IO
        §五 数据可信分层:仅消费 dict 入参(DB row),不做派生计算
        用于 main.py.load_activity_track 返回前端所需的扁平化轨迹报告字段

        Args:
            r: activities 表行 dict(必须已含 sport_type, sub_sport_type, dist_km,
               distance, duration_sec, duration, gain_m, max_alt_m, avg_pace 等)

        Returns:
            activity_canonical dict(扁平化 UI 字段 + 报告 canonical 字段)
        """
        sub_sport = str(r.get("sub_sport_type") or "").lower()
        pace_unit = "/100m" if sub_sport in ("lap_swimming", "open_water") else "/km"

        dist_km = MetricsResolver._safe_float_zero(r.get("dist_km"))
        if dist_km == 0.0:
            dist_m = MetricsResolver._safe_float_zero(r.get("distance"))
            if dist_m and dist_m > 0:
                dist_km = round(dist_m / 1000.0, 2)
        duration_sec = MetricsResolver._safe_int_zero(r.get("duration_sec") or r.get("duration"))
        gain_m = MetricsResolver._safe_float_zero(r.get("gain_m"))
        avg_hr = MetricsResolver._safe_int_zero(r.get("avg_hr")) or None
        max_hr = MetricsResolver._safe_int_zero(r.get("max_hr")) or None
        calories = MetricsResolver._safe_int_zero(r.get("calories")) or None
        avg_pace = MetricsResolver._safe_float_zero(r.get("avg_pace")) or None

        if dist_km and dist_km > 0:
            if dist_km < 0.1:
                distance_display = f"{int(dist_km * 1000)}m"
            else:
                distance_display = f"{round(dist_km, 2):.2f}km"
        else:
            distance_display = "-- km"

        if avg_pace and avg_pace > 0:
            pm = int(avg_pace // 60)
            ps = int(avg_pace % 60)
            avg_pace_display = f"{pm}'{ps:02d}''{pace_unit}"
        else:
            avg_pace_display = f"-- {pace_unit}"

        return {
            "id": MetricsResolver._safe_int_zero(r.get("id")),
            "sport_type": str(r.get("sport_type") or "unknown"),
            "sub_sport_type": str(r.get("sub_sport_type") or "unknown"),
            "region": str(r.get("region") or "").strip(),
            "weather": MetricsResolver._decode_weather_json(r.get("weather_json")),
            "dist_km": dist_km,
            "distance_display": distance_display,
            "duration_sec": duration_sec,
            "gain_m": gain_m,
            "max_alt_m": MetricsResolver._safe_float_zero(r.get("max_alt_m")),
            "avg_hr": avg_hr,
            "max_hr": max_hr,
            "calories": calories,
            "avg_pace": avg_pace,
            "avg_pace_display": avg_pace_display,
            "pace_unit": pace_unit,
            "start_time": str(r.get("start_time") or ""),
            "min_alt_m": MetricsResolver._safe_float_zero(r.get("min_alt_m")),
            "total_descent_m": MetricsResolver._safe_float_zero(r.get("total_descent_m")),
            "up_count": MetricsResolver._safe_int_zero(r.get("up_count")),
            "down_count": MetricsResolver._safe_int_zero(r.get("down_count")),
            "max_single_climb_m": MetricsResolver._safe_float_zero(r.get("max_single_climb_m")),
            "difficulty_score": MetricsResolver._safe_int_zero(r.get("difficulty_score")),
            "avg_grade_pct": MetricsResolver._safe_float(r.get("avg_grade_pct")),
            "max_slope_pct": MetricsResolver._safe_float(r.get("max_slope_pct")),
            "min_slope_pct": MetricsResolver._safe_float(r.get("min_slope_pct")),
            "uphill_pct": MetricsResolver._safe_float(r.get("uphill_pct")),
            "downhill_pct": MetricsResolver._safe_float(r.get("downhill_pct")),
            "report_metrics_version": MetricsResolver._safe_int_zero(r.get("report_metrics_version")),
        }

    # ══════════════════════════════════════════════════════════════════
    # V4.0 治理: _build_real_laps_from_row 业务计算下沉(圈速数据)
    # §V4.0 防腐层契约:本节从 main.py 整体迁移,纯计算,无 IO
    # 严禁在 main.py 中重新实现该方法
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def _build_real_laps_from_row(row: dict[str, Any]) -> list[dict[str, Any]]:
        """从 activities.laps_json 解析真实圈速数据,转换为前端展示格式。

        §V4.0 防腐层契约:本方法从 main.py 整体迁移,纯计算,无 IO
        §2.1 字段全链路可追溯:UI 字段必须能追溯至 FIT SDK
        真实数据源:FIT lap_mesgs → MetricsResolver._normalize_laps → laps_json

        Args:
            row: activities 表行 dict(必须含 laps_json 键)

        Returns:
            list[dict]: 圈速列表,每圈含 lap_no/distance_km/pace_sec/hr/cadence/gct_ms/power_w
            返回 [] 表示无真实数据,调用方应 fallback 到 _build_lap_rows
        """
        raw = row.get("laps_json")
        if not raw:
            return []
        try:
            import json
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return []
        if not isinstance(parsed, list) or not parsed:
            return []
        rows: list[dict[str, Any]] = []
        for idx, lap in enumerate(parsed):
            if not isinstance(lap, dict):
                continue
            dist_m = MetricsResolver._safe_float_zero(lap.get("distance_m"))
            elapsed = MetricsResolver._safe_float_zero(lap.get("elapsed_sec"))
            lap_avg_hr = MetricsResolver._safe_int_zero(lap.get("avg_hr"))
            lap_max_hr = MetricsResolver._safe_int_zero(lap.get("max_hr"))
            lap_avg_cadence = MetricsResolver._safe_int_zero(lap.get("avg_cadence"))
            lap_avg_power = MetricsResolver._safe_int_zero(lap.get("avg_power"))
            lap_ascent = MetricsResolver._safe_int_zero(lap.get("total_ascent"))
            lap_descent = MetricsResolver._safe_int_zero(lap.get("total_descent"))
            lap_calories = MetricsResolver._safe_int_zero(lap.get("total_calories"))
            lap_swolf = MetricsResolver._safe_int_zero(lap.get("swolf"))
            lap_stroke_distance = MetricsResolver._safe_float_zero(lap.get("avg_stroke_distance"))
            lap_stroke_style = lap.get("swim_stroke")
            lap_length_distance = MetricsResolver._safe_float_zero(lap.get("length_distance_m"))
            # V9.x 修复:从 normalized lap dict 读 stance_time_ms(§2.1 全链路可追溯)
            # 原实现硬编码 None 切断追溯链,本次改为读真值
            lap_gct_ms = MetricsResolver._safe_int_zero(lap.get("stance_time_ms")) or None
            if dist_m <= 0 and elapsed <= 0:
                continue
            pace_sec = int(round(elapsed / (dist_m / 1000.0))) if dist_m > 0 and elapsed > 0 else 0
            rows.append({
                "lap_no": idx + 1,
                "distance_km": round(dist_m / 1000.0, 2) if dist_m > 0 else None,
                "pace_sec": pace_sec if pace_sec > 0 else None,
                "hr": lap_avg_hr if lap_avg_hr else None,
                "max_hr": lap_max_hr if lap_max_hr else None,
                "cadence": lap_avg_cadence if lap_avg_cadence else None,
                "gct_ms": lap_gct_ms,   # V9.x:从硬编码 None 改为透传 Resolver 解析值
                "power_w": lap_avg_power if lap_avg_power else None,
                "ascent_m": lap_ascent if lap_ascent else None,
                "descent_m": lap_descent if lap_descent else None,
                "calories": lap_calories if lap_calories else None,
                "swolf": lap_swolf if lap_swolf else None,
                "stroke_style": lap_stroke_style if lap_stroke_style else None,
                "stroke_distance_m": round(lap_stroke_distance, 2) if lap_stroke_distance else None,
                "length_distance_m": round(lap_length_distance, 1) if lap_length_distance else None,
                "source_type": lap.get("source_type") or "fit_sdk",
            })
        return rows

    # ══════════════════════════════════════════════════════════════════
    # V4.0 治理: _convert_track_to_algorithm_records + _compute_advanced_metrics
    # 业务计算下沉(6维高级指标:TRIMP/Decoupling/VAM/Threshold HR/Anaerobic Peak)
    # §V4.0 防腐层契约:纯计算,无 IO,仅消费 dict/list 入参
    # IO 隔离:profile_backend.get_profile() 留在 main.py
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def _convert_track_to_algorithm_records(track_data: list[dict]) -> list[dict]:
        """将 FIT 引擎输出的标准轨迹点转换为 AdvancedMetricsCalc 需要的记录格式。

        §V4.0 防腐层契约:本方法从 main.py 整体迁移,纯计算,无 IO
        仅使用 track_backend.haversine_m 做纯数学计算(非 DB/文件 IO)
        """
        if not track_data:
            return []
        from datetime import datetime
        import track_backend
        records = []
        cumulative_dist = 0.0
        prev_lat, prev_lon = None, None
        for pt in track_data:
            ts = None
            raw_time = pt.get("time")
            if raw_time:
                try:
                    ts = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass
            if ts is None:
                continue

            if "speed" not in pt and "enhanced_speed" in pt:
                pt["speed"] = pt["enhanced_speed"]
            if "altitude" not in pt and "enhanced_altitude" in pt:
                pt["altitude"] = pt["enhanced_altitude"]
            if "hr" not in pt and "heart_rate" in pt:
                pt["hr"] = pt["heart_rate"]

            lat = pt.get("lat")
            lon = pt.get("lon")
            raw_distance = MetricsResolver._safe_float(pt.get("distance"))
            if raw_distance is not None and raw_distance >= 0:
                cumulative_dist = raw_distance
            else:
                dist_segment = 0.0
                if lat is not None and lon is not None and prev_lat is not None and prev_lon is not None:
                    dist_segment = track_backend.haversine_m(prev_lat, prev_lon, lat, lon)
                cumulative_dist += dist_segment
            prev_lat, prev_lon = lat, lon

            raw_speed = pt.get("speed")
            pace = pt.get("pace")
            calc_speed = (1000.0 / pace) if pace and pace > 0 else 0.0
            final_speed = raw_speed if raw_speed is not None and raw_speed >= 0 else calc_speed

            records.append({
                "timestamp": ts,
                "heart_rate": pt.get("hr"),
                "speed": final_speed,
                "altitude": pt.get("altitude") or pt.get("alt"),
                "distance": cumulative_dist,
                "power": pt.get("power"),
                "cadence": pt.get("cadence"),
            })
        return records

    @staticmethod
    def _compute_advanced_metrics(
        records: list[dict],
        user_profile_dict: dict[str, Any],
        sport_type: str | None = None,
    ) -> dict[str, Any]:
        """6 维雷达算法:TRIMP / 有氧解耦 / VAM / Threshold HR / Anaerobic Peak。

        §V4.0 防腐层契约:本方法从 main.py 整体迁移,纯计算,无 IO
        IO 隔离:user_profile_dict 由 main.py 从 profile_backend.get_profile() 预取后传入
        严禁在 Resolver 中调用 profile_backend 或任何 SQLite 查询

        Args:
            records: _convert_track_to_algorithm_records 的输出(list of dict)
            user_profile_dict: profile_backend.get_profile().to_dict() 的输出(含可能 None 值的字段)
            sport_type: 活动运动类型,用于运动专项无氧算法分支

        Returns:
            dict 含 trimp/decoupling/vam/threshold_hr/anaerobic_peak, 不含 metrics_version
            (metrics_version 由 main.py 在返回后设置,保持单一真相源)
        """
        from utils.metrics_calc import AdvancedMetricsCalc
        # 过滤 None 值(纯 dict 转换,与原始 main.py 行为一致)
        user_profile_dict = {k: v for k, v in user_profile_dict.items() if v is not None}
        calc = AdvancedMetricsCalc
        trimp = calc.calculate_trimp(records, user_profile_dict)
        decoupling = calc.calculate_aerobic_decoupling(records)
        vam = calc.calculate_vam(records)
        threshold_detail = calc.calculate_threshold_detail(records, sport_type, user_profile_dict)
        threshold_hr = threshold_detail.get("threshold_hr")
        anaerobic_detail = calc.calculate_anaerobic_peak_detail(records, sport_type, user_profile_dict)
        anaerobic_peak = anaerobic_detail.get("value")
        result = {
            "trimp": trimp,
            "decoupling": decoupling,
            "vam": vam,
            "threshold_hr": threshold_hr,
            "anaerobic_peak": anaerobic_peak,
        }
        result.update({
            "threshold_source": threshold_detail.get("source"),
            "threshold_confidence": threshold_detail.get("confidence"),
            "threshold_power": threshold_detail.get("threshold_power"),
            "threshold_wkg": threshold_detail.get("threshold_wkg"),
            "best_20m_power": threshold_detail.get("best_20m_power"),
            "best_20m_hr": threshold_detail.get("best_20m_hr"),
            "anaerobic_peak_source": anaerobic_detail.get("source"),
            "anaerobic_peak_confidence": anaerobic_detail.get("confidence"),
            "best_5s_power": anaerobic_detail.get("best_5s_power"),
            "best_15s_power": anaerobic_detail.get("best_15s_power"),
            "best_30s_power": anaerobic_detail.get("best_30s_power"),
            "best_60s_power": anaerobic_detail.get("best_60s_power"),
            "best_15s_wkg": anaerobic_detail.get("best_15s_wkg"),
            "best_30s_wkg": anaerobic_detail.get("best_30s_wkg"),
            "best_60s_wkg": anaerobic_detail.get("best_60s_wkg"),
            "best_30s_speed": anaerobic_detail.get("best_30s_speed"),
        })
        return result

    @staticmethod
    def _build_ai_snapshot_block(row: dict[str, Any]) -> dict[str, Any]:
        """AI 语义快照构建器(V4.0 治理下沉)

        §V4.0 防腐层契约:本方法从 main.py 整体迁移,纯计算,无 IO
        §五 AI 边界:仅消费 dict 入参(由 main.py 从 DB row 转换),不直接连 DB
        PURE FACT CONTRACT: 所有字段来自入参 row(DB/resolver truth)
        禁止前端计算数据、推理结构、per-point 指标进入。

        Args:
            row: activities 表行 dict(必须已含 sport_type, sub_sport_type, dist_km,
                 duration_sec, avg_hr, max_hr, gain_m, max_alt_m, avg_pace 等字段)

        Returns:
            AI Snapshot dict(经 _validate_ai_snapshot 校验)
        """
        sub_sport = str(row.get("sub_sport_type") or "").lower()
        pace_unit = "/100m" if sub_sport in ("lap_swimming", "open_water") else "/km"

        # ── Display Fields (纯格式化,不重新计算) ──
        raw_dist_km = row.get("dist_km")
        if raw_dist_km is not None:
            dist_km = MetricsResolver._safe_float(raw_dist_km)
        else:
            raw_dist_m = row.get("distance")
            dist_km = round(MetricsResolver._safe_float(raw_dist_m) / 1000.0, 2) if raw_dist_m is not None else None

        if dist_km is not None and dist_km > 0:
            if dist_km < 0.1:
                distance_display = f"{int(dist_km * 1000)}m"
            else:
                distance_display = f"{round(dist_km, 2):.2f}km"
        else:
            distance_display = "-- km"

        raw_avg_pace = row.get("avg_pace")
        avg_pace = MetricsResolver._safe_float(raw_avg_pace) if raw_avg_pace is not None else None
        if avg_pace is not None and avg_pace > 0:
            pm = int(avg_pace // 60)
            ps = int(avg_pace % 60)
            avg_pace_display = f"{pm}'{ps:02d}''{pace_unit}"
        else:
            avg_pace_display = f"-- {pace_unit}"

        snapshot: dict[str, Any] = {
            "activity_id": row.get("activity_id") or row.get("id"),
            "sport_type": row.get("sport_type"),
            "sub_sport_type": row.get("sub_sport_type"),
            "distance_km": dist_km,
            "distance_display": distance_display,
            "duration_sec": row.get("duration_sec") or row.get("duration"),
            "avg_pace": avg_pace,
            "avg_pace_display": avg_pace_display,
            "pace_unit": pace_unit,
            "avg_hr": row.get("avg_hr"),
            "max_hr": row.get("max_hr"),
            "calories": row.get("calories"),
            "elevation_gain_m": row.get("gain_m"),
            "max_alt_m": row.get("max_alt_m"),
            "avg_cadence": row.get("avg_cadence"),
            "normalized_power": row.get("normalized_power"),
            "swolf": row.get("swolf"),
            "tss": row.get("tss"),
            "start_time": row.get("start_time"),
            "start_lat": row.get("start_lat"),
            "start_lon": row.get("start_lon"),
            "region": row.get("region"),
            "source": "DB Canonical / Resolver Truth",
            "hr_decoupling": row.get("hr_decoupling"),
            "hr_curve": row.get("hr_curve"),
            "speed_curve": row.get("speed_curve"),
            "device_name": row.get("device_name"),
            "min_alt_m": row.get("min_alt_m"),
            "total_descent_m": row.get("total_descent_m"),
            "up_count": row.get("up_count"),
            "down_count": row.get("down_count"),
            "max_single_climb_m": row.get("max_single_climb_m"),
            "difficulty_score": row.get("difficulty_score"),
            "report_metrics_version": row.get("report_metrics_version"),
            "avg_grade_pct": row.get("avg_grade_pct"),
            "max_slope_pct": row.get("max_slope_pct"),
            "min_slope_pct": row.get("min_slope_pct"),
            "uphill_pct": row.get("uphill_pct"),
            "downhill_pct": row.get("downhill_pct"),
        }

        MetricsResolver._validate_ai_snapshot(snapshot)
        MetricsResolver._debug_ai_snapshot(snapshot)
        return snapshot

    @staticmethod
    def _build_ai_snapshot_text_block(snapshot: dict[str, Any] | None) -> str:
        """将 AI snapshot 格式化为 LLM system prompt 可嵌入的文本块(V4.0 治理下沉)

        §V4.0 防腐层契约:本方法从 main.py 整体迁移,纯文本格式化,无 IO
        用于 call_llm 路径的 LLM 输入构造
        """
        if not snapshot:
            return ""
        lines = [
            "【运动语义快照 — 系统真值(非前端计算)】",
            f"- 运动类型: {snapshot.get('sport_type') or '-'} / {snapshot.get('sub_sport_type') or '-'}",
            f"- 距离: {snapshot.get('distance_display') or '-'} ({snapshot.get('distance_km')} km)",
            f"- 用时: {snapshot.get('duration_sec')} 秒",
            f"- 配速: {snapshot.get('avg_pace_display') or '-'} ({snapshot.get('pace_unit') or '-'})",
            f"- 平均心率: {snapshot.get('avg_hr')} bpm / 最大: {snapshot.get('max_hr')} bpm",
            f"- 卡路里: {snapshot.get('calories')}",
            f"- 累计爬升: {snapshot.get('elevation_gain_m')} m / 最高海拔: {snapshot.get('max_alt_m')} m",
        ]
        if snapshot.get("normalized_power") is not None:
            lines.append(f"- NP: {snapshot.get('normalized_power')} W")
        if snapshot.get("swolf") is not None:
            lines.append(f"- SWOLF: {snapshot.get('swolf')}")
        if snapshot.get("avg_cadence") is not None:
            lines.append(f"- 平均步频/踏频: {snapshot.get('avg_cadence')}")
        if snapshot.get("tss") is not None:
            lines.append(f"- TSS: {snapshot.get('tss')}")
        if snapshot.get("region"):
            lines.append(f"- 区域: {snapshot.get('region')}")
        lines.append("")
        lines.append("【重要】以上数值来自系统数据库(唯一真值),优先于轨迹明细表中的任何前端推算值。")
        return "\n".join(lines)

    @staticmethod
    def _semicircle_to_deg(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value) * SEMICIRCLE_SCALE
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_sport(value: Any) -> str:
        if value is None:
            return "unknown"
        token = str(value).strip().lower().replace("-", "_").replace(" ", "_")
        if any(m in token for m in (".fit", ".gpx", ".kml", "/", "\\")):
            return "unknown"
        return SPORT_ALIASES.get(token, token or "unknown")

    @staticmethod
    def _fmt_date_label(value: Any) -> str:
        if value is None:
            return ""
        from datetime import datetime, timedelta, timezone
        try:
            if isinstance(value, datetime):
                dt = value
            else:
                s = str(value).replace("\x00", "").strip()
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            bj_tz = timezone(timedelta(hours=8))
            dt_local = dt.astimezone(bj_tz)
            return dt_local.strftime("%Y-%m-%d")
        except (ValueError, TypeError, OverflowError):
            return ""

    @staticmethod
    def _fmt_distance(km: Any) -> str:
        try:
            d = float(km)
        except (TypeError, ValueError):
            return "-- km"
        if d >= 1.0:
            return f"{d:.2f} km"
        return f"{int(d * 1000)} m"

    @staticmethod
    def _fmt_duration(sec: Any) -> str:
        try:
            s = int(float(sec))
        except (TypeError, ValueError):
            return "--:--"
        h, m = divmod(s, 3600)
        m, s = divmod(m, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    @staticmethod
    def _fmt_pace(pace_sec: Any, unit: str = "/km") -> str:
        try:
            p = float(pace_sec)
        except (TypeError, ValueError):
            return f"-- {unit}"
        if p <= 0:
            return f"-- {unit}"
        minutes = int(p // 60)
        seconds = int(round(p % 60))
        return f"{minutes}'{seconds:02d}''{unit}"

    @staticmethod
    def _fmt_elevation(m: Any) -> str:
        try:
            v = float(m)
        except (TypeError, ValueError):
            return "-- m"
        return f"{int(v)} m"

    @staticmethod
    def _fmt_device_display_name(product_code: str) -> str:
        """snake_case 产品代号 → 人类可读产品名称"""
        display = str(product_code or "").strip()
        if not display or display.lower() in ("unknown", "unknown_device", "none"):
            return "Unknown Device"
        parts = display.split("_")
        title_parts = []
        for p in parts:
            p_upper = p.upper()
            if p in ("apac", "twn", "jpn", "chn", "kor", "sea"):
                title_parts.append(f"({p_upper})")
            else:
                title_parts.append(p[0].upper() + p[1:] if p else p)
        return " ".join(title_parts)

    @staticmethod
    def _resolve_device_name(raw: dict[str, Any], meta: dict[str, Any]) -> str:
        """从 raw['file_id_mesgs'] 提取 product_id，通过 SDK profile 翻译为产品型号"""
        fid = raw.get("file_id_mesgs")
        file_id = fid[0] if isinstance(fid, list) and fid else {}

        garmin_product = file_id.get("garmin_product") if isinstance(file_id, dict) else None
        product = file_id.get("product") if isinstance(file_id, dict) else None

        if garmin_product:
            product_code = str(garmin_product).strip()
        elif product is not None:
            pid_int = int(float(product)) if product else 0
            display = _DEVICE_DISPLAY_OVERLAY.get(pid_int)
            if display:
                product_code = display
            else:
                product_code = _garmin_device_name_dict().get(pid_int, f"Garmin Product {pid_int}")
        else:
            product_code = (meta.get("device") or {}).get("name") or ""

        if not product_code or str(product_code).isdigit():
            return "Unknown Device"

        return MetricsResolver._fmt_device_display_name(product_code)

    @staticmethod
    def _classify_cardio_load(
        avg_hr: Any,
        max_hr: Any,
        resting_hr: Any = None,
        sport_type: str = "running",
        avg_power_w: Any = None,
    ) -> str:
        """V7.8:HRR-based Cardio Load(按 sport 路由)。

        跑步/游泳/徒步:HRR 比例(< 0.55 very_low ... > 0.90 extreme)
        骑行/滑雪:优先 Power(无 power 降级 HR)
        见 docs/physiology_reference.md §指标 2。
        """
        if avg_hr is None or max_hr is None or resting_hr is None:
            return "unknown"
        try:
            avg_hr_f = float(avg_hr)
            max_hr_f = float(max_hr)
            resting_hr_f = float(resting_hr)
        except (TypeError, ValueError):
            return "unknown"
        hrr_denominator = max_hr_f - resting_hr_f
        if hrr_denominator <= 0:
            return "unknown"

        dimension = _classify_sport_dimension(sport_type)
        hr_ratio = (avg_hr_f - resting_hr_f) / hrr_denominator

        # V7.8:骑行/滑雪优先 Power,无 power 降级 HR
        if dimension["uses_power"] and avg_power_w is not None:
            try:
                power_f = float(avg_power_w)
                # 简化:有功率时粗略按 250W FTP 标定
                power_pct = power_f / 250.0
                # 取 HR 比例与 power 比例的较大值(保守)
                effective = max(hr_ratio, power_pct)
            except (TypeError, ValueError):
                effective = hr_ratio
        else:
            effective = hr_ratio

        if effective < 0.55:
            return "very_low"
        if effective < 0.70:
            return "low"
        if effective < 0.80:
            return "moderate"
        if effective < 0.90:
            return "high"
        return "extreme"

    @staticmethod
    def _classify_pace_stability(pace_values: list[float]) -> str:
        if len(pace_values) < 2:
            return "unknown"
        stddev = MetricsResolver._stddev(pace_values)
        avg = sum(pace_values) / len(pace_values)
        cv = (stddev / avg * 100) if avg > 0 else 0
        if cv < 3:
            return "stable"
        if cv < 8:
            return "moderate"
        return "variable"

    @staticmethod
    def _classify_vi(
        power_stream: list[float] | None,
        sport_type: str = "running",
        duration_min: float = 0.0,
    ) -> dict[str, Any]:
        """V7.8:Variability Index = NP / AvgPower。

        见 docs/physiology_reference.md §指标 3。
        仅对 uses_power=True 的 sport 计算(cycling/mountain_biking/skiing)。
        返回:{"vi": float|None, "level": str, "np_w": float|None,
              "avg_w": float|None, "confidence": "high"|"medium"|"low"|"unavailable"}
        """
        dimension = _classify_sport_dimension(sport_type)
        if not dimension["uses_power"]:
            return {
                "vi": None, "level": "unknown", "np_w": None, "avg_w": None,
                "confidence": "unavailable",
            }
        if not power_stream or len(power_stream) < 30:
            return {
                "vi": None, "level": "unknown", "np_w": None, "avg_w": None,
                "confidence": "unavailable",
            }
        # 过滤零功率段(滑行/休息,见 reference §6 风险说明)
        nonzero = [p for p in power_stream if p > 0]
        if len(nonzero) < 30:
            return {
                "vi": None, "level": "unknown", "np_w": None, "avg_w": None,
                "confidence": "low",
            }
        avg_w = sum(nonzero) / len(nonzero)
        # NP = (1/T) * Σ(p^4) ^(1/4)
        fourth_power_mean = sum(p ** 4 for p in nonzero) / len(nonzero)
        np_w = fourth_power_mean ** 0.25
        vi = np_w / avg_w if avg_w > 0 else None
        if vi is None:
            level, confidence = "unknown", "low"
        elif vi < 1.05:
            level = "stable"
            confidence = "high" if duration_min > 10 else "medium"
        elif vi <= 1.15:
            level = "moderate"
            confidence = "high" if duration_min > 10 else "medium"
        else:
            level = "high_variance"
            confidence = "high" if duration_min > 10 else "medium"
        return {
            "vi": round(vi, 4),
            "level": level,
            "np_w": round(np_w, 1),
            "avg_w": round(avg_w, 1),
            "confidence": confidence,
        }

    @staticmethod
    def _classify_elevation(gain_m: Any, distance_km: Any) -> str:
        try:
            g = float(gain_m or 0)
        except (TypeError, ValueError):
            g = 0.0
        try:
            d = float(distance_km or 0)
        except (TypeError, ValueError):
            d = 0.0
        if d == 0:
            return "unknown"
        ratio = g / d
        if ratio < 10:
            return "flat"
        if ratio < 30:
            return "rolling_hills"
        return "mountainous"

    @staticmethod
    def _stddev(values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return math.sqrt(variance)

    # ── environment calibration (V4.0) ─────────────────────────

    @staticmethod
    def _get_heat_stress_tolerance(temp_c: float) -> float:
        """
        基于环境温度(或酷热指数)的热应激有氧解耦容忍度 (%)
        V4.0 标准：按阶梯放宽心率漂移的判定阈值
        """
        if temp_c is None:
            return 5.0  # 缺失温度时，采用常温基线

        if temp_c < 20.0:
            return 5.0   # 常温基线 (Baseline)
        elif 20.0 <= temp_c < 25.0:
            return 6.5   # 中度热应激 (Moderate)
        elif 25.0 <= temp_c < 30.0:
            return 8.0   # 重度热应激 (High)
        else:
            return 10.0  # 极端热应激 (Extreme)

    @staticmethod
    def _calibrate_hr_for_altitude(hr_raw: float, altitude_m: float) -> float:
        """
        高海拔缺氧心率代偿校准 (V4.0 标准)
        在海拔 > 1500m 时，引入缺氧惩罚因子动态下调心率，防止模型误判效率下降
        """
        if hr_raw is None or hr_raw <= 0:
            return 0.0

        if altitude_m is None or altitude_m <= 1500.0:
            return float(hr_raw)

        # 超过 1500m 启动缺氧惩罚因子
        alpha_alt = 1.0 - (max(0.0, altitude_m - 1500.0) * 0.00003)

        # 兜底：防止极端错误海拔（如飞到平流层）导致除零或过度放大，限制最小为 0.7
        alpha_alt = max(0.7, alpha_alt)

        return float(hr_raw / alpha_alt)

    # ── calories & bonk engine (V4.0) ─────────────────────────

    @staticmethod
    def _calculate_calories_per_minute(hr: float, weight_kg: float = 70.0, age_yrs: float = 30.0, is_male: bool = True) -> float:
        """
        基于 Keytel (2005) 严谨多因子心率模型的卡路里消耗推演 (kcal/min)
        无功率时，该公式是推演糖原消耗的最佳医学依据。
        """
        if hr is None or hr <= 60:
            return 0.0

        if is_male:
            ee = (-55.0969 + 0.6309 * hr + 0.1988 * weight_kg + 0.2017 * age_yrs) / 4.184
        else:
            ee = (-20.4022 + 0.4472 * hr + 0.1263 * weight_kg + 0.0740 * age_yrs) / 4.184

        return max(0.0, ee)

    # === V7.8 指标 1:Glycogen Depletion Risk(替代 _detect_bonk_event 硬阈值)===
    # 见 docs/physiology_reference.md §指标 1
    _GLYCOGEN_RISK_ZONES: dict[str, tuple[float, float]] = {
        "running":         (1400.0, 1800.0),
        "trail_running":   (1600.0, 2200.0),
        "cycling":         (1800.0, 2400.0),
        "mountain_biking": (1800.0, 2400.0),
        "hiking":          (1400.0, 1800.0),
        "swimming":        (1200.0, 1600.0),
        "open_water":      (1200.0, 1600.0),
        "skiing":          (1600.0, 2200.0),
        "default":         (1400.0, 1800.0),
    }

    @staticmethod
    def _assess_glycogen_depletion_risk(
        total_calories: float,
        sport_type: str = "running",
    ) -> dict[str, Any]:
        """V7.8 区间模型糖原耗竭风险评估。

        返回 dict 字段:
          risk_level:  "low" | "moderate" | "high" | "unknown"
          kcal:        float
          zone:        [lower, upper] kcal 区间
          confidence:  "medium" | "low" | "unavailable"

        不输出二元 bonk: true/false(过于绝对化,见 reference §6 风险说明)
        """
        kcal = float(total_calories or 0.0)
        zone = MetricsResolver._GLYCOGEN_RISK_ZONES.get(
            str(sport_type or "").lower(),
            MetricsResolver._GLYCOGEN_RISK_ZONES["default"],
        )
        lower, upper = zone

        if kcal <= 0:
            level, confidence = "unknown", "unavailable"
        elif kcal < lower:
            level, confidence = "low", "medium"
        elif kcal <= upper:
            level, confidence = "moderate", "medium"
        else:
            level, confidence = "high", "medium"

        return {
            "risk_level": level,
            "kcal": round(kcal, 1),
            "zone": [lower, upper],
            "confidence": confidence,
        }

    @staticmethod
    def _build_bonk_risk(
        total_calories: float,
        sport_type: str = "running",
        bonk_events: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Build the review-facing Bonk risk object from Resolver truth."""
        risk = MetricsResolver._assess_glycogen_depletion_risk(
            total_calories=total_calories,
            sport_type=sport_type,
        )
        risk_level = str(risk.get("risk_level") or "unknown")
        has_event = bool(bonk_events)
        is_at_risk = has_event and risk_level in {"moderate", "high"}
        event_confidences = {
            str(ev.get("confidence") or "").lower()
            for ev in bonk_events or []
            if isinstance(ev, dict)
        }
        if risk.get("confidence") == "unavailable":
            confidence = "unavailable"
        elif "high" in event_confidences:
            confidence = "high"
        else:
            confidence = "medium" if is_at_risk else "low"

        result = {
            "is_at_risk": bool(is_at_risk),
            "confidence": confidence,
            "risk_level": risk_level,
            "kcal": risk.get("kcal"),
            "zone": risk.get("zone"),
        }
        if bonk_events:
            first = next((ev for ev in bonk_events if isinstance(ev, dict)), None)
            if first:
                for key in ("risk_start_km", "risk_end_km", "evidence"):
                    if key in first:
                        result[key] = first.get(key)
        return result

    @staticmethod
    def _build_review_decoupling(efficiency_curve: list) -> dict[str, Any]:
        """Build the review-facing decoupling metric from efficiency curve."""
        result: dict[str, Any] = {
            "pct": 0.0,
            "level": "unknown",
        }
        if not efficiency_curve or len(efficiency_curve) < 2:
            return result

        split_idx = len(efficiency_curve) // 2
        first_half = [
            float(v)
            for v in efficiency_curve[:split_idx]
            if v and v > 0
        ]
        second_half = [
            float(v)
            for v in efficiency_curve[split_idx:]
            if v and v > 0
        ]
        if not first_half or not second_half:
            return result

        early_efficiency = sum(first_half) / len(first_half)
        late_efficiency = sum(second_half) / len(second_half)
        if early_efficiency <= 0:
            return result

        pct = round(abs(early_efficiency - late_efficiency) / early_efficiency * 100.0, 2)
        if pct < 5:
            level = "excellent"
        elif pct < 10:
            level = "good"
        elif pct < 15:
            level = "warn"
        else:
            level = "bad"

        return {
            "pct": pct,
            "level": level,
            "confidence": "medium",
            "early_efficiency": round(early_efficiency, 4),
            "late_efficiency": round(late_efficiency, 4),
        }

    @staticmethod
    def _calculate_track_difficulty(
        dist_km: float,
        gain_m: float,
        max_alt_m: float,
        max_single_climb_m: float,
        sport_type: str = "running",
    ) -> dict[str, Any]:
        """V4.0: 多模态脉图轨迹难度指数 (MTDI)

        §V4.0 防腐层契约:本方法从 main.py 下沉,纯计算,无 IO
        §2.1 / §2.2 / §2.4: 难度为唯一可信计算,禁止前端复算、禁止 AI 重算

        难度阈值(从 main.py 整体迁移):
          1 (LV1)   score < 8
          2 (LV2)   8  <= score < 16
          3 (LV3)   16 <= score < 29
          4 (LV4)   29 <= score < 46
          5 (LV5)   46 <= score < 76
          6 (LV6)   76 <= score < 111
          7 (LV7)   111 <= score < 181
          8 (LV8)   score >= 181
        """
        # 难度等级阈值(从 main.py MTDI_LEVEL_THRESHOLDS 迁移)
        _MTDI_LEVEL_THRESHOLDS: tuple[float, ...] = (8, 16, 29, 46, 76, 111, 181)

        dist = max(0, dist_km or 0)
        gain = max(0, gain_m or 0)
        max_alt = max(0, max_alt_m or 0)
        max_climb = max(0, max_single_climb_m or 0)

        sport_str = str(sport_type or "").lower()
        if "cycl" in sport_str or "bik" in sport_str or "骑" in sport_str:
            dist_factor = 3.0
            gain_factor = 120.0
            if "mountain" in sport_str or "山地" in sport_str:
                dist_factor = 2.0
        else:
            dist_factor = 1.0
            gain_factor = 100.0

        base_score = (dist / dist_factor) + (gain / gain_factor)
        k_alt = 1.0 + max(0, (max_alt - 2000) / 20000.0)
        p_climb = max_climb / gain_factor
        mtdi_score = (base_score * k_alt) + p_climb

        level = 1
        for threshold in _MTDI_LEVEL_THRESHOLDS:
            if mtdi_score >= threshold:
                level += 1
            else:
                break

        return {
            "score": round(mtdi_score, 1),
            "level": int(level),
            "level_name": f"LV {level}",
            "factors": {
                "dist_factor": dist_factor,
                "gain_factor": gain_factor,
                "base_score": round(base_score, 2),
                "k_alt": round(k_alt, 3),
                "p_climb": round(p_climb, 2),
            },
        }

    @staticmethod
    def _calculate_fatigue_zones(
        distance_curve: list[float],
        ei_curve: list[float],
        sport_type: str,
        avg_hr: Any = None,
        profile_max_hr: Any = None,
        profile_resting_hr: Any = None,
    ) -> list[dict[str, Any]]:
        """V4.0: 基于 sport_type 敏感度和真实 distance_curve 的疲劳带判定

        §V4.0 防腐层契约:本方法从 main.py 下沉,消除重复业务计算
        §§五 AI 边界:仅消费 Resolver 内部 distance_curve / ei_curve,无外部 IO
        修复原 for 循环修改 i 无效的致命 Bug(改用 while)
        修复原线性均摊距离错误(改用真实 distance_curve)
        """
        if not distance_curve or not ei_curve or len(distance_curve) != len(ei_curve):
            return []

        n = len(ei_curve)
        if n < 10:
            return []

        sport_type = sport_type.lower()
        hrr_ratio: float | None = None
        try:
            avg_hr_f = float(avg_hr)
            max_hr_f = float(profile_max_hr)
            resting_hr_f = float(profile_resting_hr)
            denominator = max_hr_f - resting_hr_f
            if avg_hr_f > 0 and denominator > 0:
                hrr_ratio = (avg_hr_f - resting_hr_f) / denominator
        except (TypeError, ValueError):
            hrr_ratio = None

        if sport_type in ("running", "trail_running", "treadmill_running"):
            # Easy aerobic runs often have noisy EI/GAP early in the activity. If the
            # personal HRR intensity is clearly easy, avoid turning curve noise into
            # a sustained "fatigue/pressure" claim.
            if hrr_ratio is not None and hrr_ratio < 0.65:
                return []
            window = max(3, n // 40)
            threshold_warn = 0.10
            threshold_high = 0.20
            if hrr_ratio is not None and hrr_ratio < 0.75:
                threshold_warn = 0.16
                threshold_high = 0.28
        elif sport_type in ("hiking", "walking", "mountaineering"):
            window = max(5, n // 20)
            threshold_warn = 0.18
            threshold_high = 0.35
        elif sport_type in ("cycling", "road_cycling", "mountain_biking"):
            window = max(5, n // 25)
            threshold_warn = 0.15
            threshold_high = 0.30
        else:
            window = max(3, n // 30)
            threshold_warn = 0.15
            threshold_high = 0.30

        fatigue_zones: list[dict[str, Any]] = []
        cur_start_idx: int | None = None
        cur_start_val: float | None = None

        i = 0
        while i <= n - window:
            wnd = [v for v in ei_curve[i : i + window] if v and v > 0]
            if not wnd:
                i += 1
                continue

            avg = sum(wnd) / len(wnd)

            if cur_start_idx is None:
                cur_start_idx = i
                cur_start_val = avg
            else:
                drop_rate = (cur_start_val - avg) / cur_start_val if cur_start_val > 0 else 0
                if drop_rate >= threshold_warn:
                    if i - cur_start_idx >= window:
                        level = "high" if drop_rate >= threshold_high else "medium"
                        # 使用实际累积距离,避免线性均摊的虚假距离
                        start_km = round(distance_curve[cur_start_idx] / 1000.0, 2)
                        end_km = round(distance_curve[i] / 1000.0, 2)
                        if end_km > start_km:
                            fatigue_zones.append({
                                "start_km": start_km,
                                "end_km": end_km,
                                "level": level,
                            })
                        cur_start_idx = i
                        cur_start_val = avg
                else:
                    cur_start_val = avg
            i += window

        # 处理未收尾的最后一段
        if cur_start_idx is not None and n - cur_start_idx >= window:
            wnd_end = [v for v in ei_curve[cur_start_idx + window : n] if v and v > 0]
            if wnd_end and cur_start_val:
                avg_end = sum(wnd_end) / len(wnd_end)
                drop_rate = (cur_start_val - avg_end) / cur_start_val if cur_start_val > 0 else 0
                if drop_rate >= threshold_warn:
                    level = "high" if drop_rate >= threshold_high else "medium"
                    start_km = round(distance_curve[cur_start_idx] / 1000.0, 2)
                    end_km = round(distance_curve[-1] / 1000.0, 2)
                    if end_km > start_km:
                        fatigue_zones.append({
                            "start_km": start_km,
                            "end_km": end_km,
                            "level": level,
                        })

        return fatigue_zones

    @staticmethod
    def _energy_reserve_risk_layer(
        distance_curve: list[float],
        time_curve: list[float] | None,
        total_calories: float,
        sport_type: str = "running",
        weight_kg: Any = None,
        avg_hr: Any = None,
        profile_max_hr: Any = None,
        profile_resting_hr: Any = None,
        lactate_threshold_hr: Any = None,
        vo2max: Any = None,
    ) -> dict[str, Any]:
        """Estimate energy-reserve risk without producing a point event."""
        base = MetricsResolver._assess_glycogen_depletion_risk(
            total_calories=total_calories,
            sport_type=sport_type,
        )
        level = str(base.get("risk_level") or "unknown")
        kcal = MetricsResolver._safe_float_zero(total_calories)
        if not distance_curve or len(distance_curve) < 2:
            base.update({
                "risk_level": "unknown",
                "confidence": "unavailable",
                "factors": ["distance_curve_missing"],
            })
            return base

        distances = [MetricsResolver._safe_float(d) for d in distance_curve]
        distances = [d for d in distances if d is not None]
        if len(distances) < 2:
            base.update({
                "risk_level": "unknown",
                "confidence": "unavailable",
                "factors": ["distance_curve_missing"],
            })
            return base

        total_dist_m = max(distances) - min(distances)
        total_km = total_dist_m / 1000.0
        duration_sec = 0.0
        if time_curve and len(time_curve) >= 2:
            time_vals = [MetricsResolver._safe_float(v) for v in time_curve]
            time_vals = [v for v in time_vals if v is not None]
            if len(time_vals) >= 2:
                duration_sec = max(time_vals) - min(time_vals)
        duration_min = duration_sec / 60.0 if duration_sec > 0 else 0.0

        weight = MetricsResolver._safe_float(weight_kg)
        kcal_per_kg = kcal / weight if weight and weight > 25 else None
        kcal_per_hour = kcal / (duration_sec / 3600.0) if duration_sec > 0 else None
        hrr_ratio = None
        threshold_ratio = None
        try:
            avg_hr_f = float(avg_hr)
            max_hr_f = float(profile_max_hr)
            resting_hr_f = float(profile_resting_hr)
            if avg_hr_f > 0 and max_hr_f > resting_hr_f:
                hrr_ratio = (avg_hr_f - resting_hr_f) / (max_hr_f - resting_hr_f)
        except (TypeError, ValueError):
            hrr_ratio = None
        try:
            avg_hr_f = float(avg_hr)
            lthr_f = float(lactate_threshold_hr)
            if avg_hr_f > 0 and lthr_f > 0:
                threshold_ratio = avg_hr_f / lthr_f
        except (TypeError, ValueError):
            threshold_ratio = None

        score = {"unknown": 0, "low": 0, "moderate": 2, "high": 4}.get(level, 0)
        factors: list[str] = [f"kcal={round(kcal, 1)}"]
        if total_km > 0:
            factors.append(f"distance_km={round(total_km, 2)}")
        if duration_min > 0:
            factors.append(f"duration_min={round(duration_min, 1)}")
        if kcal_per_kg is not None:
            factors.append(f"kcal_per_kg={round(kcal_per_kg, 1)}")
            if kcal_per_kg >= 22:
                score += 2
            elif kcal_per_kg >= 16:
                score += 1
        if kcal_per_hour is not None:
            factors.append(f"kcal_per_hour={round(kcal_per_hour, 0)}")
            if kcal_per_hour >= 800:
                score += 1
        if hrr_ratio is not None:
            factors.append(f"hrr_ratio={round(hrr_ratio, 2)}")
            if hrr_ratio >= 0.78:
                score += 2
            elif hrr_ratio >= 0.68:
                score += 1
        if threshold_ratio is not None:
            factors.append(f"threshold_ratio={round(threshold_ratio, 2)}")
            if threshold_ratio >= 0.96:
                score += 2
            elif threshold_ratio >= 0.90:
                score += 1
        vo2 = MetricsResolver._safe_float(vo2max)
        if vo2 and vo2 > 0:
            factors.append(f"vo2max={round(vo2, 1)}")

        sport = str(sport_type or "").lower()
        if sport in {"running", "trail_running", "treadmill_running"}:
            short_distance_km = 12.0
        elif sport in {"cycling", "road_cycling", "mountain_biking"}:
            short_distance_km = 35.0
        else:
            short_distance_km = 8.0
        if (
            kcal < float(base.get("zone", [1400.0])[0])
            or (total_km and total_km < short_distance_km and duration_min and duration_min < 75)
        ):
            score = min(score, 1)
            factors.append("short_or_low_energy_activity")

        if base.get("confidence") == "unavailable":
            final_level, confidence = "unknown", "unavailable"
        elif score >= 5:
            final_level, confidence = "high", "high"
        elif score >= 3:
            final_level, confidence = "moderate", "medium"
        else:
            final_level, confidence = "low", "medium"

        base.update({
            "risk_level": final_level,
            "confidence": confidence,
            "score": int(score),
            "distance_km": round(total_km, 2),
            "duration_min": round(duration_min, 1) if duration_min else None,
            "kcal_per_kg": round(kcal_per_kg, 1) if kcal_per_kg is not None else None,
            "hrr_ratio": round(hrr_ratio, 3) if hrr_ratio is not None else None,
            "threshold_ratio": round(threshold_ratio, 3) if threshold_ratio is not None else None,
            "factors": factors,
        })
        return base

    @staticmethod
    def _detect_energy_gap_performance_window(
        distance_curve: list[float],
        ei_curve: list[float],
        speed_curve: list[float] | None = None,
        hr_curve: list[float] | None = None,
        cadence_curve: list[float] | None = None,
        power_curve: list[float] | None = None,
    ) -> dict[str, Any] | None:
        """Find a sustained performance-evidence window without a half-distance anchor."""
        if not distance_curve or not ei_curve or len(distance_curve) != len(ei_curve) or len(ei_curve) < 20:
            return None
        n = len(ei_curve)
        d0 = MetricsResolver._safe_float(distance_curve[0])
        d1 = MetricsResolver._safe_float(distance_curve[-1])
        if d0 is None or d1 is None or d1 <= d0:
            return None
        total_km = (d1 - d0) / 1000.0
        if total_km <= 0:
            return None

        def valid_values(series: list[Any], start: int, end: int) -> list[float]:
            return [
                float(v)
                for v in series[max(0, start):min(n, end)]
                if MetricsResolver._safe_float(v) is not None and float(v) > 0
            ]

        def avg(series: list[Any], start: int, end: int) -> float | None:
            vals = valid_values(series, start, end)
            if len(vals) < max(3, (end - start) // 3):
                return None
            return sum(vals) / len(vals)

        window = max(5, min(24, n // 8))
        confirm = max(3, window // 2)
        min_start_idx = max(window, int(n * 0.18))
        best: dict[str, Any] | None = None

        for i in range(min_start_idx, n - window + 1):
            pre_start = max(0, i - window)
            pre_ei = avg(ei_curve, pre_start, i)
            cur_ei = avg(ei_curve, i, i + window)
            if pre_ei is None or cur_ei is None or pre_ei <= 0:
                continue
            drop = (pre_ei - cur_ei) / pre_ei
            if drop < 0.12:
                continue

            confirm_end = min(n, i + window + confirm)
            follow_ei = avg(ei_curve, i + confirm, confirm_end) or cur_ei
            if follow_ei > pre_ei * 0.90:
                continue

            evidence: list[str] = [f"EI持续下降约{round(drop * 100)}%"]
            score = 2
            speed_drop = None
            if speed_curve and len(speed_curve) == n:
                pre_speed = avg(speed_curve, pre_start, i)
                cur_speed = avg(speed_curve, i, i + window)
                if pre_speed and cur_speed and pre_speed > 0:
                    speed_drop = (pre_speed - cur_speed) / pre_speed
                    if speed_drop >= 0.06:
                        score += 1
                        evidence.append("速度/配速同步变差")
            if hr_curve and len(hr_curve) == n:
                pre_hr = avg(hr_curve, pre_start, i)
                cur_hr = avg(hr_curve, i, i + window)
                if pre_hr and cur_hr:
                    if cur_hr >= pre_hr + 3 and speed_drop is not None and speed_drop >= 0.03:
                        score += 1
                        evidence.append("心率压力没有随掉速同步缓解")
                    elif cur_hr <= pre_hr - 4 and speed_drop is not None and speed_drop >= 0.08:
                        score += 1
                        evidence.append("心率和速度同时回落，可能出现明显乏力")
            if cadence_curve and len(cadence_curve) == n:
                pre_cad = avg(cadence_curve, pre_start, i)
                cur_cad = avg(cadence_curve, i, i + window)
                if pre_cad and cur_cad and pre_cad > 0 and (pre_cad - cur_cad) / pre_cad >= 0.04:
                    score += 1
                    evidence.append("步频同步下降")
            if power_curve and len(power_curve) == n:
                pre_power = avg(power_curve, pre_start, i)
                cur_power = avg(power_curve, i, i + window)
                if pre_power and cur_power and pre_power > 0 and (pre_power - cur_power) / pre_power >= 0.06:
                    score += 1
                    evidence.append("功率输出同步下降")

            if score < 3:
                continue

            start_km = round((float(distance_curve[i]) - d0) / 1000.0, 2)
            end_idx = min(n - 1, i + window + confirm - 1)
            end_km = round((float(distance_curve[end_idx]) - d0) / 1000.0, 2)
            if end_km <= start_km:
                continue

            candidate = {
                "start_idx": i,
                "end_idx": end_idx,
                "risk_start_km": start_km,
                "risk_end_km": end_km,
                "value_y": round(cur_ei, 4),
                "drop_pct": round(drop * 100.0, 1),
                "confidence": "high" if score >= 5 else "medium",
                "score": score,
                "evidence": evidence,
            }
            if best is None or candidate["score"] > best["score"] or (
                candidate["score"] == best["score"] and candidate["start_idx"] < best["start_idx"]
            ):
                best = candidate

        return best

    @staticmethod
    def _detect_bonk_event(
        distance_curve: list[float],
        ei_curve: list[float],
        total_calories: float,
        sport_type: str = "running",
        time_curve: list[float] | None = None,
        hr_curve: list[float] | None = None,
        speed_curve: list[float] | None = None,
        cadence_curve: list[float] | None = None,
        power_curve: list[float] | None = None,
        weight_kg: Any = None,
        avg_hr: Any = None,
        profile_max_hr: Any = None,
        profile_resting_hr: Any = None,
        lactate_threshold_hr: Any = None,
        vo2max: Any = None,
    ) -> list[dict]:
        """Detect energy-gap risk clues from reserve risk and sustained evidence.

        The event location is a risk-window start, not an exact bonk point.
        """
        reserve = MetricsResolver._energy_reserve_risk_layer(
            distance_curve=distance_curve,
            time_curve=time_curve,
            total_calories=total_calories,
            sport_type=sport_type,
            weight_kg=weight_kg,
            avg_hr=avg_hr,
            profile_max_hr=profile_max_hr,
            profile_resting_hr=profile_resting_hr,
            lactate_threshold_hr=lactate_threshold_hr,
            vo2max=vo2max,
        )
        reserve_level = str(reserve.get("risk_level") or "unknown")
        if reserve_level not in {"moderate", "high"}:
            return []

        performance = MetricsResolver._detect_energy_gap_performance_window(
            distance_curve=distance_curve,
            ei_curve=ei_curve,
            speed_curve=speed_curve,
            hr_curve=hr_curve,
            cadence_curve=cadence_curve,
            power_curve=power_curve,
        )
        if not performance:
            return []

        confidence = "high" if (
            reserve.get("confidence") == "high" and performance.get("confidence") == "high"
        ) else "medium"
        evidence = list(performance.get("evidence") or [])
        if reserve_level == "high":
            evidence.insert(0, "能量储备压力偏高")
        else:
            evidence.insert(0, "能量储备进入需留意区间")

        risk_start_km = performance.get("risk_start_km")
        risk_end_km = performance.get("risk_end_km")
        kcal = int(MetricsResolver._safe_float_zero(total_calories))
        description = (
            f"能量消耗约 {kcal} kcal，系统在 {risk_start_km:.1f}-{risk_end_km:.1f} km "
            f"识别到能量断档风险线索；这是风险窗口起点，不代表精确撞墙坐标。"
        )
        if evidence:
            description += " 主要依据：" + "、".join(evidence[:3]) + "。"

        return [{
            "type": "BONK_WARNING",
            "title": "能量断档风险线索",
            "label": "能量断档线索",
            "trigger_km": risk_start_km,
            "risk_start_km": risk_start_km,
            "risk_end_km": risk_end_km,
            "value_y": performance.get("value_y"),
            "confidence": confidence,
            "risk_level": reserve_level,
            "description": description,
            "evidence": evidence,
        }]

    # ── LTTB downsampling ─────────────────────────────────────

    @staticmethod
    def _lttb_sample(points: list[dict[str, Any]], threshold: int = 60) -> list[dict[str, Any]]:
        """LTTB (Largest-Triangle-Three-Buckets) 曲率感知降采样。

        契约依据:
          §2.1 字段全链路可追溯: 仅选择点的子集, 不修改经纬度
          §V4.0 防腐层: 纯计算无 IO, 从 main.py 整体迁移
          §十 Non-Goals: 纯本地算法, 零网络依赖

        算法来源:
          Sveinn Steinarsson 2013, "Downsampling Time Series for Visual Representation"
          (MS thesis, University of Iceland) — 公开学术算法, 无专利
          同实现广泛用于 ECharts/Highcharts 工业级图表库

        关键不变式:
          1. 起点 (index 0) 与终点 (index n-1) 强制保留
          2. 中间点按"最大三角形面积"准则选择 (曲率感知)
          3. O(n) 时间复杂度
          4. 输出点数 = min(threshold, len(points))

        Args:
            points: GPS 轨迹点列表, 每点必须含 'lat' / 'lon' 字段
            threshold: 目标采样点数, 默认 60 (适配 760x220 canvas 真实比例渲染)

        Returns:
            list[dict]: 降采样后的点列表 (按原顺序)
        """
        n = len(points)
        # 边界: 0 / 1 个点直接返回
        if n < 2:
            return list(points) if n else []
        # 边界: threshold < 2 视为 2 (LTTB 数学要求至少 2 个点)
        if threshold < 2:
            threshold = 2
        # 边界: 不需要采样
        if n <= threshold:
            return list(points)
        # 边界: threshold == 2 时仅保留首尾,无中间桶
        if threshold == 2:
            return [points[0], points[n - 1]]

        # 桶大小 (排除首尾 2 个必保留点)
        bucket_size = (n - 2) / (threshold - 2)

        sampled: list[dict[str, Any]] = []
        # 强制保留起点
        sampled.append(points[0])

        # 前一个被保留点的索引 (用于三角形面积计算)
        prev_index = 0

        # 遍历每个"选择桶"
        for i in range(1, threshold - 1):
            # 当前桶的索引范围 [start, end)
            bucket_start = int((i - 1) * bucket_size) + 1
            bucket_end = int(i * bucket_size) + 1
            # 边界修正: 最后一桶包含到 n-1 (排除终点)
            if i == threshold - 2:
                bucket_end = n - 1
            # 下一桶的第一个点 (用于三角形计算的"下一个保留点")
            next_start = int(i * bucket_size) + 1
            if next_start >= n - 1:
                next_start = n - 2  # 防止越界

            # 当前桶内计算最大三角形面积的点
            prev_p = points[prev_index]
            next_p = points[next_start]
            ax = float(prev_p.get("lon", 0) or 0)
            ay = float(prev_p.get("lat", 0) or 0)
            bx = float(next_p.get("lon", 0) or 0)
            by = float(next_p.get("lat", 0) or 0)

            max_area = -1.0
            max_index = bucket_start
            for j in range(bucket_start, bucket_end):
                p = points[j]
                cx = float(p.get("lon", 0) or 0)
                cy = float(p.get("lat", 0) or 0)
                # 三角形面积 = |(B-A) x (C-A)| / 2 (仅需绝对值,省去 /2)
                area = abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay))
                if area > max_area:
                    max_area = area
                    max_index = j

            sampled.append(points[max_index])
            prev_index = max_index

        # 强制保留终点
        sampled.append(points[n - 1])
        return sampled

    # ── lap normalization ─────────────────────────────────────

    @staticmethod
    def _normalize_laps(laps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """归一化 FIT lap_mesgs 为前端展示格式(§2.1 全链路可追溯)。

        §V4.0 防腐层契约:本方法从 main.py 整体迁移,纯计算,无 IO
        §2.1 全链路可追溯:UI 字段必须能追溯至 FIT SDK
          - avg_stance_time (FIT, ms) → stance_time_ms
          - avg_vertical_oscillation (FIT, cm) → vertical_oscillation_cm
          - avg_step_length (FIT, m) → stride_length_m
          - avg_vertical_ratio (FIT, %) → vertical_ratio_pct
          - avg_stance_time_balance (FIT, %) → stance_time_balance_pct

        Returns:
            list[dict]: 11 字段归一化圈速字典(含步频/GCT/垂直振幅/步幅比/左右平衡)
        """
        result: list[dict[str, Any]] = []
        for i, lap in enumerate(laps):
            if not isinstance(lap, dict):
                continue
            dist = MetricsResolver._num(lap.get("total_distance"))
            elapsed = MetricsResolver._num(lap.get("total_timer_time"))
            avg_hr = MetricsResolver._num(lap.get("avg_heart_rate"))
            max_hr = MetricsResolver._num(lap.get("max_heart_rate"))
            avg_power = MetricsResolver._num(lap.get("avg_power"))
            avg_cadence = MetricsResolver._num(lap.get("avg_cadence"))
            total_ascent = MetricsResolver._num(lap.get("total_ascent"))
            total_descent = MetricsResolver._num(lap.get("total_descent"))
            total_calories = MetricsResolver._num(lap.get("total_calories"))
            swolf = MetricsResolver._num(lap.get("swolf"))
            stroke_distance = MetricsResolver._num(lap.get("avg_stroke_distance"))
            swim_stroke = lap.get("swim_stroke")
            lengths = MetricsResolver._num(lap.get("lengths"))
            # V9.x 修复:增读 FIT 步态字段,§2.1 全链路可追溯,严禁硬编码 None
            # 字段名对齐 fit_engine._read_lap_data 输出(avg_ 前缀为 FIT lap 聚合值)
            stance_time_ms = MetricsResolver._safe_int_zero(lap.get("avg_stance_time")) or None
            vertical_oscillation_cm = MetricsResolver._safe_float_zero(lap.get("avg_vertical_oscillation")) or None
            stride_length_m = MetricsResolver._safe_float_zero(lap.get("avg_step_length")) or None
            # 额外跑步动态:垂直步幅比、左右平衡
            vertical_ratio_pct = MetricsResolver._safe_float_zero(lap.get("avg_vertical_ratio")) or None
            stance_time_balance_pct = MetricsResolver._safe_float_zero(lap.get("avg_stance_time_balance")) or None
            if dist == 0 and elapsed == 0:
                continue
            result.append({
                "lap_index": lap.get("lap_index", i),
                "distance_m": dist,
                "elapsed_sec": elapsed,
                "avg_hr": avg_hr if avg_hr else None,
                "max_hr": max_hr if max_hr else None,
                "avg_power": avg_power if avg_power else None,
                "avg_cadence": avg_cadence if avg_cadence else None,
                "total_ascent": total_ascent if total_ascent else None,
                "total_descent": total_descent if total_descent else None,
                "total_calories": total_calories if total_calories else None,
                "swolf": swolf if swolf else None,
                "avg_stroke_distance": stroke_distance if stroke_distance else None,
                "swim_stroke": swim_stroke if swim_stroke else None,
                "length_distance_m": round(dist / lengths, 1) if dist and lengths else None,
                "stance_time_ms": stance_time_ms,
                "vertical_oscillation_cm": vertical_oscillation_cm,
                "stride_length_m": stride_length_m,
                "vertical_ratio_pct": vertical_ratio_pct,
                "stance_time_balance_pct": stance_time_balance_pct,
            })
        return result

    # ── V10.0 任务 1:按距离桶聚合逐秒记录(骑行 5km 自动切圈) ──
    # 见 docs/cycling_auto_laps_plan.md §P0-1
    #
    # 契约:fit-arch-contrac §2.2 数据可信分层 / §2.1 字段全链路可追溯
    #   - 输入:activities.points_json 解码后的逐秒记录(来自 fit_engine._read_track_data)
    #   - 输出:与 _normalize_laps 同字段结构的圈数据
    #   - 数据层级:frontend_fallback(由 fit_sdk records 派生,非 canonical,严禁写回)
    #   - 严禁写回 laps_json(§八 8.3 canonical 只接受 fit_sdk)
    #   - 严禁进 ai_snapshots(§五 5.3 AI Snapshot 白名单)
    #
    # V10.0 R-1 修订:字段命名 source → source_type,与契约 §2.2 层级命名对齐
    #   - fit_sdk: FIT 真实圈
    #   - frontend_fallback: 本函数输出(UI 临时推导数据)
    #   - mock: 测试数据
    #   - synthetic: AI 生成数据
    _AUTO_LAP_MIN_BUCKET_M: float = 5000.0
    _NP_WINDOW_SEC: int = 30

    @staticmethod
    def _parse_record_time_to_sec(t: Any) -> float:
        """统一 record.time 字段为秒。

        支持:
          - float / int(已是秒数,FIT distance 推导的相对秒数)
          - ISO 字符串(2026-06-26T08:27:44)
          - datetime 对象
          - None → 0.0
        """
        if t is None:
            return 0.0
        if isinstance(t, (int, float)):
            return float(t)
        if isinstance(t, str):
            try:
                from datetime import datetime
                normalized = t.strip()
                if normalized.endswith("Z"):
                    normalized = normalized[:-1] + "+00:00"
                return datetime.fromisoformat(normalized).timestamp()
            except (TypeError, ValueError):
                return 0.0
        try:
            from datetime import datetime as _dt
            if isinstance(t, _dt):
                return t.timestamp()
        except Exception:
            pass
        return 0.0

    @staticmethod
    def _compute_normalized_power(
        power_values: list[Any],
        window_sec: int = 30,
    ) -> int | None:
        """标准化功率 NP:30s 滚动平均的 4 阶平均。

        §2.1 数据来源契约:输入必须是 fit_sdk record.power,严禁合成。
        数据不足 window_sec 或全为 None/0 时返回 None。
        """
        valid = [MetricsResolver._num(p) for p in power_values if p is not None]
        valid = [v for v in valid if v > 0]
        if len(valid) < window_sec:
            return None
        rolling_means: list[float] = []
        for i in range(len(valid) - window_sec + 1):
            window = valid[i:i + window_sec]
            rolling_means.append(sum(window) / window_sec)
        if not rolling_means:
            return None
        fourth_power_mean = sum(x ** 4 for x in rolling_means) / len(rolling_means)
        if fourth_power_mean <= 0:
            return None
        return int(round(fourth_power_mean ** 0.25))

    @staticmethod
    def _interpolate_time_at_distance(records: list[dict[str, Any]], target_distance_m: float) -> float:
        """在单调 distance records 中按距离线性插值 time。

        仅用于自动切圈边界。距离边界本身是 UI fallback 的分段需要,
        时间仍来自相邻 FIT record.time 的线性插值,不写回 canonical 数据。
        """
        if not records:
            return 0.0
        if target_distance_m <= records[0]["distance_m"]:
            return records[0]["time_sec"]
        if target_distance_m >= records[-1]["distance_m"]:
            return records[-1]["time_sec"]
        prev = records[0]
        for current in records[1:]:
            prev_d = prev["distance_m"]
            current_d = current["distance_m"]
            if current_d < target_distance_m:
                prev = current
                continue
            prev_t = prev["time_sec"]
            current_t = current["time_sec"]
            if current_d <= prev_d:
                return current_t
            ratio = (target_distance_m - prev_d) / (current_d - prev_d)
            return prev_t + (current_t - prev_t) * ratio
        return records[-1]["time_sec"]

    @staticmethod
    def _build_synthetic_laps_from_points(
        points: list[dict[str, Any]],
        sport_type: str,
        bucket_m: float = 5000.0,
    ) -> list[dict[str, Any]]:
        """按距离桶聚合逐秒记录,生成等效圈数据。

        V10.0 任务 1 实现,仅用于骑行类活动(FIT 只有 1 lap 或 laps_json 为空时)。

        契约:
          - 纯计算,无 IO(§V4.0 防腐层)
          - 不写回 canonical DB(§八 8.3)
          - 输出 source_type="frontend_fallback"(V10.0 R-1 修订,与契约 §2.2 层级命名一致)
          - 跑步/徒步/游泳等其他运动类型严禁调用(由调用方在 main.py 控制)

        Args:
            points: 从 activities.points_json / track_json 解码的逐秒记录
                    必含字段:distance(累积距离,米)、time(秒或ISO)、hr、power、cadence、alt
            sport_type: 运动类型字符串(仅用于 source 标签,不参与计算)
            bucket_m: 距离桶大小(米),骑行固定 5000

        Returns:
            list[dict]: 圈数据,字段结构与 _normalize_laps 完全一致
                        每项额外带 source_type="frontend_fallback"(V10.0 R-1)
        """
        # ── 防御:空数据 ──
        if not points or len(points) < 2:
            return []

        # ── 防御:bucket_m 必须为正 ──
        if bucket_m <= 0:
            return []

        # ── 清洗为单调累积距离 records ──
        raw_records: list[dict[str, Any]] = []
        last_abs_distance: float | None = None
        first_abs_distance: float | None = None
        for p in points:
            if not isinstance(p, dict) or p.get("distance") is None:
                continue
            d_abs = MetricsResolver._safe_float(p.get("distance"))
            if d_abs is None or d_abs < 0:
                continue
            if last_abs_distance is not None and d_abs < last_abs_distance:
                continue
            if first_abs_distance is None:
                first_abs_distance = d_abs
            rel_distance = d_abs - first_abs_distance
            if rel_distance < 0:
                continue
            raw_records.append({
                "distance_m": rel_distance,
                "time_sec": MetricsResolver._parse_record_time_to_sec(p.get("time")),
                "point": p,
            })
            last_abs_distance = d_abs

        if len(raw_records) < 2 or raw_records[-1]["distance_m"] <= 0:
            return []

        total_distance_m = raw_records[-1]["distance_m"]

        # ── 按精确距离边界聚合:0-5km,5-10km,...,剩余段 ──
        result: list[dict[str, Any]] = []
        segment_start = 0.0
        bucket_idx = 0
        epsilon = 1e-6
        while segment_start < total_distance_m - epsilon:
            segment_end = min(segment_start + bucket_m, total_distance_m)
            distance_m = segment_end - segment_start
            if distance_m <= 0:
                break

            # 用时(秒)
            elapsed_sec = (
                MetricsResolver._interpolate_time_at_distance(raw_records, segment_end)
                - MetricsResolver._interpolate_time_at_distance(raw_records, segment_start)
            )
            if elapsed_sec < 0:
                elapsed_sec = 0.0

            segment_records = [
                r for r in raw_records
                if segment_start <= r["distance_m"] <= segment_end
            ]
            if not segment_records:
                segment_records = [
                    r for r in raw_records
                    if segment_start < r["distance_m"] <= segment_end
                ]
            segment_points = [r["point"] for r in segment_records]

            # ── 聚合 hr / power / cadence ──
            hr_vals = [p.get("hr") for p in segment_points]
            hr_clean = [MetricsResolver._num(v) for v in hr_vals if v is not None and MetricsResolver._num(v) > 0]
            avg_hr = int(round(sum(hr_clean) / len(hr_clean))) if hr_clean else None
            max_hr = int(round(max(hr_clean))) if hr_clean else None

            power_vals = [p.get("power") for p in segment_points]
            power_clean = [MetricsResolver._num(v) for v in power_vals if v is not None and MetricsResolver._num(v) > 0]
            avg_power = int(round(sum(power_clean) / len(power_clean))) if power_clean else None
            max_power = int(round(max(power_clean))) if power_clean else None
            np_value = MetricsResolver._compute_normalized_power(power_vals, MetricsResolver._NP_WINDOW_SEC)

            cadence_vals = [p.get("cadence") for p in segment_points]
            cadence_clean = [MetricsResolver._num(v) for v in cadence_vals if v is not None and MetricsResolver._num(v) > 0]
            avg_cadence = int(round(sum(cadence_clean) / len(cadence_clean))) if cadence_clean else None

            # ── 累计爬升/下降(alt 差分累加) ──
            total_ascent = 0.0
            total_descent = 0.0
            prev_alt = None
            for p in segment_points:
                alt_raw = p.get("alt")
                alt = MetricsResolver._num(alt_raw) if alt_raw is not None else None
                if alt is None:
                    continue
                if prev_alt is not None:
                    delta = alt - prev_alt
                    if delta > 0:
                        total_ascent += delta
                    elif delta < 0:
                        total_descent += -delta
                prev_alt = alt

            # ── 平均速度(米/秒) ──
            avg_speed_mps = (distance_m / elapsed_sec) if elapsed_sec > 0 else None

            # ── 跳过空桶(防御:distance_m==0 且 elapsed_sec==0) ──
            # 同时防御:distance 全为 0 时(无有效距离数据)不应输出圈
            if distance_m == 0:
                continue

            result.append({
                "lap_index": bucket_idx,
                "distance_m": round(distance_m, 2),
                "elapsed_sec": round(elapsed_sec, 2),
                "avg_hr": avg_hr,
                "max_hr": max_hr,
                "avg_power": avg_power,
                "max_power": max_power,
                "normalized_power": np_value,
                "avg_cadence": avg_cadence,
                "total_ascent": round(total_ascent, 2),
                "total_descent": round(total_descent, 2),
                "total_calories": None,
                "avg_speed_mps": round(avg_speed_mps, 3) if avg_speed_mps is not None else None,
                "source_type": "frontend_fallback",  # V10.0 R-1:对齐契约 §2.2 层级命名
            })
            segment_start = segment_end
            bucket_idx += 1

        return result

    # === V7.9 指标 5:Efficiency Score(21d baseline 归一化) ===
    # 见 docs/physiology_reference.md §指标 5
    # 21d 中位数 baseline 是脉图自建标准(reference §3 明确标注"部分")
    _EFFICIENCY_BASELINE_WINDOW_DAYS: int = 21
    _EFFICIENCY_SCORE_BASELINE: float = 50.0
    _EFFICIENCY_SCORE_RANGE: float = 25.0
    _EFFICIENCY_MIN_HISTORY: int = 3

    @staticmethod
    def _compute_efficiency_score(
        avg_hr: float | None,
        avg_pace_sec_per_km: float | None,
        sport_type: str = "running",
        duration_sec: float = 0.0,
    ) -> dict[str, Any]:
        """V7.9 指标 5:Efficiency Score 基础比值计算。

        返回:{"score": None, "ratio": float|None, "level": "unknown",
              "confidence": "high"|"medium"|"low"|"unavailable"}

        注意:score 在 baseline 比对后才填,本函数只算 ratio。
        见 docs/physiology_reference.md §指标 5。
        """
        # V7.8 复用:sport 路由(swimming 不计算,心率测量不可靠)
        dimension = _classify_sport_dimension(sport_type)
        if dimension["uses_swolf"]:
            return {
                "score": None, "ratio": None, "level": "unknown",
                "confidence": "unavailable",
            }
        if avg_hr is None or avg_pace_sec_per_km is None or avg_pace_sec_per_km <= 0:
            return {
                "score": None, "ratio": None, "level": "unknown",
                "confidence": "unavailable",
            }
        if avg_hr <= 0:
            return {
                "score": None, "ratio": None, "level": "unknown",
                "confidence": "unavailable",
            }
        if duration_sec < 15 * 60:  # < 15 min 样本不足,见 reference §6 边界
            return {
                "score": None, "ratio": None, "level": "unknown",
                "confidence": "unavailable",
            }

        # 效率 = 速度 / 心率(高 = 高效率,慢配速低心率)
        speed_mps = 1000.0 / float(avg_pace_sec_per_km)
        ratio = speed_mps / float(avg_hr)

        return {
            "score": None,  # 由 evaluate_efficiency 在 baseline 比对后填
            "ratio": round(ratio, 6),
            "level": "unknown",
            "confidence": "high",
        }

    @staticmethod
    def _classify_steady_aerobic(
        records: list,
        duration_sec: float = 0.0,
    ) -> dict[str, Any]:
        """V7.10:steady aerobic 前置检查(见 reference §5 前置条件)。

        返回:{"is_steady_aerobic": bool, "pace_cv": float|None,
              "pause_pct": float|None, "reasons": list[str]}

        True 表示输入质量足以计算；自然变速会降置信度但不再直接屏蔽。
        """
        reasons: list[str] = []

        # 1. duration > 45 min
        if duration_sec < MetricsResolver._HR_DRIFT_MIN_DURATION_MIN * 60:
            reasons.append(
                f"duration<{MetricsResolver._HR_DRIFT_MIN_DURATION_MIN}min"
            )

        valid_hr_count = 0
        for rec in records or []:
            if not isinstance(rec, dict):
                continue
            hr = MetricsResolver._num(
                MetricsResolver._record_value(rec, "heart_rate", "hr")
            )
            if hr > 30:
                valid_hr_count += 1
        if valid_hr_count < MetricsResolver._HR_DRIFT_MIN_RECORDS:
            reasons.append(f"records<{MetricsResolver._HR_DRIFT_MIN_RECORDS}")

        # 2. 配速变异度：普通长距离自然变速只降低置信度，极端变速才排除。
        pace_values: list[float] = []
        for rec in records or []:
            if not isinstance(rec, dict):
                continue
            spd = MetricsResolver._num(
                MetricsResolver._record_value(rec, "speed", "enhanced_speed")  # V8.11
            )
            if spd and spd > 0.1:
                pace_values.append(16.6667 / spd)  # sec/km
        pace_cv: float | None = None
        if len(pace_values) >= 2:
            stddev = MetricsResolver._stddev(pace_values)
            avg = sum(pace_values) / len(pace_values)
            pace_cv = (stddev / avg * 100) if avg > 0 else 0
            if pace_cv >= MetricsResolver._HR_DRIFT_EXCLUDE_PACE_CV:
                reasons.append(
                    f"pace_cv={pace_cv:.1f}% >= {MetricsResolver._HR_DRIFT_EXCLUDE_PACE_CV}%"
                )
        elif records:
            reasons.append("missing_pace")

        # 3. 停顿占比 < 10%(过滤长时间休息)
        pause_pct: float | None = None
        if records and duration_sec > 0:
            pause_sec = 0.0
            for rec in records:
                if not isinstance(rec, dict):
                    continue
                spd = MetricsResolver._num(
                    MetricsResolver._record_value(rec, "speed", "enhanced_speed")  # V8.11
                )
                if spd is not None and spd < 0.5:
                    pause_sec += 1.0  # 简化为每条 record 1 秒
            pause_pct = (pause_sec / duration_sec) * 100
            if pause_pct >= MetricsResolver._HR_DRIFT_MAX_PAUSE_PCT:
                reasons.append(
                    f"pause_pct={pause_pct:.1f}% >= {MetricsResolver._HR_DRIFT_MAX_PAUSE_PCT}%"
                )

        return {
            "is_steady_aerobic": len(reasons) == 0,
            "pace_cv": pace_cv,
            "pause_pct": pause_pct,
            "reasons": reasons,
        }

    @staticmethod
    def _fetch_efficiency_baseline(
        db_path: str,
        sport_type: str,
        current_activity_id: int,
        window_days: int = 21,
    ) -> dict[str, Any]:
        """V7.9:从 activities 表取 21d 同 sport 历史中位数 efficiency ratio。

        §8 canonical DB 原则:只读,严禁写入。
        返回:{"baseline_ratio": float|None, "sample_size": int, "window_days": int}
        """
        import sqlite3
        from datetime import datetime, timedelta, timezone
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
            cursor.execute(
                """
                SELECT avg_hr, avg_pace, duration_sec
                FROM activities
                WHERE sport_type = ?
                  AND id != ?
                  AND start_time < ?
                  AND avg_hr IS NOT NULL
                  AND avg_pace IS NOT NULL
                  AND duration_sec > ?
                ORDER BY start_time DESC
                """,
                (sport_type, current_activity_id, cutoff_ts, 15 * 60),
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            return {"baseline_ratio": None, "sample_size": 0, "window_days": window_days}

        ratios = []
        for avg_hr, avg_pace, _dur in rows:
            if avg_pace and float(avg_pace) > 0 and avg_hr and float(avg_hr) > 0:
                speed_mps = 1000.0 / float(avg_pace)
                ratios.append(speed_mps / float(avg_hr))

        if len(ratios) < MetricsResolver._EFFICIENCY_MIN_HISTORY:
            return {
                "baseline_ratio": None,
                "sample_size": len(ratios),
                "window_days": window_days,
            }

        # 中位数(对异常值更鲁棒)
        ratios.sort()
        n = len(ratios)
        if n % 2 == 1:
            median = ratios[n // 2]
        else:
            median = (ratios[n // 2 - 1] + ratios[n // 2]) / 2
        return {
            "baseline_ratio": round(median, 6),
            "sample_size": len(ratios),
            "window_days": window_days,
        }

    # === V7.10 指标 6:HR Drift(真实算法) ===
    # 见 docs/physiology_reference.md §指标 6
    # 替换 V7.6 decoupling_pct 临时代理(main.py 注释 "V7.6 临时代理" 同步更新)
    _HR_DRIFT_MIN_DURATION_MIN: int = 45   # reference §5 前置:duration > 45min
    _HR_DRIFT_MAX_PACE_CV: float = 8.0     # 配速自然波动阈值(>8% 降低置信度)
    _HR_DRIFT_EXCLUDE_PACE_CV: float = 60.0 # 极端变速/间歇才排除漂移计算
    _HR_DRIFT_MAX_PAUSE_PCT: float = 10.0  # 停顿时长占活动总时长上限(>10% 排除)
    _HR_DRIFT_SPLIT_RATIO: float = 0.5     # 前后半程分界(50%)
    _HR_DRIFT_MIN_RECORDS: int = 20        # 至少 20 条数据点

    # === V7.11 指标 7:Durability Index(耐久指数) ===
    # 见 docs/physiology_reference.md §指标 7
    _DURABILITY_MIN_DURATION_MIN: int = 45   # reference §5 前置:duration > 45min
    _DURABILITY_HEAD_RATIO: float = 0.30      # 前 30% 切片(reference §4 自建聚合)
    _DURABILITY_TAIL_RATIO: float = 0.30      # 后 30% 切片
    _DURABILITY_MAX_SCORE: float = 100.0      # reference §6 误用 1:必须 cap
    _DURABILITY_BASELINE_SCORE: float = 100.0 # 不掉速 = 100 分

    # === V7.12 指标 8:Cadence Stability(步频稳定性) ===
    # 见 docs/physiology_reference.md §指标 8
    # 脉图自建 stability 框架(std + late_run decay),区别于行业 optimal cadence
    _CADENCE_MIN_DURATION_MIN: int = 20   # reference §7 UNAVAILABLE:duration < 20min
    _CADENCE_MIN_DURATION_HIGH: int = 30  # reference §7 HIGH:duration > 30min
    _CADENCE_MAX_CV: float = 6.0          # CV 上限(>6% 视为间歇训练)
    _CADENCE_BASELINE_SCORE: float = 100.0
    _CADENCE_STD_WEIGHT: float = 0.6      # std 部分权重
    _CADENCE_DECAY_WEIGHT: float = 0.4    # late_decay 部分权重

    # === V7.13 指标 9:Training Load(TRIMP 简化版) ===
    # 见 docs/physiology_reference.md §指标 9
    # Banister TRIMP 模型(Banister 1991) + HR-zone-weighted duration(脉图简化)
    # §6 误用 2 提示:跨 sport 不可比;前端显示需 sport_type 显式标注
    _TRAINING_LOAD_ZONE_WEIGHTS: dict = {
        "Z1": 1.0,
        "Z2": 2.0,
        "Z3": 3.0,
        "Z4": 5.0,
        "Z5": 8.0,
    }
    _TRAINING_LOAD_MAX_SCORE: float = 1000.0   # clamp 上限(防止异常活动爆表)
    _TRAINING_LOAD_MIN_DURATION_MIN: int = 5   # reference §7 推算:duration < 5min 无意义
    _TRAINING_LOAD_HIGH_DURATION_MIN: int = 30 # HIGH confidence 阈值

    @staticmethod
    def _normalize_training_load_zone_distribution(hr_zone_distribution) -> tuple[dict[str, float], list[str]]:
        """Normalize HR zone input to percentages.

        Historical rows store zone values as seconds/sample counts, while some
        tests and callers use percentages. Training load needs percentages.
        """
        if not isinstance(hr_zone_distribution, dict):
            return {}, ["invalid_zone_distribution"]

        raw: dict[str, float] = {}
        for zone_key in MetricsResolver._TRAINING_LOAD_ZONE_WEIGHTS.keys():
            try:
                value = float(hr_zone_distribution.get(zone_key) or 0.0)
            except (TypeError, ValueError):
                value = 0.0
            if value > 0:
                raw[zone_key] = value

        total = sum(raw.values())
        if total <= 0:
            return {}, ["empty_zone_distribution"]

        if total <= 1.2:
            return {k: v * 100.0 for k, v in raw.items()}, ["zone_distribution_ratios_normalized"]
        if 98.0 <= total <= 102.0:
            return raw, []
        return {k: v / total * 100.0 for k, v in raw.items()}, ["zone_distribution_counts_normalized"]

    @staticmethod
    def _training_load_hrr_zone(
        avg_hr=None,
        profile_max_hr=None,
        profile_resting_hr=None,
        resting_hr=None,
    ) -> tuple[dict | None, str | None]:
        max_hr_for_hrr = profile_max_hr
        resting_hr_for_hrr = (
            profile_resting_hr
            if profile_resting_hr is not None
            else resting_hr
        )
        try:
            avg_hr_f = float(avg_hr)
            max_hr_f = float(max_hr_for_hrr)
            resting_hr_f = float(resting_hr_for_hrr)
        except (TypeError, ValueError):
            return None, "missing_profile_max_hr_or_resting_hr"
        denominator = max_hr_f - resting_hr_f
        if avg_hr_f <= 0 or denominator <= 0:
            return None, "invalid_hrr_denominator"

        ratio = (avg_hr_f - resting_hr_f) / denominator
        if ratio < 0.55:
            zone_key, weight = "Z1", 1.0
        elif ratio < 0.70:
            zone_key, weight = "Z2", 2.0
        elif ratio < 0.80:
            zone_key, weight = "Z3", 3.0
        elif ratio < 0.90:
            zone_key, weight = "Z4", 5.0
        else:
            zone_key, weight = "Z5", 8.0
        return {"ratio": ratio, "zone_key": zone_key, "weight": weight}, None

    @staticmethod
    def _training_load_zone_distribution_conflicts_with_hrr(
        zone_pct: dict[str, float],
        hrr_zone: dict | None,
    ) -> bool:
        """Detect legacy distributions computed from activity max HR."""
        if not hrr_zone:
            return False
        hrr_ratio = hrr_zone.get("ratio")
        hrr_weight = hrr_zone.get("weight")
        if hrr_ratio is None or hrr_weight is None:
            return False
        high_pct = float(zone_pct.get("Z4", 0.0)) + float(zone_pct.get("Z5", 0.0))
        z5_pct = float(zone_pct.get("Z5", 0.0))
        zone_weighted = sum(
            MetricsResolver._TRAINING_LOAD_ZONE_WEIGHTS.get(k, 0.0) * float(v) / 100.0
            for k, v in zone_pct.items()
        )
        if hrr_ratio < 0.70 and high_pct >= 35.0 and zone_weighted >= float(hrr_weight) + 2.0:
            return True
        if hrr_ratio < 0.80 and z5_pct >= 35.0 and zone_weighted >= float(hrr_weight) + 2.5:
            return True
        return False

    @staticmethod
    def _compute_training_load(
        hr_zone_distribution=None,
        avg_hr=None,
        max_hr=None,
        resting_hr=None,
        profile_max_hr=None,
        profile_resting_hr=None,
        duration_sec: float = 0.0,
        sport_type: str = "running",
        hr_source: str = "chest_strap",
    ) -> dict:
        """V7.13 指标 9:Training Load(Banister TRIMP 简化版)。

        算法(无 zone distribution 时的降级):
          HRR = (avg_hr - resting_hr) / (profile_max_hr - resting_hr)
          用 HRR 查表映射到 zone → 用 zone 权重
          load = duration_min * zone_weight

        算法(有 zone distribution):
          load = duration_min * SUM(zone_weight * zone_time_pct / 100)

        返回:{"load": float|None, "level": str, "zone_used": str|list|None,
              "confidence": "high"|"medium"|"low"|"unavailable"}

        见 docs/physiology_reference.md §指标 9。
        """
        # 基础检查
        if duration_sec < MetricsResolver._TRAINING_LOAD_MIN_DURATION_MIN * 60:
            return {
                "load": None, "level": "unknown", "zone_used": None,
                "confidence": "unavailable",
                "reasons": ["duration<5min"],
            }

        duration_min = duration_sec / 60.0
        reasons: list[str] = []
        hrr_zone, hrr_error = MetricsResolver._training_load_hrr_zone(
            avg_hr=avg_hr,
            profile_max_hr=profile_max_hr,
            profile_resting_hr=profile_resting_hr,
            resting_hr=resting_hr,
        )

        if hr_zone_distribution:
            # 完整算法:有 HR zone 分布
            zone_pct, zone_reasons = MetricsResolver._normalize_training_load_zone_distribution(
                hr_zone_distribution
            )
            reasons.extend(zone_reasons)
            if not zone_pct:
                return {
                    "load": None, "level": "unknown", "zone_used": None,
                    "confidence": "unavailable",
                    "reasons": reasons or ["empty_zone_distribution"],
                }
            if MetricsResolver._training_load_zone_distribution_conflicts_with_hrr(zone_pct, hrr_zone):
                load = duration_min * float(hrr_zone["weight"])
                zone_used = hrr_zone["zone_key"]
                reasons.append("zone_distribution_incompatible_with_profile_hrr")
                used_hrr_fallback = True
            else:
                total_weighted = 0.0
                zone_used_list = []
                for zone_key, time_pct in zone_pct.items():
                    weight = MetricsResolver._TRAINING_LOAD_ZONE_WEIGHTS.get(zone_key, 0.0)
                    if weight > 0 and time_pct and float(time_pct) > 0:
                        total_weighted += weight * float(time_pct) / 100.0
                        zone_used_list.append(zone_key)
                load = duration_min * total_weighted
                zone_used = zone_used_list
                used_hrr_fallback = False
            load = min(load, MetricsResolver._TRAINING_LOAD_MAX_SCORE)
        elif avg_hr:
            if not hrr_zone:
                return {
                    "load": None, "level": "unknown", "zone_used": None,
                    "confidence": "unavailable",
                    "reasons": [hrr_error or "missing_profile_max_hr_or_resting_hr"],
                }
            # 降级算法:用个人 HRR 推算主要 zone,不得用单次活动 max_hr 冒充最大心率。
            load = duration_min * float(hrr_zone["weight"])
            load = min(load, MetricsResolver._TRAINING_LOAD_MAX_SCORE)
            zone_used = hrr_zone["zone_key"]
            used_hrr_fallback = True
        else:
            return {
                "load": None, "level": "unknown", "zone_used": None,
                "confidence": "unavailable",
                "reasons": ["missing_hr"],
            }

        # 等级判定(脉图自建阈值,可调)
        if load >= 400:
            level = "very_high"
        elif load >= 250:
            level = "high"
        elif load >= 120:
            level = "moderate"
        elif load >= 50:
            level = "low"
        else:
            level = "very_low"

        # confidence 校正(reference §7 4 级条件)
        confidence = "high"
        if hr_source == "optical":
            confidence = "medium"
        if not hr_zone_distribution or used_hrr_fallback:
            confidence = "medium"  # MEDIUM:无 zone distribution(基于 avg_hr 推算)
        if sport_type == "swimming":
            confidence = "medium"  # MEDIUM:游泳 HR 可靠性标 MEDIUM
        if duration_sec < MetricsResolver._TRAINING_LOAD_HIGH_DURATION_MIN * 60:
            confidence = "medium"  # MEDIUM:duration 5-30min

        return {
            "load": round(load, 1),
            "level": level,
            "zone_used": zone_used,
            "confidence": confidence,
            "reasons": reasons,
        }

    @staticmethod
    def _compute_cadence_stability(
        cadence_stream: list | None,
        duration_sec: float = 0.0,
        sport_type: str = "running",
        is_intermittent: bool = False,
    ) -> dict:
        """V7.12 指标 8:Cadence Stability(std + late_decay,0-100 分)。

        算法:
          std_score  = 100 * max(0, 1 - cv / 6.0)         # std 部分(CV 越小越稳)
          decay_pct  = (avg_late - avg_early) / avg_early # 后期步频衰减
          decay_score = 100 * max(0, 1 + decay_pct / 0.10) # 衰减 < 10% 给满分
          score = std_score * 0.6 + decay_score * 0.4

        返回:{"score": float|None, "level": str, "cv": float|None,
              "decay_pct": float|None, "is_intermittent": bool,
              "confidence": "high"|"medium"|"low"|"unavailable"}

        见 docs/physiology_reference.md §指标 8。
        """
        # 仅 running / trail_running 适用(reference §5)
        if sport_type not in ("running", "trail_running"):
            return {
                "score": None, "level": "unknown",
                "cv": None, "decay_pct": None,
                "is_intermittent": False,
                "confidence": "unavailable",
            }

        # 前置检查
        if not cadence_stream or len(cadence_stream) < 20:
            return {
                "score": None, "level": "unknown",
                "cv": None, "decay_pct": None,
                "is_intermittent": False,
                "confidence": "unavailable",
            }
        if duration_sec < MetricsResolver._CADENCE_MIN_DURATION_MIN * 60:
            return {
                "score": None, "level": "unknown",
                "cv": None, "decay_pct": None,
                "is_intermittent": False,
                "confidence": "unavailable",
            }

        # 过滤 0 / 异常值(Garmin 静止时输出 0)
        valid = [c for c in cadence_stream if c and c > 30]  # 正常步频 > 30 spm
        if len(valid) < 20:
            return {
                "score": None, "level": "unknown",
                "cv": None, "decay_pct": None,
                "is_intermittent": False,
                "confidence": "unavailable",
            }

        n = len(valid)
        avg_cad = sum(valid) / n
        stddev = MetricsResolver._stddev(valid)
        cv = (stddev / avg_cad * 100) if avg_cad > 0 else 0

        # 间歇训练检测(reference §6 误用 1:CV > 6%)
        if cv > MetricsResolver._CADENCE_MAX_CV or is_intermittent:
            return {
                "score": None, "level": "unknown",
                "cv": round(cv, 2), "decay_pct": None,
                "is_intermittent": True,
                "confidence": "low",
            }

        # 前后半程步频均值
        half_idx = n // 2
        early_cad = sum(valid[:half_idx]) / half_idx
        late_cad = sum(valid[half_idx:]) / (n - half_idx)
        decay_pct_val: float | None
        if early_cad <= 0:
            decay_pct_val = None
            decay_score = 0.0
        else:
            decay_pct_val = round(
                (late_cad - early_cad) / early_cad * 100.0, 2
            )
            # 衰减 < 10% 给满分;每衰减 10% 扣 100 分(扣到 0)
            decay_score = max(
                0.0,
                min(100.0, 100.0 * (1 + decay_pct_val / 10.0)),
            )

        # std 部分:CV 越小越稳
        std_score = max(
            0.0,
            min(100.0, 100.0 * (1 - cv / MetricsResolver._CADENCE_MAX_CV)),
        )

        score = std_score * MetricsResolver._CADENCE_STD_WEIGHT +                 decay_score * MetricsResolver._CADENCE_DECAY_WEIGHT
        score = round(max(0.0, min(100.0, score)), 1)

        # 等级判定
        if score >= 90:
            level = "excellent"
        elif score >= 75:
            level = "good"
        elif score >= 60:
            level = "warn"
        else:
            level = "bad"

        # confidence 校正(reference §7 4 级条件)
        confidence = "high"
        if sport_type == "trail_running":
            confidence = "medium"  # MEDIUM:trail running(地形影响)
        if duration_sec < MetricsResolver._CADENCE_MIN_DURATION_HIGH * 60:
            confidence = "medium"  # MEDIUM:duration 20-30min

        return {
            "score": score,
            "level": level,
            "cv": round(cv, 2),
            "decay_pct": decay_pct_val,
            "is_intermittent": False,
            "confidence": confidence,
        }

    @staticmethod
    def _compute_durability_index(
        speed_stream: list | None,
        duration_sec: float = 0.0,
        sport_type: str = "running",
        is_race: bool = False,
    ) -> dict:
        """V7.11 指标 7:Durability Index(前 30% vs 后 30% 速度比,0-100 分)。

        算法:
          head_speed = avg(speed_stream[:30%])
          tail_speed = avg(speed_stream[-30%:])
          ratio = tail_speed / head_speed
          score = 100 * ratio  (cap 在 [0, 100])

        返回:{"score": float|None, "level": str, "head_speed": float|None,
              "tail_speed": float|None, "is_splitable": bool,
              "confidence": "high"|"medium"|"low"|"unavailable"}

        见 docs/physiology_reference.md §指标 7。
        """
        # V7.8 复用:sport 路由(swimming 不计算)
        dimension = _classify_sport_dimension(sport_type)
        if dimension["uses_swolf"]:
            return {
                "score": None, "level": "unknown",
                "head_speed": None, "tail_speed": None,
                "is_splitable": False,
                "confidence": "unavailable",
            }

        # 前置检查
        if duration_sec < MetricsResolver._DURABILITY_MIN_DURATION_MIN * 60:
            return {
                "score": None, "level": "unknown",
                "head_speed": None, "tail_speed": None,
                "is_splitable": False,
                "confidence": "unavailable",
            }
        if not speed_stream or len(speed_stream) < 20:
            return {
                "score": None, "level": "unknown",
                "head_speed": None, "tail_speed": None,
                "is_splitable": False,
                "confidence": "unavailable",
            }

        # 过滤无效值(0 / 负值)
        valid = [s for s in speed_stream if s and s > 0]
        if len(valid) < 20:
            return {
                "score": None, "level": "unknown",
                "head_speed": None, "tail_speed": None,
                "is_splitable": False,
                "confidence": "unavailable",
            }

        n = len(valid)
        head_idx = max(1, int(n * MetricsResolver._DURABILITY_HEAD_RATIO))
        tail_idx = max(1, int(n * MetricsResolver._DURABILITY_TAIL_RATIO))

        head_speed = sum(valid[:head_idx]) / head_idx
        tail_speed = sum(valid[-tail_idx:]) / tail_idx

        if head_speed <= 0:
            return {
                "score": None, "level": "unknown",
                "head_speed": None, "tail_speed": None,
                "is_splitable": False,
                "confidence": "unavailable",
            }

        ratio = tail_speed / head_speed
        # 100 * ratio, cap [0, 100](reference §6 误用 1:negative split 不能超 100)
        score = max(
            0.0,
            min(
                MetricsResolver._DURABILITY_MAX_SCORE,
                MetricsResolver._DURABILITY_BASELINE_SCORE * ratio,
            ),
        )

        # 等级判定
        if score >= 95:
            level = "excellent"
        elif score >= 85:
            level = "good"
        elif score >= 70:
            level = "warn"
        else:
            level = "bad"

        # confidence 校正(reference §7 4 级条件)
        confidence = "high"
        if duration_sec < 60 * 60:  # 45-60min → MEDIUM
            confidence = "medium"
        if is_race:
            confidence = "low"  # LOW:比赛配速策略(reference §7)

        return {
            "score": round(score, 1),
            "level": level,
            "head_speed": round(head_speed, 4),
            "tail_speed": round(tail_speed, 4),
            "is_splitable": True,
            "confidence": confidence,
        }

    @staticmethod
    def _compute_hr_drift(
        records: list,
        duration_sec: float = 0.0,
    ) -> dict[str, Any]:
        """V7.10 指标 6:HR Drift 真实算法。

        算法:drift_pct = (avg_hr_late - avg_hr_early) / avg_hr_early × 100
        前置:duration > 45min + 足够心率样本 + 无极端变速/长停顿。

        返回:{"drift_pct": float|None, "level": str, "early_hr": float|None,
              "late_hr": float|None, "is_steady_aerobic": bool,
              "confidence": "high"|"medium"|"low"|"unavailable",
              "reasons": list[str]}

        见 docs/physiology_reference.md §指标 6。
        """
        # 前置检查
        steady = MetricsResolver._classify_steady_aerobic(
            records=records, duration_sec=duration_sec
        )
        if not steady["is_steady_aerobic"]:
            return {
                "drift_pct": None, "level": "unknown",
                "early_hr": None, "late_hr": None,
                "is_steady_aerobic": False,
                "confidence": "unavailable",
                "reasons": steady["reasons"],
            }

        if not records or duration_sec <= 0:
            return {
                "drift_pct": None, "level": "unknown",
                "early_hr": None, "late_hr": None,
                "is_steady_aerobic": False,
                "confidence": "unavailable",
                "reasons": ["empty records or zero duration"],
            }

        # 过滤有效 records
        valid_recs = [r for r in records if isinstance(r, dict)]
        n = len(valid_recs)
        if n < MetricsResolver._HR_DRIFT_MIN_RECORDS:
            return {
                "drift_pct": None, "level": "unknown",
                "early_hr": None, "late_hr": None,
                "is_steady_aerobic": False,
                "confidence": "unavailable",
                "reasons": [
                    f"records<{MetricsResolver._HR_DRIFT_MIN_RECORDS}"
                ],
            }

        # 按 timestamp 排序(防御性,FIT 顺序应已保证)
        sorted_recs = sorted(
            valid_recs,
            key=lambda r: MetricsResolver._num(
                MetricsResolver._record_value(r, "timestamp", "time")
            ) or 0,
        )

        # 前后半程分界
        half_idx = int(n * MetricsResolver._HR_DRIFT_SPLIT_RATIO)
        early_recs = sorted_recs[:half_idx]
        late_recs = sorted_recs[half_idx:]

        def _avg_hr(recs: list) -> float | None:
            hrs: list[float] = []
            for r in recs:
                hr = MetricsResolver._num(
                    MetricsResolver._record_value(r, "heart_rate", "hr")
                )
                if hr and hr > 30:  # 排除 0 / 异常低值
                    hrs.append(float(hr))
            if not hrs:
                return None
            return sum(hrs) / len(hrs)

        early_hr = _avg_hr(early_recs)
        late_hr = _avg_hr(late_recs)

        if early_hr is None or late_hr is None or early_hr <= 0:
            return {
                "drift_pct": None, "level": "unknown",
                "early_hr": early_hr, "late_hr": late_hr,
                "is_steady_aerobic": True,
                "confidence": "unavailable",
                "reasons": ["no valid HR data in early/late half"],
            }

        drift_pct = round((late_hr - early_hr) / early_hr * 100.0, 2)

        # 等级判定(Friel / Coggan 阈值)
        if drift_pct < 5.0:
            level = "excellent"
        elif drift_pct < 10.0:
            level = "good"
        elif drift_pct < 15.0:
            level = "warn"
        else:
            level = "bad"

        # confidence 校正(reference §7 4 级条件)
        # 当前 V7.10 已是真实算法,无需再标 "代理算法"
        confidence = "high"
        if duration_sec < 60 * 60:  # < 60min → MEDIUM
            confidence = "medium"
        confidence_reasons: list[str] = []
        pace_cv = steady.get("pace_cv")
        if pace_cv is not None and pace_cv >= MetricsResolver._HR_DRIFT_MAX_PACE_CV:
            confidence = "low" if pace_cv >= MetricsResolver._HR_DRIFT_MAX_PACE_CV * 2 else "medium"
            confidence_reasons.append(
                f"pace_cv={pace_cv:.1f}% >= {MetricsResolver._HR_DRIFT_MAX_PACE_CV}%"
            )

        return {
            "drift_pct": drift_pct,
            "level": level,
            "early_hr": round(early_hr, 1),
            "late_hr": round(late_hr, 1),
            "is_steady_aerobic": not confidence_reasons,
            "confidence": confidence,
            "reasons": confidence_reasons,
        }
def evaluate_efficiency(
    avg_hr: float | None,
    avg_pace_sec_per_km: float | None,
    sport_type: str,
    duration_sec: float,
    baseline_ratio: float | None,
    sample_size: int,
    avg_temp_c: float | None = None,
    max_alt_m: float | None = None,
    hr_source: str = "chest_strap",
) -> dict[str, Any]:
    """V7.9 公开 API:组合 baseline 比对 + confidence 评估(reference §7 4 级条件)。

    见 docs/physiology_reference.md §指标 5。
    """
    base = MetricsResolver._compute_efficiency_score(
        avg_hr=avg_hr,
        avg_pace_sec_per_km=avg_pace_sec_per_km,
        sport_type=sport_type,
        duration_sec=duration_sec,
    )

    if base["confidence"] == "unavailable":
        return {
            "score": None, "ratio": base["ratio"], "level": "unknown",
            "confidence": "unavailable", "delta_pct": None,
            "baseline_ratio": None, "sample_size": 0,
        }

    # 无 baseline 归一化
    if baseline_ratio is None or baseline_ratio <= 0:
        return {
            "score": None, "ratio": base["ratio"], "level": "unknown",
            "confidence": "low", "delta_pct": None,
            "baseline_ratio": None, "sample_size": sample_size,
        }

    delta_pct = (base["ratio"] - baseline_ratio) / baseline_ratio * 100
    # 25% 改善 → +25 分;25% 退化 → -25 分
    score_delta = (delta_pct / 25.0) * MetricsResolver._EFFICIENCY_SCORE_RANGE
    score = MetricsResolver._EFFICIENCY_SCORE_BASELINE + score_delta
    score = max(0.0, min(100.0, score))  # clamp 0-100

    if delta_pct > 5:
        level = "improving"
    elif delta_pct < -5:
        level = "declining"
    else:
        level = "stable"

    # confidence 校正(reference §7 4 级条件)
    confidence = "high"
    if hr_source == "optical":
        confidence = "medium"
    if duration_sec < 30 * 60:
        confidence = "medium"
    if avg_temp_c is not None and avg_temp_c > 28.0:
        confidence = "low"
    if max_alt_m is not None and max_alt_m > 2000.0:
        confidence = "low"

    return {
        "score": round(score, 1),
        "ratio": base["ratio"],
        "level": level,
        "confidence": confidence,
        "delta_pct": round(delta_pct, 2),
        "baseline_ratio": baseline_ratio,
        "sample_size": sample_size,
    }


# ══════════════════════════════════════════════════════════════════
# V9.4.0: Training Effect 派生层(契约 docs/training_effect_v1_contract §6.5/§6.6)
# 真理源:FIT session message 直读 training_effect_aerobic / anaerobic_training_effect
# Resolver 唯一做的事:读 FIT 数值 + 查表(title/label/summary)+ 字符串拼接 overall_summary
# 8 运动 × 2 维度 × 6 TE 范围 = 96 单元(从用户原 §二 逐字填入)
# ══════════════════════════════════════════════════════════════════

# 6 等级 ID 顺序(决定 max() 优先级)
_TE_LEVEL_ORDER = {
    "recovery": 0,
    "activation": 1,
    "maintenance": 2,
    "improvement": 3,
    "overload": 4,
    "extreme": 5,
}

# 6 等级 ID 列表(下标 0~5 对应 6 个 TE 范围)
_TE_LEVEL_IDS = ["recovery", "activation", "maintenance", "improvement", "overload", "extreme"]

# TE 分数 → 等级下标(0~5)映射
_TE_RANGE_BOUNDS = [0.0, 1.0, 2.0, 3.0, 4.0, 4.5, 5.0]

# V9.4.4:训练收益 6 等级中文 label 真理源(前端 _TE_LEVEL_LABELS_CN 真理源,后端唯一)
# 与 _TE_LEVEL_IDS 顺序严格一致
_TE_LEVEL_LABELS_CN: dict[str, str] = {
    "recovery":    "恢复",
    "activation":  "激活",
    "maintenance": "维持",
    "improvement": "提升",
    "overload":    "高负荷",
    "extreme":     "极限",
}

# V9.4.4:训练收益 6 等级颜色真理源(前端 _TE_LEVEL_COLORS 真理源,后端唯一)
# 与 _TE_LEVEL_IDS 顺序严格一致(Gray/Blue/Cyan/Green/Orange/Red,用户原 §三)
_TE_LEVEL_COLORS: dict[str, str] = {
    "recovery":    "#64748b",
    "activation":  "#3b82f6",
    "maintenance": "#06b6d4",
    "improvement": "#22c55e",
    "overload":    "#f97316",
    "extreme":     "#ef4444",
}

# 运动 × 维度 → (primary_title, secondary_title)(用户原 §四 逐字)
_TE_SPORT_TITLE = {
    "running":         ("有氧收益", "速度刺激"),
    "trail_running":   ("耐力收益", "高强度刺激"),
    "hiking":          ("耐力收益", "高强度刺激"),
    "cycling":         ("耐力输出", "冲刺刺激"),
    "indoor_cycling":  ("有氧输出", "功率刺激"),
    "swimming":        ("耐力收益", "速度刺激"),
    "strength":        ("肌肉刺激", "爆发负荷"),
    "hiit":            ("心肺刺激", "爆发刺激"),
}

# 运动 × 维度 × 6 TE 范围 = 96 单元(用户原 §二 逐字)
# 索引顺序:[recovery, activation, maintenance, improvement, overload, extreme]
_TE_SPORT_MATRIX = {
    # ─── 1. 跑步(Running) ───
    "running": {
        "primary": [
            ("恢复跑", "以恢复与轻松活动为主"),
            ("轻度耐力激活", "对心肺形成轻微刺激"),
            ("维持有氧耐力", "保持当前耐力水平"),
            ("提升有氧耐力", "有效增强基础耐力"),
            ("强化心肺能力", "形成较强有氧刺激"),
            ("极限耐力负荷", "接近极限耐力训练"),
        ],
        "secondary": [
            ("无明显速度刺激", "基本为纯有氧训练"),
            ("少量变速刺激", "包含轻度变速"),
            ("提升速度能力", "形成一定爆发刺激"),
            ("强化爆发能力", "高强度配速刺激明显"),
            ("高强度间歇刺激", "对无氧系统形成较强负荷"),
            ("极限速度训练", "接近极限冲刺负荷"),
        ],
    },
    # ─── 2. 越野跑(Trail Running) ───
    "trail_running": {
        "primary": [
            ("轻松山地恢复", "无明显山地负荷"),
            ("轻度耐力刺激", "对山地体能形成轻微刺激"),
            ("维持山地耐力", "保持当前山地能力"),
            ("提升爬升耐力", "有效增强爬升基础耐力"),
            ("强化长距离耐力", "形成较强山地有氧刺激"),
            ("极限山地耐力", "接近极限山地耐力训练"),
        ],
        "secondary": [
            ("无明显高强度刺激", "基本为纯耐力训练"),
            ("少量高强度配速", "包含轻度高强度配速"),
            ("提升爆发输出", "形成一定爆发刺激"),
            ("强化高强度能力", "高强度输出刺激明显"),
            ("高负荷间歇刺激", "对无氧系统形成较强负荷"),
            ("极限山地输出", "接近极限山地爆发"),
        ],
    },
    # ─── 3. 徒步(Hiking) ───
    "hiking": {
        "primary": [
            ("轻松活动", "无明显长距离负荷"),
            ("轻度长距离活动", "对长距离体能形成轻微刺激"),
            ("维持基础体能", "保持当前基础体能"),
            ("提升长距离耐力", "有效增强长距离基础耐力"),
            ("强化山地体能", "形成较强长距离有氧刺激"),
            ("极限长距离负荷", "接近极限长距离徒步"),
        ],
        "secondary": [
            ("无明显高强度刺激", "基本为平坦轻松徒步"),
            ("少量高强度活动", "包含轻度高强度活动"),
            ("中等强度刺激", "形成一定体能刺激"),
            ("强化高强度能力", "高强度刺激明显"),
            ("高负荷体能刺激", "对体能系统形成较强负荷"),
            ("极限高强度负荷", "接近极限体能挑战"),
        ],
    },
    # ─── 4. 公路骑行(Cycling) ───
    "cycling": {
        "primary": [
            ("恢复骑行", "以恢复与轻松骑行为主"),
            ("轻度输出激活", "对心肺形成轻微刺激"),
            ("维持持续输出", "保持当前持续输出能力"),
            ("提升持续功率", "有效增强持续输出基础"),
            ("强化耐力输出", "形成较强持续有氧刺激"),
            ("极限耐力骑行", "接近极限持续输出"),
        ],
        "secondary": [
            ("无明显冲刺刺激", "基本为匀速骑行"),
            ("少量变速刺激", "包含轻度变速"),
            ("提升冲刺能力", "形成一定爆发刺激"),
            ("强化爆发输出", "高强度冲刺刺激明显"),
            ("高强度间歇刺激", "对无氧系统形成较强负荷"),
            ("极限冲刺负荷", "接近极限冲刺训练"),
        ],
    },
    # ─── 5. 室内骑行(Indoor Cycling) ───
    "indoor_cycling": {
        "primary": [
            ("轻松恢复骑行", "以恢复与轻松踩踏为主"),
            ("轻度踩踏激活", "对心肺形成轻微刺激"),
            ("维持有氧输出", "保持当前有氧输出能力"),
            ("提升持续踩踏能力", "有效增强踩踏输出基础"),
            ("强化功率耐力", "形成较强有氧刺激"),
            ("极限功率训练", "接近极限持续功率"),
        ],
        "secondary": [
            ("无明显高强度刺激", "基本为匀速踩踏"),
            ("少量间歇刺激", "包含轻度间歇"),
            ("提升爆发输出", "形成一定爆发刺激"),
            ("强化高强度能力", "高强度刺激明显"),
            ("高负荷功率间歇", "对无氧系统形成较强负荷"),
            ("极限功率训练", "接近极限高强度踩踏"),
        ],
    },
    # ─── 6. 游泳(Swimming) ───
    "swimming": {
        "primary": [
            ("轻松恢复游", "以恢复与轻松游动为主"),
            ("轻度耐力激活", "对心肺形成轻微刺激"),
            ("维持持续游动能力", "保持当前游动耐力"),
            ("提升游泳耐力", "有效增强基础游泳耐力"),
            ("强化心肺能力", "形成较强游泳有氧刺激"),
            ("极限耐力训练", "接近极限游泳耐力"),
        ],
        "secondary": [
            ("无明显速度刺激", "基本为匀速游动"),
            ("少量冲刺训练", "包含轻度冲刺"),
            ("提升爆发能力", "形成一定划水爆发刺激"),
            ("强化高强度划水", "高强度划水刺激明显"),
            ("高强度速度训练", "对无氧系统形成较强负荷"),
            ("极限速度负荷", "接近极限冲刺游动"),
        ],
    },
    # ─── 7. 力量训练(Strength)— 用户原 §5.7 标注「彻底换语言」 ───
    "strength": {
        "primary": [
            ("轻度肌肉激活", "对肌肉形成轻微刺激"),
            ("基础力量刺激", "形成一定肌肉负荷"),
            ("维持力量状态", "保持当前力量水平"),
            ("提升肌肉负荷", "有效增强基础力量"),
            ("强化力量刺激", "形成较强肌肉刺激"),
            ("极限力量负荷", "接近极限力量训练"),
        ],
        "secondary": [
            ("无明显爆发训练", "基本为稳定力量训练"),
            ("少量爆发刺激", "包含轻度爆发动作"),
            ("提升爆发能力", "形成一定爆发刺激"),
            ("强化高强度输出", "高强度爆发刺激明显"),
            ("高负荷力量刺激", "对爆发系统形成较强负荷"),
            ("极限爆发训练", "接近极限爆发训练"),
        ],
    },
    # ─── 8. HIIT / 功能训练 ───
    "hiit": {
        "primary": [
            ("轻度活动", "无明显心肺负荷"),
            ("轻度心肺刺激", "对心肺形成轻微刺激"),
            ("维持有氧能力", "保持当前有氧水平"),
            ("提升心肺能力", "有效增强基础心肺"),
            ("强化高强度耐力", "形成较强心肺刺激"),
            ("极限心肺负荷", "接近极限心肺训练"),
        ],
        "secondary": [
            ("无明显爆发刺激", "基本为稳定有氧"),
            ("少量高强度动作", "包含轻度高强度动作"),
            ("提升爆发能力", "形成一定爆发刺激"),
            ("强化高强度输出", "高强度爆发刺激明显"),
            ("高负荷间歇刺激", "对无氧系统形成较强负荷"),
            ("极限爆发负荷", "接近极限间歇爆发"),
        ],
    },
}


def _te_to_index(score):
    """0.0~5.0 TE 分数 → 0~5 等级下标(用户原 §三 6 范围)"""
    if score is None:
        return 0
    if score < _TE_RANGE_BOUNDS[1]:
        return 0  # 0.0~0.9 recovery
    if score < _TE_RANGE_BOUNDS[2]:
        return 1  # 1.0~1.9 activation
    if score < _TE_RANGE_BOUNDS[3]:
        return 2  # 2.0~2.9 maintenance
    if score < _TE_RANGE_BOUNDS[4]:
        return 3  # 3.0~3.9 improvement
    if score < _TE_RANGE_BOUNDS[5]:
        return 4  # 4.0~4.5 overload
    return 5      # 4.5~5.0 extreme


def build_training_effect(record, sport_type):
    """V9.4.4:消费 FIT Firstbeat TE 字段 + 查表,返回契约 §2.1 JSON 结构。

    真理源:
      1. FIT session.total_training_effect + total_anaerobic_training_effect
         (Garmin Firstbeat 私有算法,fitparse 已应用 scale 0.1 → 0.0~5.0) — `data_source=fit_sdk`
      2. 双字段都 None → 返回 None(走前端占位,不重算)

    设计依据:
      - 专家说明:不要从 heart_rate/pace 自己重算 Garmin TE(Firstbeat 私有,涉及长期训练状态)
      - 脉图正确定位:消费 Garmin TE + 做语义解释
      - 任一字段为 None 仍接受(设备部分输出场景),缺失维度走 0.0 fallback(标 fit_sdk)
      - 双字段都 None 才返回 None

    依据:docs/training_effect_v1_contract.md §6.5/§6.6

    Args:
        record: activity record dict
        sport_type: 运动类型(原始 sport_type)

    Returns:
        dict | None: 契约 §2.1 JSON 结构(无任何可用数据时返回 None)
    """
    if not isinstance(record, dict):
        return None
    aerobic = record.get("aerobic_training_effect")
    anaerobic = record.get("anaerobic_training_effect")
    has_fit_te = aerobic is not None or anaerobic is not None

    if not has_fit_te:
        # V9.4.4:双字段都 None → 走前端占位(不再做启发式估算,避免与 Garmin 私有算法冲突)
        return None

    data_source = "fit_sdk"

    # 规范化 sport_type
    sport = str(sport_type or "running").strip().lower()

    primary_score = float(aerobic) if aerobic is not None else 0.0
    secondary_score = float(anaerobic) if anaerobic is not None else 0.0

    primary_title, secondary_title = _TE_SPORT_TITLE.get(sport, _TE_SPORT_TITLE["running"])

    matrix = _TE_SPORT_MATRIX.get(sport, _TE_SPORT_MATRIX["running"])
    primary_idx = _te_to_index(primary_score)
    secondary_idx = _te_to_index(secondary_score)
    primary_label, primary_summary = matrix["primary"][primary_idx]
    secondary_label, secondary_summary = matrix["secondary"][secondary_idx]

    primary_level = _TE_LEVEL_IDS[primary_idx]
    secondary_level = _TE_LEVEL_IDS[secondary_idx]
    if _TE_LEVEL_ORDER[primary_level] >= _TE_LEVEL_ORDER[secondary_level]:
        global_level = primary_level
    else:
        global_level = secondary_level

    # overall_summary 拼接(V9.4.4:不再有 estimated 路径,只来自 FIT Firstbeat)
    overall_summary = "本次训练{prim},并包含{seco}。".format(
        prim=primary_summary, seco=secondary_summary
    )

    return {
        "sport_type": sport,
        "primary": {
            "title": primary_title,
            "score": round(primary_score, 1),
            "level": primary_level,
            "label": primary_label,
            "summary": primary_summary,
        },
        "secondary": {
            "title": secondary_title,
            "score": round(secondary_score, 1),
            "level": secondary_level,
            "label": secondary_label,
            "summary": secondary_summary,
        },
        "global_level": global_level,
        "overall_summary": overall_summary,
        "data_source": data_source,  # V9.4.4:fit_sdk 透明标记(FIT Firstbeat 直读)
        # V9.4.4:6 等级 label/color 透传(真理源自 _TE_LEVEL_LABELS_CN / _TE_LEVEL_COLORS)
        # 前端 _TE_LEVEL_LABELS_CN / _TE_LEVEL_COLORS 保留作 fallback(防回退老 API)
        "level_labels_cn": _TE_LEVEL_LABELS_CN,
        "level_colors": _TE_LEVEL_COLORS,
    }


# ══════════════════════════════════════════════════════════════════
# V_ENV.1.1:Environment Challenge 派生工具(Phase 1:climb / altitude / heat)
# §调研报告 §3.1/§3.2/§3.3;Phase 1 不实现 GPS curvature 与 Vertical Intensity
# 契约依据:fit-arch-contrac §2.1 字段可追溯 + §六 审计字段隔离
# 严禁读 self.xxx / 写 DB / 写 AI snapshot
# ══════════════════════════════════════════════════════════════════


def calculate_climb_density(total_ascent_m, distance_km):
    """V_ENV.1.1:爬升密度 = 累计爬升(m) / 距离(km)。

    Phase 1 仅做派生,不做时间归一化(Vertical Intensity 推迟至 Phase 3)。

    契约:
      - 任一输入为 None / distance_km<=0 → 返回 0.0(降级,不抛异常)
      - total_ascent_m < 0 → 视为 0
      - 返回值单位: m/km(UI 侧只用于映射 level,自身不直接展示)
    """
    if total_ascent_m is None or distance_km is None:
        return 0.0
    if distance_km <= 0.0:
        return 0.0
    ascent = max(0.0, float(total_ascent_m))
    return ascent / float(distance_km)


def classify_altitude_stress(max_altitude_m):
    """V_ENV.1.1:海拔压力 5 档分级(主指标 max_altitude,严禁替换为 avg)。

    阈值与语义严格按调研报告 §3.2 表:
      < 1500           → 0  无明显影响
      [1500, 2500)     → 1  轻度压力
      [2500, 3500)     → 2  中等高海拔
      [3500, 4500)     → 3  高海拔压力
      >= 4500          → 4  极限海拔环境

    降级:
      - max_altitude_m 为 None 或 < 0 → 返回 0
    """
    if max_altitude_m is None or max_altitude_m < 0:
        return 0
    alt = float(max_altitude_m)
    if alt < 1500.0:
        return 0
    if alt < 2500.0:
        return 1
    if alt < 3500.0:
        return 2
    if alt < 4500.0:
        return 3
    return 4


def classify_heat_stress(temp_c, humidity):
    """V_ENV.1.1:热环境压力 4 档分级(Temperature × Humidity 粗分)。

    公式:
      product = temp_c * humidity    # humidity 范围 0~1

    阈值与语义严格按调研报告 §3.3 表:
      < 500           → 0  环境舒适
      [500, 1200)     → 1  略有热感
      [1200, 2100)    → 2  炎热环境
      >= 2100         → 3  高温挑战

    降级(单维度缺失/双维度缺失):
      - temp_c is None → 返回 0(温度缺失无法判定)
      - humidity is None:
          < 25°C  → 0
          [25, 30) → 1
          [30, 35) → 2
          >= 35   → 3
      - 两者都 None → 返回 0

    契约:
      - 拒绝伪精确:不做 WBGT / Heat Index / AI 热风险
      - 此为环境摘要,不替代生理指标
    """
    if temp_c is None and humidity is None:
        return 0
    if temp_c is None:
        return 0
    if humidity is None:
        # 单维度降级:仅按温度粗分
        t = float(temp_c)
        if t < 25.0:
            return 0
        if t < 30.0:
            return 1
        if t < 35.0:
            return 2
        return 3
    product = float(temp_c) * float(humidity)
    if product < 500.0:
        return 0
    if product < 1200.0:
        return 1
    if product < 2100.0:
        return 2
    return 3


# ══════════════════════════════════════════════════════════════════
# V_ENV.1.2:Environment Challenge 语义路由(6 运动 × 4 模块 × 4/5 级)
# §调研报告 §4.2~§4.7 1:1 复刻;skiing/mountaineering 第 3 模块走低温替换
# 契约依据:fit-arch-contrac §2.1 字段可追溯 + §五 AI 边界(纯展示文案,不入 AI Snapshot)
# 严禁读 self.xxx / 写 DB / 拼前端 payload
# ══════════════════════════════════════════════════════════════════


# ─── 1. 跑步(Running)— §4.2 ───
RUNNING_SEMANTICS = {
    "vertical": [
        {"label": "平路路线",         "explanation": "几乎无爬升,海拔变化小"},
        {"label": "略有起伏",         "explanation": "海拔起伏小,对配速影响有限"},
        {"label": "持续爬升路线",     "explanation": "持续爬升,需稳定配速策略"},
        {"label": "高强度爬升跑",     "explanation": "爬升密度大,需重点关注心率与配速管理"},
        {"label": "极限爬升挑战",     "explanation": "极端爬升密度,纯靠爬升能力,建议分段休息"},
    ],
    "altitude": [
        {"label": "低海拔环境",       "explanation": "海拔 1500m 以下,无明显高海拔影响"},
        {"label": "中低海拔跑步",     "explanation": "海拔 1500~2500m,部分敏感人群可能出现轻微反应"},
        {"label": "中高海拔环境",     "explanation": "海拔 2500~3500m,需关注呼吸节奏与水分补给"},
        {"label": "高海拔耐力环境",   "explanation": "海拔 3500~4500m,需提前适应,降低运动强度"},
        {"label": "极限高海拔挑战",   "explanation": "海拔 4500m 以上,极高生理压力,需充分评估"},
    ],
    "heat": [
        {"label": "环境舒适",         "explanation": "温湿度适宜,体感无负担"},
        {"label": "略有热感",         "explanation": "温湿度偏高,需注意补水"},
        {"label": "炎热跑步环境",     "explanation": "高温高湿,散热压力大,后程心率易偏高"},
        {"label": "高温耐力挑战",     "explanation": "极端高温,需缩短运动时间,优先安全"},
    ],
    "terrain": [
        {"label": "路线平稳",         "explanation": "路面平整,无技术难点"},
        {"label": "略复杂路线",       "explanation": "偶有起伏或弯道,需注意节奏"},
        {"label": "技术型路线",       "explanation": "出现技术路段,需关注落脚点"},
        {"label": "高技术跑步路线",   "explanation": "频繁技术路段,需较强应变能力"},
        {"label": "极限技术地形",     "explanation": "持续高难度技术路段,需高级别越野能力"},
    ],
}

# ─── 2. 越野跑(Trail Running)— §4.3 ───
TRAIL_RUNNING_SEMANTICS = {
    "vertical": [
        {"label": "轻度山地路线",     "explanation": "山地起伏小,跑感流畅"},
        {"label": "起伏山地",         "explanation": "山地有明显起伏,需调节配速"},
        {"label": "持续爬升山路",     "explanation": "持续爬升,需稳定节奏与补给"},
        {"label": "高强度山地爬升",   "explanation": "山地爬升密度大,需较强爬升能力"},
        {"label": "极限山地挑战",     "explanation": "极端山地爬升,纯靠登山能力与意志"},
    ],
    "altitude": [
        {"label": "低海拔山地",       "explanation": "1500m 以下山地,无明显高海拔影响"},
        {"label": "中低海拔路线",     "explanation": "1500~2500m 山地,呼吸略急促"},
        {"label": "中高海拔越野",     "explanation": "2500~3500m 山地,需关注节奏"},
        {"label": "高海拔山地环境",   "explanation": "3500~4500m 山地,需提前适应"},
        {"label": "极限高海拔越野",   "explanation": "4500m 以上山地,极高生理压力"},
    ],
    "heat": [
        {"label": "山地气候舒适",     "explanation": "山地温湿度适宜,体感舒适"},
        {"label": "略有热感",         "explanation": "山地温湿度略高,需注意补水"},
        {"label": "炎热山地环境",     "explanation": "山地高温,需关注散热"},
        {"label": "高温山地挑战",     "explanation": "山地极端高温,需缩短时间"},
    ],
    "terrain": [
        {"label": "路况稳定",         "explanation": "山路路况稳定,无技术难点"},
        {"label": "轻度技术路线",     "explanation": "偶有泥泞或岩石,需注意落脚"},
        {"label": "中等技术山路",     "explanation": "出现明显技术路段,需较强应变"},
        {"label": "高技术越野路线",   "explanation": "频繁技术路段,需高级别越野能力"},
        {"label": "极限技术地形",     "explanation": "持续高难度技术路段,需专业级越野经验"},
    ],
}

# ─── 3. 徒步(Hiking)— §4.4 ───
HIKING_SEMANTICS = {
    "vertical": [
        {"label": "轻松步道",         "explanation": "步道平缓,无明显爬升"},
        {"label": "略有爬升",         "explanation": "步道有爬升,需调节呼吸"},
        {"label": "持续登山路线",     "explanation": "持续登山,需稳定节奏"},
        {"label": "高强度登山挑战",   "explanation": "登山爬升密度大,需较强体能"},
        {"label": "极限长爬升路线",   "explanation": "极端爬升密度,需充分准备"},
    ],
    "altitude": [
        {"label": "低海拔徒步",       "explanation": "1500m 以下徒步,无明显高反"},
        {"label": "中低海拔环境",     "explanation": "1500~2500m,部分人有轻微反应"},
        {"label": "中高海拔徒步",     "explanation": "2500~3500m,需关注节奏"},
        {"label": "高海拔登山环境",   "explanation": "3500~4500m,需提前适应"},
        {"label": "极限高海拔环境",   "explanation": "4500m 以上,极高生理压力"},
    ],
    "heat": [
        {"label": "徒步环境舒适",     "explanation": "温湿度适宜,体感舒适"},
        {"label": "略有热感",         "explanation": "温湿度略高,需注意补水"},
        {"label": "炎热徒步环境",     "explanation": "高温高湿,需关注散热"},
        {"label": "高温登山挑战",     "explanation": "极端高温,需缩短徒步时间"},
    ],
    "terrain": [
        {"label": "步道路况稳定",     "explanation": "步道平整,无技术难点"},
        {"label": "略复杂山路",       "explanation": "偶有起伏或陡坡,需注意"},
        {"label": "技术型山地路线",   "explanation": "出现技术路段,需关注落脚"},
        {"label": "高技术登山路线",   "explanation": "频繁技术路段,需较强能力"},
        {"label": "极限技术山地",     "explanation": "持续高难度技术路段,需专业经验"},
    ],
}

# ─── 4. 公路骑行(Road Cycling)— §4.5 ───
CYCLING_SEMANTICS = {
    "vertical": [
        {"label": "平路骑行",         "explanation": "路线平直,无明显爬升"},
        {"label": "略有爬升",         "explanation": "偶有缓坡,影响有限"},
        {"label": "长爬坡路线",       "explanation": "持续爬坡,需调节档位与节奏"},
        {"label": "高强度爬坡骑行",   "explanation": "爬坡密度大,需较强爬坡能力"},
        {"label": "极限山地骑行",     "explanation": "极端爬坡,纯靠爬坡能力与体能"},
    ],
    "altitude": [
        {"label": "低海拔骑行",       "explanation": "1500m 以下,无明显高反"},
        {"label": "中低海拔路线",     "explanation": "1500~2500m,呼吸略急促"},
        {"label": "中高海拔骑行",     "explanation": "2500~3500m,需关注节奏"},
        {"label": "高海拔骑行环境",   "explanation": "3500~4500m,需提前适应"},
        {"label": "极限高海拔骑行",   "explanation": "4500m 以上,极高生理压力"},
    ],
    "heat": [
        {"label": "骑行环境舒适",     "explanation": "骑行时风冷效应,体感舒适"},
        {"label": "略有热感",         "explanation": "温湿度略高,需注意补水"},
        {"label": "炎热骑行环境",     "explanation": "高温,需关注核心体温"},
        {"label": "高温耐力骑行",     "explanation": "极端高温,需缩短骑行时间"},
    ],
    "terrain": [
        {"label": "路况稳定",         "explanation": "路面平整,无技术难点"},
        {"label": "略复杂路线",       "explanation": "偶有弯道或破损,需注意"},
        {"label": "多弯山路",         "explanation": "弯道频繁,需控速"},
        {"label": "高技术下坡路线",   "explanation": "下坡技术要求高,需强控车能力"},
        {"label": "极限技术骑行路线", "explanation": "持续高难度技术路段,需专业经验"},
    ],
}

# ─── 5. 山地骑行(MTB)— §4.6 ───
MOUNTAIN_BIKING_SEMANTICS = {
    "vertical": [
        {"label": "轻度越野路线",     "explanation": "起伏小,越野流畅"},
        {"label": "起伏土路",         "explanation": "有明显起伏,需调节节奏"},
        {"label": "持续山地爬升",     "explanation": "持续爬升,需稳定踏频"},
        {"label": "高强度越野爬升",   "explanation": "爬升密度大,需较强爬坡能力"},
        {"label": "极限山地骑行挑战", "explanation": "极端爬升,纯靠爬坡能力"},
    ],
    "altitude": [
        {"label": "低海拔越野",       "explanation": "1500m 以下,无明显高反"},
        {"label": "中低海拔路线",     "explanation": "1500~2500m,呼吸略急促"},
        {"label": "中高海拔山地",     "explanation": "2500~3500m,需关注节奏"},
        {"label": "高海拔越野环境",   "explanation": "3500~4500m,需提前适应"},
        {"label": "极限高海拔越野",   "explanation": "4500m 以上,极高生理压力"},
    ],
    "heat": [
        {"label": "越野环境舒适",     "explanation": "温湿度适宜,体感舒适"},
        {"label": "略有热感",         "explanation": "温湿度略高,需注意补水"},
        {"label": "炎热越野环境",     "explanation": "高温,需关注散热"},
        {"label": "高温山地骑行",     "explanation": "极端高温,需缩短骑行时间"},
    ],
    "terrain": [
        {"label": "土路稳定",         "explanation": "土路平整,无技术难点"},
        {"label": "轻度技术路线",     "explanation": "偶有泥泞或岩石,需注意"},
        {"label": "技术型林道",       "explanation": "出现明显技术路段,需较强控车能力"},
        {"label": "高技术越野路线",   "explanation": "频繁技术路段,需高级别越野能力"},
        {"label": "极限技术地形",     "explanation": "持续高难度技术路段,需专业经验"},
    ],
}

# ─── 6. 低温环境(滑雪/登山 第 3 模块专用替换)— §4.7.3 ───
# 5 档,下标 0~4;对应温度阈值(代码不消费,供前端 tooltip):
#   0:0°C 以上 / 1:0~-10 / 2:-10~-20 / 3:-20~-30 / 4:<-30
COLD_SEMANTICS = [
    {"label": "温度舒适",   "explanation": "0°C 以上,无明显冷应激"},
    {"label": "略低温",     "explanation": "0~-10°C,需注意手/脚保暖"},
    {"label": "低温环境",   "explanation": "-10~-20°C,需全套防寒装备"},
    {"label": "严寒环境",   "explanation": "-20~-30°C,暴露皮肤有冻伤风险"},
    {"label": "极寒挑战",   "explanation": "-30°C 以下,极高冻伤风险,需专业防寒"},
]


# ─── 7. 路由表(对外查询入口)───
# 项目实际枚举(L1547/L1551/metrics_resolver.py 全文扫描)已把 road_cycling 合并到 cycling;
# 本表兼容两种写法以便未来拆分。
# skiing/mountaineering 不在调研报告 §4.7 给 1/2/4 模块专属语义,故借越野跑/徒步兜底;
# 第 3 模块单独走 COLD_SEMANTICS。
_ENV_CHALLENGE_SPORT_MAP = {
    "running":         RUNNING_SEMANTICS,
    "trail_running":   TRAIL_RUNNING_SEMANTICS,
    "hiking":          HIKING_SEMANTICS,
    "cycling":         CYCLING_SEMANTICS,
    "road_cycling":    CYCLING_SEMANTICS,
    "mountain_biking": MOUNTAIN_BIKING_SEMANTICS,
    "skiing":          TRAIL_RUNNING_SEMANTICS,
    "mountaineering":  HIKING_SEMANTICS,
}

_COLD_SPORT_SET = {"skiing", "mountaineering"}
_DEFAULT_SEMANTICS = RUNNING_SEMANTICS


def _clamp_level(level, max_level):
    """V_ENV.1.2:level 边界归一化。

    契约:
      - None / 非数值 / 负数 / 越界 → 0(降级,不抛异常)
      - 正常返回 0..max_level 整数
    """
    if level is None:
        return 0
    try:
        v = int(level)
    except (TypeError, ValueError):
        return 0
    if v < 0:
        return 0
    if v > max_level:
        return 0
    return v


def get_environment_challenge_semantic(sport_type, module, level):
    """V_ENV.1.2 + 2.2:环境挑战语义查询,返回 {label, explanation} 字典。

    契约:
      - sport_type: 字符串,未匹配走 RUNNING_SEMANTICS
      - module ∈ {"vertical","altitude","heat","terrain"},未知返回 {"label": "--", "explanation": "--"}
      - level 越界/None 走最低档
      - skiing/mountaineering 的 "heat" 模块自动切换为低温 5 档语义
      - 返回 dict 含 label + explanation 两字段,供前端成对消费
      - 严禁进入 AI Snapshot / DB(§五 5.3 / §八)
    """
    sport_key = (sport_type or "").strip().lower() if sport_type else ""
    table = _ENV_CHALLENGE_SPORT_MAP.get(sport_key, _DEFAULT_SEMANTICS)

    if module not in table:
        return {"label": "--", "explanation": "--"}

    # 滑雪/登山 → 第 3 模块走低温 5 档替换
    if module == "heat" and sport_key in _COLD_SPORT_SET:
        idx = _clamp_level(level, max_level=4)
        return COLD_SEMANTICS[idx]

    # 普通运动 → 查表(heat 4 档 / 其余 5 档)
    bucket = table[module]
    max_level = len(bucket) - 1
    idx = _clamp_level(level, max_level=max_level)
    return bucket[idx]


# ══════════════════════════════════════════════════════════════════
# V_ENV.1.3:Environment Challenge 派生块构建器
# §调研报告 §3 数据层 + §4 语义;被 MetricsResolver.resolve() 调用
# 契约依据:fit-arch-contrac §2.1 字段可追溯 + §五 AI 边界(不进 AI Snapshot)
# 严禁读 self.xxx / 写 DB / 拼前端 payload
# ══════════════════════════════════════════════════════════════════


def _classify_climb_density_level(density):
    """V_ENV.1.3:climb_density → 5 档 level(§3.1 表)。

    阈值(单位 m/km):
      < 10           → 0
      [10, 30)       → 1
      [30, 60)       → 2
      [60, 100)      → 3
      >= 100         → 4
    """
    if density is None or density < 0:
        return 0
    d = float(density)
    if d < 10.0:
        return 0
    if d < 30.0:
        return 1
    if d < 60.0:
        return 2
    if d < 100.0:
        return 3
    return 4


def _classify_cold_level(temp_c):
    """V_ENV.1.3:低温 5 档(滑雪/登山专用,§4.7.3 表)。

    阈值(单位 °C):
      > 0          → 0  温度舒适
      [-10, 0)     → 1  略低温
      [-20, -10)   → 2  低温环境
      [-30, -20)   → 3  严寒环境
      <= -30       → 4  极寒挑战

    降级:
      - temp_c 为 None → 返回 0(温度缺失走最高档"温度舒适")
    """
    if temp_c is None:
        return 0
    t = float(temp_c)
    if t >= 0.0:
        return 0
    if t >= -10.0:
        return 1
    if t >= -20.0:
        return 2
    if t >= -30.0:
        return 3
    return 4


def _resolve_humidity_0to1(raw, meta):
    """V_ENV.1.3:从 raw/meta 双入口取 humidity,防御性归一化到 0~1。

    入口优先级:
      1. raw.get("weather").get("humidity")(主路径:parse_track_at_path / sync_local_fit_files 注入)
      2. meta.get("weather").get("humidity")(兼容路径)
      3. meta.get("humidity")(裸字段)

    防御性归一化:
      - 0~1 → 直接返回(用户传入的归一化值)
      - 1~100 → 除以 100(Open-Meteo / Garmin weather_json 百分数)
      - 100 以外异常值 → 视为 None

    Returns:
      float in [0.0, 1.0] or None
    """
    candidates = []
    # 1) raw 顶层 weather
    raw_w = raw.get("weather") if isinstance(raw, dict) else None
    if isinstance(raw_w, dict) and raw_w.get("humidity") is not None:
        candidates.append(raw_w.get("humidity"))
    # 2) meta.weather
    meta_w = meta.get("weather") if isinstance(meta, dict) else None
    if isinstance(meta_w, dict) and meta_w.get("humidity") is not None:
        candidates.append(meta_w.get("humidity"))
    # 3) meta.humidity(裸)
    if isinstance(meta, dict) and meta.get("humidity") is not None:
        candidates.append(meta.get("humidity"))

    if not candidates:
        return None

    h_raw = candidates[0]
    try:
        h = float(h_raw)
    except (TypeError, ValueError):
        return None

    if h < 0:
        return None
    if h <= 1.0:
        return h
    if h <= 100.0:
        return h / 100.0
    return None  # > 100 视为异常


def _build_environment_challenge_block(sm, sport_type, avg_temp, raw, meta):
    """V_ENV.1.3:构建 environment_challenge 4 子块派生(Phase 1 MVP)。

    契约:
      - 输入全部只读(sm / sport_type / avg_temp / raw / meta)
      - 输出结构稳定:climb/altitude/heat/technical_terrain + sport_type + phase + data_source
      - 不进 AI snapshot,不写 DB,不读 §六 审计字段
      - 任何字段缺失时按"最低档"降级,metric_value 标 None
    """
    # ── 1. 提取标量(全部防御性) ──
    total_ascent_m = float(sm.get("total_ascent", 0) or 0) if isinstance(sm, dict) else 0.0
    distance_km = float(sm.get("distance_km", 0) or 0) if isinstance(sm, dict) else 0.0
    max_alt_m = 0.0
    if isinstance(sm, dict):
        max_alt_m = float(
            sm.get("max_altitude_m", 0) or sm.get("max_alt_m", 0) or 0
        )

    # ── 2. climb 子块 ──
    climb_density = calculate_climb_density(total_ascent_m, distance_km)
    climb_level = _classify_climb_density_level(climb_density)
    climb_label = get_environment_challenge_semantic(sport_type, "vertical", climb_level)

    # ── 3. altitude 子块 ──
    altitude_level = classify_altitude_stress(max_alt_m)
    altitude_label = get_environment_challenge_semantic(sport_type, "altitude", altitude_level)

    # ── 4. heat 子块 ──
    humidity_0to1 = _resolve_humidity_0to1(raw or {}, meta or {})
    sport_key = (sport_type or "").strip().lower() if sport_type else ""
    if sport_key in _COLD_SPORT_SET:
        # 滑雪/登山:低温 5 档只看温度(§4.7.3);与 product 计算解耦
        heat_level = _classify_cold_level(avg_temp)
        heat_metric_value = round(float(avg_temp), 1) if avg_temp is not None else None
    else:
        heat_level = classify_heat_stress(avg_temp, humidity_0to1)
        # metric_value 还原 product(供前端展示/调试;缺失时 None)
        heat_metric_value = None
        if avg_temp is not None and humidity_0to1 is not None:
            try:
                heat_metric_value = round(float(avg_temp) * float(humidity_0to1), 1)
            except (TypeError, ValueError):
                heat_metric_value = None
    heat_label = get_environment_challenge_semantic(sport_type, "heat", heat_level)

    # ── 5. technical_terrain(Phase 1 占位)───
    return {
        "sport_type": sport_type,
        "climb": {
            "metric_name": "climb_density",
            "metric_value": round(climb_density, 2),
            "level": climb_level,
            "label": climb_label,
        },
        "altitude": {
            "metric_name": "max_altitude",
            "metric_value": round(max_alt_m, 1),
            "level": altitude_level,
            "label": altitude_label,
        },
        "heat": {
            "metric_name": "temp_humidity_product",
            "metric_value": heat_metric_value,
            "level": heat_level,
            "label": heat_label,
        },
        "technical_terrain": {
            "metric_name": "gps_curvature",
            "metric_value": None,
            "level": 0,
            "label": "--",
            "available": False,
        },
        "phase": 1,
        "data_source": "fit_sdk",
    }


# ══════════════════════════════════════════════════════════════════
# V4.0 治理: SemanticSportsEngine 业务类下沉
# §V4.0 防腐层契约:本类从 main.py 整体迁移,纯计算,无 IO
# 严禁在 main.py 中重新定义同名类,应使用 from metrics_resolver import SemanticSportsEngine
# ══════════════════════════════════════════════════════════════════


class SemanticSportsEngine:
    """运动类型感知的展示指标引擎

    V4.0 治理:从 main.py 整体下沉至 metrics_resolver.py
    提供 build_display_metrics / get_layout / format_duration / format_pace 等纯计算方法
    """

    METRICS = {
        "distance": {"label": "距离", "unit": "km"},
        "duration": {"label": "时长", "unit": ""},
        "avg_pace": {"label": "平均配速", "unit": "/km"},
        "avg_speed": {"label": "平均速度", "unit": "km/h"},
        "avg_hr": {"label": "平均心率", "unit": "bpm"},
        "max_hr": {"label": "最大心率", "unit": "bpm"},
        "elevation": {"label": "总爬升", "unit": "m"},
        "calories": {"label": "热量", "unit": "Kcal"}
    }

    SPORT_PROFILES = {
        "running": {
            "summary_keys": ["distance", "avg_pace", "duration", "avg_hr"],
            "cards": [{"type": "summary_grid"}, {"type": "pace_hr_chart"}, {"type": "elevation_chart"}]
        },
        "trail_running": {
            "summary_keys": ["distance", "elevation", "duration", "avg_pace"],
            "cards": [{"type": "summary_grid"}, {"type": "elevation_chart"}, {"type": "pace_hr_chart"}]
        },
        "cycling": {
            "summary_keys": ["distance", "avg_speed", "duration", "avg_hr"],
            "cards": [{"type": "summary_grid"}, {"type": "speed_hr_power_chart"}, {"type": "elevation_chart"}]
        },
        "swimming": {
            "summary_keys": ["distance", "avg_pace", "duration", "avg_hr"],
            "cards": [{"type": "summary_grid"}, {"type": "pace_hr_chart"}]
        },
        "strength": {
            "summary_keys": ["duration", "calories", "avg_hr", "max_hr"],
            "cards": [{"type": "summary_grid"}, {"type": "hr_zones_chart"}]
        },
        "hiking": {
            "summary_keys": ["distance", "duration", "elevation", "avg_hr"],
            "cards": [{"type": "summary_grid"}, {"type": "elevation_chart"}]
        }
    }

    @staticmethod
    def format_duration(seconds):
        if not seconds or seconds < 0:
            return "--"
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    @staticmethod
    def format_pace(pace_sec):
        if not pace_sec or pace_sec <= 0:
            return "--"
        return f"{pace_sec // 60}'{pace_sec % 60:02d}\""

    @classmethod
    def build_display_metrics(cls, sport_type, raw_data):
        profile = cls.SPORT_PROFILES.get(sport_type, cls.SPORT_PROFILES["running"])
        display_list = []
        for key in profile["summary_keys"]:
            meta = cls.METRICS.get(key, {"label": key, "unit": ""})
            val_str = "--"
            if key == "distance":
                val_str = f"{raw_data.get('distance_km', 0):.2f}"
            elif key == "duration":
                val_str = cls.format_duration(raw_data.get('duration_sec', 0))
            elif key == "avg_pace":
                val_str = cls.format_pace(raw_data.get('avg_pace_sec', 0))
            elif key == "avg_speed":
                dist = raw_data.get('distance_km', 0)
                sec = raw_data.get('duration_sec', 0)
                val_str = f"{(dist / sec * 3600):.1f}" if sec > 0 else "--"
            elif key in ("avg_hr", "max_hr", "calories", "elevation"):
                val = raw_data.get(key)
                val_str = str(val) if val else "--"
            display_list.append({
                "key": key,
                "label": meta["label"],
                "value": val_str,
                "unit": meta["unit"]
            })
        return display_list

    @classmethod
    def get_layout(cls, sport_type: str) -> dict:
        return {"cards": cls.SPORT_PROFILES.get(sport_type, cls.SPORT_PROFILES["running"])["cards"]}
