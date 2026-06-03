"""
大模型调用：读取本地配置，使用 requests 访问 OpenAI 兼容接口；
将轨迹 DataFrame（高密度点表）拼入 System Prompt。
"""

from __future__ import annotations

import io
import json
import math
import re
import secrets
import sys
import time
from pathlib import Path
from typing import Any

import requests

DEFAULT_URL = "http://localhost:3000/v1/chat/completions"
DEFAULT_MODEL = "openclaw"
DEFAULT_PROVIDER = "local_mcp"
DEFAULT_AGENT_ID = ""


def _config_file() -> Path:
    """配置文件路径。
    打包后（sys.frozen）始终存放在用户主目录的隐藏文件夹中，
    确保分享 .app 程序时不会携带开发者的 API Key。
    """
    if getattr(sys, "frozen", False):
        d = Path.home() / ".fitvault"
    else:
        d = Path(__file__).resolve().parent
    d.mkdir(parents=True, exist_ok=True)
    return d / "llm_config.json"


def load_llm_config() -> dict[str, Any]:
    p = _config_file()
    if not p.is_file():
        return {
            "provider": DEFAULT_PROVIDER,
            "url": DEFAULT_URL,
            "model": DEFAULT_MODEL,
            "api_key": "",
            "agent_id": DEFAULT_AGENT_ID,
        }
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    return {
        "provider": str(data.get("provider") or DEFAULT_PROVIDER),
        "url": str(data.get("url") or DEFAULT_URL).strip() or DEFAULT_URL,
        "model": str(data.get("model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        "api_key": str(data.get("api_key") or ""),
        "agent_id": str(data.get("agent_id") or DEFAULT_AGENT_ID).strip(),
        "watch_brand": str(data.get("watch_brand") or "").strip(),
        "local_dir": str(data.get("local_dir") or "").strip(),
        "ai_notified": bool(data.get("ai_notified", False)),
        "ai_notified_hash": str(data.get("ai_notified_hash") or "").strip(),
    }


def mask_secret(value: Any) -> str:
    secret = str(value or "").strip()
    if not secret:
        return ""
    if len(secret) <= 4:
        return "****"
    return f"****{secret[-4:]}"


def redact_llm_config(config: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(config or {})
    api_key = str(redacted.get("api_key") or "")
    redacted["api_key"] = ""
    redacted["has_api_key"] = bool(api_key)
    redacted["api_key_masked"] = mask_secret(api_key)
    return redacted


def save_llm_config(provider: str, url: str, model: str, api_key: str, agent_id: str = "", watch_brand: str = "", local_dir: str = "", ai_notified: bool = False, ai_notified_hash: str = "") -> None:
    cfg = {
        "provider": (provider or DEFAULT_PROVIDER).strip(),
        "url": (url or DEFAULT_URL).strip(),
        "model": (model or DEFAULT_MODEL).strip(),
        "api_key": (api_key or "").strip(),
        "agent_id": (agent_id or "").strip(),
        "watch_brand": (watch_brand or "").strip(),
        "local_dir": (local_dir or "").strip(),
        "ai_notified": bool(ai_notified),
        "ai_notified_hash": str(ai_notified_hash or "").strip(),
    }
    p = _config_file()
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def test_llm_connection(
    *,
    provider: str,
    url: str,
    model: str,
    api_key: str,
    agent_id: str = "",
) -> str:
    if not str(url or "").strip():
        raise RuntimeError("接口地址为空")
    if not str(model or "").strip():
        raise RuntimeError("模型名为空")
    test_session_id = f"llm_config_test_{int(time.time() * 1000)}_{secrets.token_hex(3)}"
    text = chat_completions(
        url=str(url).strip(),
        api_key=api_key or "",
        model=str(model).strip(),
        messages=[
            {"role": "system", "content": "你只需要用中文回复：连接成功。"},
            {"role": "user", "content": "请回复连接成功"},
        ],
        session_id=test_session_id,
        agent_id=agent_id or "",
        timeout=30,
    )
    provider_text = provider or DEFAULT_PROVIDER
    return f"{provider_text} / {model} 连接成功：{text[:80]}"


def points_to_dataframe_csv(points: list[dict[str, Any]], max_chars: int = 50_000) -> str:
    """将轨迹点转为 pandas DataFrame 再输出 CSV，便于模型按表阅读。
    CONTRACT §4.5: snapshot 必须 token 可控。max_chars=50_000 约合 ~12.5K tokens。
    此函数仅作为历史兼容防御层，不应成为主要 AI 数据源。"""
    import pandas as pd

    if not points:
        return "(无轨迹点数据)"
    df = pd.DataFrame(points)
    preferred = ["lat", "lon", "alt", "time", "hr", "cadence"]
    cols = [c for c in preferred if c in df.columns]
    rest = [c for c in df.columns if c not in cols]
    df = df[cols + rest]
    buf = io.StringIO()
    df.to_csv(buf, index=True)
    text = buf.getvalue()
    if len(text) <= max_chars:
        return text
    n = len(df)
    step = max(2, int(math.ceil(len(text) / float(max_chars) * 1.15)))
    df2 = df.iloc[::step].copy()
    buf2 = io.StringIO()
    df2.to_csv(buf2, index=True)
    return (
        f"【说明】原始轨迹共 {n} 行，为控制上下文长度已按步长 {step} 下采样后附表。\n\n"
        + buf2.getvalue()
    )


def _placemarks_block(placemarks: list[dict[str, Any]]) -> str:
    if not placemarks:
        return "(无独立路点/打卡点)"
    try:
        return json.dumps(placemarks, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return str(placemarks)


def _sport_labels(sport_type: str) -> tuple[str, str]:
    key = str(sport_type or "").strip().lower()
    mapping = {
        "running": ("跑步", "资深的跑步教练"),
        "trail_running": ("越野跑", "顶级的越野跑教练"),
        "treadmill_running": ("室内跑步", "专业的跑步训练教练"),
        "walking": ("步行", "专业的健走训练顾问"),
        "hiking": ("徒步", "资深的户外徒步领队"),
        "mountaineering": ("登山", "资深的高海拔登山向导"),
        "cycling": ("骑行", "资深的骑行教练"),
        "road_cycling": ("公路骑行", "资深的公路骑行教练"),
        "mountain_biking": ("山地骑行", "资深的山地骑行教练"),
        "swimming": ("游泳", "资深的游泳教练"),
        "driving": ("驾车", "资深的道路驾驶安全教练"),
        "skiing": ("滑雪", "资深的滑雪教练"),
        "rowing": ("划船", "资深的赛艇教练"),
    }
    if key in mapping:
        return mapping[key]
    
    import re
    if re.search(r'[\u4e00-\u9fa5]', key):
        return (key, f"专业的{key}教练")
        
    if key:
        capitalized = key.replace('_', ' ').title()
        return (capitalized, f"Experienced {capitalized} Coach")
        
    return ("综合运动", "资深的运动训练教练")


def _weather_context_block(weather_context: dict[str, Any] | None) -> str:
    if not weather_context:
        return "【环境天气】无历史天气数据。"
    temperature = weather_context.get("temperature_c")
    humidity = weather_context.get("humidity")
    wind_speed = weather_context.get("wind_speed_kmh")
    label = str(weather_context.get("weather_label") or "").strip() or "未知"
    parts = [f"状况 {label}"]
    if temperature is not None:
        parts.append(f"温度 {temperature}°C")
    if humidity is not None:
        parts.append(f"湿度 {humidity}%")
    if wind_speed is not None:
        parts.append(f"风速 {wind_speed} km/h")
    return "【环境天气】本次运动时的环境为 " + "，".join(parts) + "。请在分析配速、心率、补给与体感压力时显式考虑高温高湿、风速等环境因素。"


def build_base_system_block(
    *,
    sport_type: str,
    provider: str,
    track_filename: str,
    points: list[dict[str, Any]],
    placemarks: list[dict[str, Any]],
    weather_context: dict[str, Any] | None = None,
    ai_snapshot_block: str = "",
) -> str:
    sport_cn, role = _sport_labels(sport_type)
    table = points_to_dataframe_csv(points)
    wpts = _placemarks_block(placemarks)
    mcp_note = ""
    if provider == "local_mcp":
        mcp_note = (
            "\n【工具/MCP】当用户问及个人成绩预测、深度复盘、需要与其历史运动对比时，"
            "你应通过当前网关可用的运动数据 MCP 工具获取用户最近若干次真实运动记录作为基准；"
            "切勿向用户罗列原始历史记录全文，结论务必简短。\n"
        )
    snapshot = f"\n{ai_snapshot_block}\n" if ai_snapshot_block else ""
    return f"""你是一位{role}与 AI 户外领队。用户活动类型：【{sport_cn}】。
当前轨迹文件：{track_filename}
{mcp_note}
{snapshot}
【高密度轨迹明细表】
以下为 pandas 导出 CSV（含 lat、lon、alt、time、hr、cadence 等列，索引为点序号）：
```
{table}
```

【路点 / 打卡点 JSON】
```json
{wpts}
```

{_weather_context_block(weather_context)}

【界面约束】你的回复将显示在极窄侧边栏，务必极度简练；除非用户明确要求，否则不要用冗长列表。
禁止调用或假设任何写本地文件、生成下载文件的操作。
"""


def build_report_user_prompt_terrain(sport_type: str) -> str:
    _, role = _sport_labels(sport_type)
    return f"""你是一位{role}。请根据 System 中给出的完整 GPS 轨迹明细表，生成【标准路线路书与评估报告】。

请直接回复 Markdown 纯文本。【核心警告】：绝对不要调用任何写文件、保存本地文件或生成 MD 文件的工具。
内容必须极度简练（侧边栏极窄，每个板块一两句话，总字数控制在 150 字内）。包含：
1. ⛰️ **赛道/路线整体评估**
2. 🏃 **常规体能分配建议**
3. ⚠️ **客观环境风险与安全警示**
4. 🎒 **标准建议装备与补给**"""


def build_report_user_prompt_personalized(sport_type: str, provider: str) -> str:
    sport_cn, role = _sport_labels(sport_type)
    mcp = ""
    if provider == "local_mcp":
        mcp = (
            "【严格工具调用指令】请务必调用运动数据(如高驰 COROS) MCP 工具获取用户最近 5 次真实"
            f"{sport_cn}记录。若工具失败或未授权，仅回复："
            "「❌ 获取高驰历史数据失败或超时。无法进行精准预测，请检查 OpenClaw/QClaw 工具配置或网络状态。」"
            "禁止瞎猜、禁止保存文件。\n\n"
        )
    return f"""{mcp}你是一位{role}。请根据 System 中的完整 GPS 轨迹明细，并结合（如可用）工具返回的**最近 5 次真实{sport_cn}历史**作为体能基准，
生成【极简版】{sport_cn}预测报告。

请直接回复 Markdown 纯文本。【核心警告】：绝对不要罗列近期运动原始数据；绝对不要调用写文件工具。
总字数控制在 150 字内，仅包含：
1. ⏱️ **预计用时**
2. 🏃 **建议配速**（含心率控制简述）
3. 🎒 **建议补给**"""


def build_chat_system_block(
    *,
    sport_type: str,
    provider: str,
    track_filename: str,
    points: list[dict[str, Any]],
    placemarks: list[dict[str, Any]],
    report_json: str | None = None,
    weather_context: dict[str, Any] | None = None,
    ai_snapshot_block: str = "",
) -> str:
    sport_cn, _ = _sport_labels(sport_type)
    if not points or len(points) < 2:
        return (
            "用户当前未导入有效轨迹（少于 2 个点）。你作为户外与运动专家，在极窄侧边栏中回答，"
            "务必极度简短（尽量不超过 100 字）。"
        )
    base = build_base_system_block(
        sport_type=sport_type,
        provider=provider,
        track_filename=track_filename,
        points=points,
        placemarks=placemarks,
        weather_context=weather_context,
        ai_snapshot_block=ai_snapshot_block,
    )
    report_instruction = ""
    if report_json:
        report_instruction = f"""

【系统隐藏设定】以下是系统基于核心算法自动为您生成的路线深度分析报告 JSON 原稿。用户在 UI 面板上已经看到了这些核心建议（如配速、补给、预估用时）。在接下来的对话中，请严格以此报告的数据作为你的'长期记忆'和'回答基准'。如果用户问及报告中的细节（例如'为什么带3L水'），请直接基于这份 JSON 数据进行合理的延伸解释，绝不允许在后续对话中给出与此 JSON 矛盾的数据或建议。

```json
{report_json}
```"""
    return (
        base
        + f"\n用户计划或已完成【{sport_cn}】。若问及地理位置，可根据经纬度推断；禁止保存文件。{report_instruction}\n"
    )


def chat_completions(
    *,
    url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    session_id: str,
    agent_id: str = "",
    timeout: int = 300,
) -> str:
    headers = {"Content-Type": "application/json"}
    if api_key and api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    if agent_id and str(agent_id).strip():
        headers["X-Agent-ID"] = str(agent_id).strip()
        headers["X-Agent-Id"] = str(agent_id).strip()

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "stream": False,
        "session_id": session_id,
        "chat_id": session_id,
        "user": session_id,
    }
    if agent_id and str(agent_id).strip():
        body["agent_id"] = str(agent_id).strip()
        body["agentId"] = str(agent_id).strip()
    try:
        t0 = time.time()
        r = requests.post(url, headers=headers, json=body, timeout=timeout)
        elapsed = time.time() - t0
    except requests.RequestException as e:
        raise RuntimeError(f"网络请求失败: {e}") from e

    if not r.ok:
        err = ""
        try:
            err_obj = r.json()
            err = err_obj.get("message") or json.dumps(err_obj, ensure_ascii=False)[:800]
        except Exception:
            err = (r.text or "")[:800]
        if r.status_code == 401:
            raise RuntimeError(f"认证失败 (401): API Key 无效或未填写。{err}")
        if r.status_code == 502:
            raise RuntimeError(f"网关超时 (502): 调用工具或上游耗时过长。{err}")
        raise RuntimeError(f"HTTP {r.status_code}: {err}")

    try:
        data = r.json()
    except json.JSONDecodeError as e:
        raise RuntimeError("响应不是合法 JSON") from e

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("响应中无 choices 字段")
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if not content:
        raise RuntimeError("模型未返回内容")
    return str(content)




def _insight_mode_sport(sport_type: str) -> str:
    key = str(sport_type or "").strip().lower()
    if key in ("running", "trail_running", "treadmill_running", "walking", "hiking", "mountaineering"):
        return "running"
    if key in ("cycling", "road_cycling", "mountain_biking"):
        return "cycling"
    if key in ("swimming", "lap_swimming", "open_water"):
        return "swimming"
    return "general"


RISK_ASSESSMENT_OUTPUT_SCHEMA = """{
  "supply_risk": {"level": "低|中|高", "advice": "补给、水、电解质、能量相关建议"},
  "weather_risk": {"level": "低|中|高", "advice": "温度、湿度、风、雨、低温等环境风险建议"},
  "equipment_risk": {"level": "低|中|高", "advice": "装备、防晒、防雨、头灯、急救等建议"},
  "physical_risk": {"level": "低|中|高", "advice": "体力分配、爬升压力、心率、节奏控制建议"},
  "disclaimer": "以上建议由 AI 生成，仅供参考，请结合自身经验和实际情况判断。"
}"""


def _risk_snapshot_payload(snapshot: dict[str, Any] | None, weather_context: dict[str, Any] | None = None) -> str:
    allowed_keys = (
        "activity_id", "sport_type", "sub_sport_type", "distance_km", "distance_display",
        "duration_sec", "avg_pace", "avg_pace_display", "pace_unit", "avg_hr", "max_hr",
        "calories", "elevation_gain_m", "max_alt_m", "min_alt_m", "total_descent_m",
        "avg_cadence", "normalized_power", "swolf", "tss", "start_time", "region",
        "hr_decoupling", "device_name", "up_count", "down_count", "max_single_climb_m",
        "difficulty_score", "report_metrics_version", "source",
    )
    safe_snapshot = {}
    if isinstance(snapshot, dict):
        safe_snapshot = {key: snapshot.get(key) for key in allowed_keys if key in snapshot}
    safe_weather = weather_context if isinstance(weather_context, dict) else None
    return json.dumps(
        {"activity_snapshot": safe_snapshot, "weather_context": safe_weather},
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def build_risk_assessment_system_prompt(snapshot: dict[str, Any] | None, weather_context: dict[str, Any] | None = None) -> str:
    payload = _risk_snapshot_payload(snapshot, weather_context)
    return f"""你是一位专业户外运动风险分析师，只负责对系统提供的运动数据进行风险解读。

【数据边界 — DATA BOUNDARY（不可逾越）】
以下数据来自 DB canonical / Resolver truth / 后端权威上下文。你只允许解释，禁止生成或修改事实字段。

【当前功能区权威快照】
{payload}

【分析维度】
你必须从以下四个维度进行风险预警：
1. 补给风险：水、能量、盐丸、电解质、低血糖、脱水
2. 天气风险：温度、湿度、风、雨、低温、暴晒
3. 装备风险：防雨、防晒、头灯、急救包、保暖、防滑、路线装备
4. 体力风险：爬升压力、运动时长、心率压力、节奏控制、后程衰减

【强制禁止行为】
你 MUST NOT：
- 重新计算距离
- 推断配速
- 还原坡度
- 重新计算爬升
- 重建 per-point 数据
- 使用前端 points[] 或 DOM 推导值
- 使用 shadow_diff、shadow_diff_json、diff
- 生成任何 canonical 指标或写回字段建议
- 输出 markdown 代码块

【输出格式 — 严格 JSON】
只输出一个合法 JSON 对象，格式必须为：
{RISK_ASSESSMENT_OUTPUT_SCHEMA}

【等级约束】
level 只能使用 "低"、"中"、"高" 三个值。
"""


def build_risk_assessment_user_prompt() -> str:
    return "请基于系统指令中的权威数据快照生成风险预警 JSON。只输出纯 JSON，不要输出 markdown 标记，不要补充额外解释。"


def empty_risk_assessment(error: str = "") -> dict[str, Any]:
    default_advice = "暂无足够数据，建议结合实际路线和个人状态谨慎判断。"
    return {
        "supply_risk": {"level": "中", "advice": default_advice},
        "weather_risk": {"level": "中", "advice": default_advice},
        "equipment_risk": {"level": "中", "advice": default_advice},
        "physical_risk": {"level": "中", "advice": default_advice},
        "disclaimer": "以上建议由 AI 生成，仅供参考，请结合自身经验和实际情况判断。",
        "error": str(error or ""),
    }


def _normalize_risk_level(level: Any) -> str:
    text = str(level or "").strip()
    return text if text in {"低", "中", "高"} else "中"


def _normalize_risk_item(value: Any) -> dict[str, str]:
    default_advice = "暂无足够数据，建议结合实际路线和个人状态谨慎判断。"
    if not isinstance(value, dict):
        value = {}
    return {
        "level": _normalize_risk_level(value.get("level")),
        "advice": str(value.get("advice") or default_advice)[:500],
    }


def normalize_risk_assessment_json(raw_text: str) -> dict[str, Any]:
    if not raw_text:
        return empty_risk_assessment("LLM 未返回内容")

    text = str(raw_text).strip()
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return empty_risk_assessment(f"JSON 解析失败: {text[:120]}")

    if not isinstance(data, dict):
        return empty_risk_assessment("风险预警结果格式错误")

    schema = empty_risk_assessment(str(data.get("error") or ""))
    for key in ("supply_risk", "weather_risk", "equipment_risk", "physical_risk"):
        schema[key] = _normalize_risk_item(data.get(key))
    schema["disclaimer"] = str(data.get("disclaimer") or schema["disclaimer"])[:500]
    return schema



RADAR_DIMENSION_INTERPRETATION: dict[str, str] = {
    "endurance": "耐力:基于 Banister 专业训练负荷 + 42 天 PMC 长期负荷(慢性训练负荷)。专业训练负荷<30→20 分,30~80→50 分,80~150→75 分,≥150→95 分。慢性训练负荷反映长期训练负荷累积。",
    "recovery": "恢复:直接消费 user_profile.hrv_baseline(来自 Garmin Connect / MCP 画像同步),clamp 到 [0, 100]。fallback = 60。",
    "stability": "心肺稳定:基于有氧解耦 Pa:Hr 90 天最近 5 次均值。decoupling<5%→95 分,5~10%→75 分,10~15%→55 分,≥15%→30 分。",
    "threshold": "阈值:基于乳酸阈值心率(20 分钟滑动窗口 × 0.95)90 天最大值。threshold_hr/max_hr <0.75→40 分,0.75~0.82→65 分,0.82~0.88→82 分,≥0.88→95 分。",
    "climbing": "爬升:基于后端『有效爬坡段』算法计算的 VAM(m/h = 有效段累计爬升 / 有效段时间 × 3600),经 90 天可信活动过滤(cycling / road_cycling / mountain_biking / running ≥ 20m@1km,trail_running ≥ 30m@1km,hiking ≥ 50m@1km)与 p90 聚合后得到。低爬升通勤 / 平路活动不作为爬升能力依据。阈值随运动类型变化:running 默认 300 / 600 / 900 m/h,cycling 100 / 250 / 500 m/h,hiking 100 / 200 / 400 m/h。LLM 只能解释系统提供的 canonical snapshot,禁止重新计算或推断。",
    "anaerobic": "无氧爆发:基于 30 秒滑动窗口峰值速度 90 天最大值。跑步<3 m/s→20 分,3~5→50 分,5~7→75 分,≥7→95 分;骑行<8→20 分,8~12→50 分,12~16→75 分,≥16→95 分。",
}

RADAR_INSIGHT_OUTPUT_SCHEMA = """{
  "summary": "80 字以内的中文总结,概述该运动类型的整体能力画像与亮点短板",
  "sport_type": "running|trail_running|hiking|cycling|swimming",
  "sport_mode": "running|cycling|swimming|general",
  "dimension_interpretation": [
    {
      "key": "endurance|recovery|stability|threshold|climbing|anaerobic",
      "label": "中文维度名(耐力/恢复/心肺稳定/阈值/爬升/无氧爆发)",
      "score": 0-100 整数,
      "comment": "30-60 字解读:该维度当前水平的具体含义,以及提升建议方向"
    }
  ],
  "strongest_dim": "得分最高维度的 key",
  "weakest_dim": "得分最低维度的 key",
  "balance_assessment": "均衡|轻度失衡|失衡 — 6 维度间离散度",
  "load_status": {
    "ctl": 数字,
    "atl": 数字,
    "tsb": 数字,
    "status": "状态轻松|理想|压力状态|过度训练 — 综合训练平衡度解读"
  },
  "training_advice": "针对最弱维度的具体训练建议,120 字以内",
  "long_term_trend": "提升|稳定|下滑 — 90 天能力趋势(基于慢性训练负荷走向)",
  "disclaimer": "AI 生成仅供参考,具体训练请结合个人实际"
}"""


def _build_radar_insight_snapshot_payload(snapshot: dict[str, Any] | None) -> str:
    """将 radar insight snapshot 序列化为 system prompt 可嵌入的 JSON 字符串。
    §5.4 规则 3:仅暴露后端权威字段,严禁前端计算值或 DOM 推导值。
    """
    if not snapshot:
        return "{}"
    return json.dumps(
        snapshot,
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def build_radar_insight_system_prompt(
    snapshot: dict[str, Any] | None,
    sport_type: str,
) -> str:
    """雷达图 AI 洞察 system prompt 构建器。"""
    payload = _build_radar_insight_snapshot_payload(snapshot)

    sport_cn_map = {
        "running": "跑步",
        "trail_running": "越野跑",
        "treadmill_running": "跑步机",
        "hiking": "徒步",
        "mountaineering": "登山",
        "cycling": "骑行",
        "road_cycling": "公路骑行",
        "mountain_biking": "山地骑行",
        "swimming": "游泳",
        "lap_swimming": "泳池游泳",
        "open_water": "公开水域",
    }
    sport_cn = sport_cn_map.get(sport_type, sport_type or "运动")

    mode = _insight_mode_sport(sport_type)

    return f"""你是一位资深运动表现分析师与训练科学专家,专长于{sport_cn}长期能力画像分析。

【数据边界 — DATA BOUNDARY(不可逾越)】
以下数据由脉图系统从 SQLite canonical DB / 雷达后端引擎 / 用户画像 Resolver 预计算,**绝对权威**。你只允许解释(interpret),禁止任何形式的重新推导、估算、推断。

【当前功能区权威快照 — 90 天滚动聚合】
```json
{payload}
```

【6 维度评分含义解读(供你理解为何得此分)】
- {RADAR_DIMENSION_INTERPRETATION['endurance']}
- {RADAR_DIMENSION_INTERPRETATION['recovery']}
- {RADAR_DIMENSION_INTERPRETATION['stability']}
- {RADAR_DIMENSION_INTERPRETATION['threshold']}
- {RADAR_DIMENSION_INTERPRETATION['climbing']}
- {RADAR_DIMENSION_INTERPRETATION['anaerobic']}

【运动专项约束(基于 {mode} 模式)】
- 若 sport_mode == "running":重点解读配速相关维度(endurance / stability),爬升因人而异
- 若 sport_mode == "cycling":重点解读功率与心率漂移(stability / threshold),爬升由垂直爬升速率体现
- 若 sport_mode == "swimming":重点解读耐力持续性(endurance / threshold),爬升维度不适用(N/A)
- 若 sport_mode == "general":均衡解读 6 维度

【运动专项爬升维度解读 — 涉及 VAM 阈值差异时遵循】
- 爬升(VAM)阈值按 sport_type 分支:cycling/road_cycling/mountain_biking 用 100/250/500 m/h,
  hiking 用 100/200/400 m/h,其他运动(跑步/越野跑)沿用 300/600/900 m/h。
- 解读骑行/徒步用户爬升维度时:
  · 必须先说明阈值基准("该得分基于骑行 VAM 基准,不同于跑步")
  · 重点呈现 vam 数值本身(m/h)而非分数,因骑行/徒步 VAM 上限低于跑步
  · 不得跨运动类比("您比跑步用户的爬升差"——评分体系本就不同)
- 解读跑步/越野跑用户爬升维度时:维持现有叙事(分数与阈值对照即可)。

【必须输出维度】
dimension_interpretation 数组必须严格包含该运动类型 schema 中的所有维度(参考现有雷达图 RADAR_SCHEMAS):
- running: endurance, recovery, stability, threshold, climbing, anaerobic(6 个)
- trail_running: endurance, recovery, stability, climbing, anaerobic(5 个,无 threshold)
- cycling: endurance, recovery, stability, threshold, climbing, anaerobic(6 个)
- hiking: endurance, recovery, climbing(3 个)
- swimming: endurance, recovery, threshold(3 个)

【强行约束 — 绝对禁止行为】
你 MUST NOT:
- 重新计算距离、时间、配速、心率、爬升
- 还原或推断 per-point 数据
- 重新计算专业训练负荷 / 垂直爬升速率 / threshold_hr / decoupling / anaerobic_peak
- 重新计算慢性训练负荷 / 急性训练负荷 / 训练平衡度
- 使用前端 DOM 推导值或 UI fallback 值
- 使用 shadow_diff / shadow_diff_json / diff / 任何 debug-only 字段
- 生成任何 canonical 指标或写回字段建议
- 跨能力区域胡乱联想(例如把跑步洞察写成骑行)
- 输出 markdown 代码块标记
- 忽略维度缺失维度(score 为 0 时,comment 写"暂无足够数据"而非略过)

【输出格式 — 严格 JSON】
只输出一个合法 JSON 对象,格式必须严格遵循:
{RADAR_INSIGHT_OUTPUT_SCHEMA}

【铁律】
1. 只使用上方【权威快照】中的数值,禁止重新计算
2. dimension_interpretation 数组必须覆盖该 sport_type 的全部 schema 维度
3. 输出必须是纯 JSON,不要包含 markdown 代码块标记
4. 所有数值字段必须填数字,文本字段填中文
5. training_advice 必须针对 weakest_dim 给出具体可执行建议
6. balance_assessment 判定:6 维度极差 < 15 = 均衡,15~30 = 轻度失衡,≥30 = 失衡
7. load_status.status 判定:训练平衡度 > 5 = 状态轻松,0~5 = 理想,-10~0 = 压力状态,<-10 = 过度训练
"""


def build_radar_insight_user_prompt(sport_type: str) -> str:
    """雷达图 AI 洞察 user prompt:触发 LLM 输出的固定指令。"""
    sport_cn_map = {
        "running": "跑步", "trail_running": "越野跑", "hiking": "徒步",
        "cycling": "骑行", "swimming": "游泳",
    }
    sport_cn = sport_cn_map.get(sport_type, sport_type or "该运动")
    return (
        f"请基于系统指令中提供的 90 天{sport_cn}雷达图权威快照,"
        f"生成结构化 JSON 解读。只输出纯 JSON,不要输出 markdown 标记,"
        f"不要补充额外解释,不要寒暄。"
    )


def empty_radar_insight(error: str = "") -> dict[str, Any]:
    """雷达图 AI 洞察空态:LLM 失败 / 无数据 / 无维度时使用。"""
    return {
        "summary": error or "暂无 90 天数据,无法生成洞察",
        "sport_type": "",
        "sport_mode": "general",
        "dimension_interpretation": [],
        "strongest_dim": None,
        "weakest_dim": None,
        "balance_assessment": "well_balanced",
        "load_status": {
            "ctl": 0,
            "atl": 0,
            "tsb": 0,
            "status": "optimal",
        },
        "training_advice": "请先积累 90 天运动数据后再生成洞察",
        "long_term_trend": "stable",
        "disclaimer": "AI 生成仅供参考,具体训练请结合个人实际",
        "error": str(error or ""),
    }


def normalize_radar_insight_json(raw_text: str) -> dict[str, Any]:
    """将 LLM 返回的原始文本标准化为 radar insight schema。
    失败时返回 empty_radar_insight,严禁抛异常至前端。
    """
    if not raw_text:
        return empty_radar_insight("LLM 未返回内容")

    text = raw_text.strip()

    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return empty_radar_insight(f"JSON 解析失败: {text[:120]}")

    if not isinstance(data, dict):
        return empty_radar_insight("洞察结果格式错误")

    schema = empty_radar_insight()
    schema["summary"] = str(data.get("summary") or schema["summary"])[:300]
    schema["sport_type"] = str(data.get("sport_type") or schema["sport_type"])
    schema["sport_mode"] = str(data.get("sport_mode") or schema["sport_mode"])
    schema["strongest_dim"] = str(data.get("strongest_dim") or "") or None
    schema["weakest_dim"] = str(data.get("weakest_dim") or "") or None
    schema["balance_assessment"] = str(data.get("balance_assessment") or "均衡")
    schema["training_advice"] = str(data.get("training_advice") or schema["training_advice"])[:500]
    schema["long_term_trend"] = str(data.get("long_term_trend") or "稳定")
    schema["disclaimer"] = str(data.get("disclaimer") or schema["disclaimer"])[:300]

    raw_dims = data.get("dimension_interpretation") or []
    if isinstance(raw_dims, list):
        clean_dims = []
        for d in raw_dims[:6]:
            if not isinstance(d, dict):
                continue
            try:
                score_val = int(d.get("score") or 0)
            except (TypeError, ValueError):
                score_val = 0
            score_val = max(0, min(score_val, 100))
            clean_dims.append({
                "key": str(d.get("key") or ""),
                "label": str(d.get("label") or d.get("key") or ""),
                "score": score_val,
                "comment": str(d.get("comment") or "")[:200],
            })
        schema["dimension_interpretation"] = clean_dims

    raw_load = data.get("load_status") or {}
    if isinstance(raw_load, dict):
        try:
            schema["load_status"]["ctl"] = float(raw_load.get("ctl") or 0)
            schema["load_status"]["atl"] = float(raw_load.get("atl") or 0)
            schema["load_status"]["tsb"] = float(raw_load.get("tsb") or 0)
            schema["load_status"]["status"] = str(
                raw_load.get("status") or schema["load_status"]["status"]
            )
        except (TypeError, ValueError):
            pass

    return schema
