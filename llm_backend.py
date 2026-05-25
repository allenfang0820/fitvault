"""
大模型调用：读取本地配置，使用 requests 访问 OpenAI 兼容接口；
将轨迹 DataFrame（高密度点表）拼入 System Prompt。
"""

from __future__ import annotations

import io
import json
import math
import sys
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
    }


def save_llm_config(provider: str, url: str, model: str, api_key: str, agent_id: str = "", watch_brand: str = "", local_dir: str = "") -> None:
    cfg = {
        "provider": (provider or DEFAULT_PROVIDER).strip(),
        "url": (url or DEFAULT_URL).strip(),
        "model": (model or DEFAULT_MODEL).strip(),
        "api_key": (api_key or "").strip(),
        "agent_id": (agent_id or "").strip(),
        "watch_brand": (watch_brand or "").strip(),
        "local_dir": (local_dir or "").strip(),
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
    text = chat_completions(
        url=str(url).strip(),
        api_key=api_key or "",
        model=str(model).strip(),
        messages=[
            {"role": "system", "content": "你只需要用中文回复：连接成功。"},
            {"role": "user", "content": "请回复连接成功"},
        ],
        session_id="llm_config_test",
        agent_id=agent_id or "",
        timeout=30,
    )
    provider_text = provider or DEFAULT_PROVIDER
    return f"{provider_text} / {model} 连接成功：{text[:80]}"


def points_to_dataframe_csv(points: list[dict[str, Any]], max_chars: int = 420_000) -> str:
    """将轨迹点转为 pandas DataFrame 再输出 CSV，便于模型按表阅读。"""
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
        r = requests.post(url, headers=headers, json=body, timeout=timeout)
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


# ═══════════════════════════════════════════════════════
# Insight Engine — Schema-Driven AI Sports Analysis
# Task 3.3: 将 AI 从"被动问答"升级为"结构化运动洞察引擎"
# ═══════════════════════════════════════════════════════

import re

INSIGHT_SCHEMA_DESCRIPTION = """{
  "summary": "一段中文总结，50字以内",
  "performance_grade": "S|A|B|C|D 五级之一",
  "key_metrics": {
    "pace_efficiency": "excellent|good|fair|poor — 配速稳定性评价",
    "hr_efficiency": "excellent|good|fair|poor — 心率经济性评价",
    "endurance": "excellent|good|fair|poor — 耐力表现评价",
    "climbing_ability": "excellent|good|fair|poor|N/A — 爬坡能力评价"
  },
  "anomalies": ["异常发现列表，如心率异常区间、配速崩塌段等，无则空数组"],
  "strengths": ["本次运动亮点列表"],
  "risks": ["需要关注的风险点列表，如过度疲劳迹象、心率过高等"],
  "training_load": "high|moderate|low — 本次训练负荷评估",
  "fatigue_index": 0-100 整数，0=极轻松 100=极度疲劳,
  "efficiency_index": 0-100 整数，0=低效 100=极高效率,
  "recommendation": "针对该次运动的训练建议，80字以内",
  "sport_mode": "running|cycling|swimming|general"
}"""

# Task 4.2: Insight 展示字段顺序（仅声明渲染顺序，不改 schema / prompt / value）
INSIGHT_FIELD_ORDER = [
    "performance_summary",
    "body_load",
    "efficiency_analysis",
    "risk_warning",
    "history_comparison",
]


def _insight_mode_sport(sport_type: str) -> str:
    key = str(sport_type or "").strip().lower()
    if key in ("running", "trail_running", "treadmill_running", "walking", "hiking", "mountaineering"):
        return "running"
    if key in ("cycling", "road_cycling", "mountain_biking"):
        return "cycling"
    if key in ("swimming", "lap_swimming", "open_water"):
        return "swimming"
    return "general"


def _build_insight_system_prompt(
    snapshot: dict[str, Any] | None,
    mode: str,
    history_block: str = "",
) -> str:
    if not snapshot:
        return "无可用运动数据，无法生成分析。"

    sport_cn = str(snapshot.get("sport_type") or "综合运动")
    dist_display = snapshot.get("distance_display") or "--"
    duration_sec = snapshot.get("duration_sec") or 0
    dur_min = int(duration_sec // 60) if duration_sec else 0
    avg_hr = snapshot.get("avg_hr") or "--"
    max_hr = snapshot.get("max_hr") or "--"
    pace_display = snapshot.get("avg_pace_display") or "--"
    elevation = snapshot.get("elevation_gain_m") or 0
    calories = snapshot.get("calories") or "--"
    tss = snapshot.get("tss")
    np_val = snapshot.get("normalized_power")

    mode_specific = ""
    if mode == "running":
        mode_specific = f"""【跑步专项分析指令】
- 评估配速结构：前/中/后半程配速是否稳定，是否有明显衰减
- 评估心率效率：在给定配速下心率是否经济（低心率+稳定配速 = good）
- 评估后半程衰减：对比前50%与后50%的平均配速差异超过10%记为风险
- 结合爬升 {elevation}m 评估爬坡对配速/心率的影响"""
    elif mode == "cycling":
        mode_specific = f"""【骑行专项分析指令】
- 评估功率区间分布（如存在 NP={np_val}W）
- 评估心率漂移：长时间稳定输出下心率是否可控
- 评估节奏稳定性：变速频繁程度
- 结合爬升 {elevation}m 评估爬坡段输出"""
    elif mode == "swimming":
        mode_specific = """【游泳专项分析指令】
- 评估划水效率（如存在 SWOLF 数据）
- 评估耐力持续性
- 评估速度稳定性"""

    hist = f"\n{history_block}\n" if history_block else ""

    return f"""你是一位资深运动表现分析师，专长于{sport_cn}数据分析。

{hist}
{mode_specific}

【数据边界 — DATA BOUNDARY（不可逾越）】
以下运动数据由系统预计算，**绝对权威**。你只允许解释（interpret），禁止任何形式的重新推导。

【当前运动数据 — 系统真值（禁止重新计算）】
- 运动类型: {sport_cn}
- 距离: {dist_display}
- 用时: {dur_min} 分钟
- 平均配速: {pace_display}
- 平均心率: {avg_hr} bpm / 最大心率: {max_hr} bpm
- 卡路里: {calories}
- 累计爬升: {elevation} m
- TSS: {tss if tss is not None else 'N/A'}

【强行约束 — 绝对禁止行为】
你 MUST NOT：
- 重新计算距离（recompute distance）
- 推断配速（estimate pace）
- 还原坡度（infer slope）
- 重建 per-point 数据（reconstruct per-point data）
- 使用任何外部假设（use any external assumptions）
- 生成训练负荷/疲劳模型等推理结构（no training_load model / fatigue model）
- 将历史数据作为分析引擎输入（history is context reference ONLY）

【输出格式 — 严格 JSON】
你必须返回一个合法 JSON 对象，格式如下：
{INSIGHT_SCHEMA_DESCRIPTION}

【评分细则】
- S: 精英级（心率极低、配速稳定、效率极高）
- A: 优秀（配速心率均衡、无明显衰减）
- B: 良好（整体可接受、存在局部优化空间）
- C: 一般（有明显疲劳、心率偏高或配速不稳）
- D: 需关注（严重疲劳、多项指标异常）

【铁律】
1. 只使用上方【当前运动数据】中的数值，禁止重新计算
2. 禁止使用轨迹点做推断
3. 输出必须是纯 JSON，不要包含 markdown 代码块标记
4. 所有数值字段必须填数字，文本字段填中文
5. 无相关能力的指标填 "N/A"
6. 训练负荷/疲劳指数/效率指数仅基于上述数值做定性评估
"""


def _build_insight_user_prompt() -> str:
    return "请根据系统指令中提供的运动数据，生成结构化 JSON 分析报告。不要输出 markdown 标记，只输出纯 JSON。"


def normalize_insight_json(raw_text: str) -> dict[str, Any]:
    """将 LLM 返回的原始文本标准化为 insight schema。"""
    if not raw_text:
        return _empty_insight("LLM 未返回内容")

    text = raw_text.strip()

    # 去除可能的 markdown 代码块包裹
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()

    # 找到第一个 { 到最后一个 } 之间的 JSON
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return _empty_insight(f"JSON 解析失败: {text[:100]}")

    schema = {
        "summary": "",
        "performance_grade": "C",
        "key_metrics": {
            "pace_efficiency": "fair",
            "hr_efficiency": "fair",
            "endurance": "fair",
            "climbing_ability": "N/A",
        },
        "anomalies": [],
        "strengths": [],
        "risks": [],
        "training_load": "moderate",
        "fatigue_index": 50,
        "efficiency_index": 50,
        "recommendation": "",
        "sport_mode": "general",
    }

    def _str(v: Any) -> str:
        return str(v) if v is not None else ""

    def _int_range(v: Any, default: int = 50) -> int:
        try:
            val = int(float(str(v)))
            return max(0, min(100, val))
        except (TypeError, ValueError):
            return default

    schema["summary"] = _str(data.get("summary") or data.get("总结") or "")
    grade = _str(data.get("performance_grade") or data.get("grade") or "C").upper()
    schema["performance_grade"] = grade if grade in ("S", "A", "B", "C", "D") else "C"

    km = data.get("key_metrics") or {}
    schema["key_metrics"]["pace_efficiency"] = _str(
        km.get("pace_efficiency") or km.get("配速效率") or "fair"
    )
    schema["key_metrics"]["hr_efficiency"] = _str(
        km.get("hr_efficiency") or km.get("心率效率") or "fair"
    )
    schema["key_metrics"]["endurance"] = _str(
        km.get("endurance") or km.get("耐力") or "fair"
    )
    schema["key_metrics"]["climbing_ability"] = _str(
        km.get("climbing_ability") or km.get("爬坡能力") or "N/A"
    )

    for key in ("anomalies", "strengths", "risks"):
        val = data.get(key) or data.get(
            {"anomalies": "异常", "strengths": "亮点", "risks": "风险"}.get(key, key)
        ) or []
        if isinstance(val, list):
            schema[key] = [str(x) for x in val[:8]]
        elif isinstance(val, str):
            schema[key] = [val] if val else []

    load = _str(data.get("training_load") or data.get("训练负荷") or "moderate")
    schema["training_load"] = load if load in ("high", "moderate", "low") else "moderate"

    schema["fatigue_index"] = _int_range(
        data.get("fatigue_index") or data.get("疲劳指数"), 50
    )
    schema["efficiency_index"] = _int_range(
        data.get("efficiency_index") or data.get("效率指数"), 50
    )
    schema["recommendation"] = _str(
        data.get("recommendation") or data.get("建议") or ""
    )
    mode = _str(data.get("sport_mode") or data.get("运动模式") or "general")
    schema["sport_mode"] = mode if mode in ("running", "cycling", "swimming", "general") else "general"

    return schema


def _empty_insight(error: str = "") -> dict[str, Any]:
    return {
        "summary": error or "无可用数据",
        "performance_grade": "C",
        "key_metrics": {
            "pace_efficiency": "N/A",
            "hr_efficiency": "N/A",
            "endurance": "N/A",
            "climbing_ability": "N/A",
        },
        "anomalies": [],
        "strengths": [],
        "risks": [],
        "training_load": "low",
        "fatigue_index": 0,
        "efficiency_index": 0,
        "recommendation": error or "当前无法生成分析",
        "sport_mode": "general",
    }
