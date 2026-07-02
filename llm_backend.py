"""
大模型调用：读取本地配置，使用 requests 访问 OpenAI 兼容接口；
将轨迹点表（高密度点表）拼入 System Prompt。
"""

from __future__ import annotations

import io
import csv
import errno
import json
import math
import os
import plistlib
import re
import secrets
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests

DEFAULT_URL = "http://localhost:3000/v1/chat/completions"
DEFAULT_MODEL = "openclaw"
DEFAULT_PROVIDER = "local_mcp"
DEFAULT_AGENT_ID = ""
DEFAULT_TRANSPORT = "http"
DEFAULT_CLI_TIMEOUT_SEC = 300
VALID_TRANSPORTS = {"http", "cli"}
VALID_CLI_TYPES = {"codex", "openclaw", "claude", "custom"}
VALID_GARMIN_REGIONS = {"cn", "global"}
VALID_COROS_REGIONS = {"cn", "us", "eu"}
CLI_ERROR_SNIPPET_CHARS = 800
QCLAW_LAUNCHAGENT_ENV_KEYS = {
    "AUTH_GATEWAY_PORT",
    "NODE_EXTRA_CA_CERTS",
    "NODE_USE_SYSTEM_CA",
    "OPENCLAW_CONFIG_PATH",
    "OPENCLAW_GATEWAY_PORT",
    "OPENCLAW_LAUNCHD_LABEL",
    "OPENCLAW_SERVICE_KIND",
    "OPENCLAW_SERVICE_MARKER",
    "OPENCLAW_SERVICE_VERSION",
    "OPENCLAW_STATE_DIR",
    "QCLAW_LLM_API_KEY",
    "QCLAW_LLM_BASE_URL",
    "QCLAW_WECHAT_WS_URL",
}
CONFIG_DIR_NAME = ".fitvault"
CONFIG_FILE_NAME = "llm_config.json"


def _legacy_project_config_file() -> Path:
    return Path(__file__).resolve().parent / CONFIG_FILE_NAME


def _user_config_dir() -> Path:
    d = Path.home() / CONFIG_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _migrate_legacy_project_config(target: Path) -> None:
    """Copy the development-era project config once, without overwriting user config."""
    if getattr(sys, "frozen", False) or target.exists():
        return
    legacy = _legacy_project_config_file()
    try:
        if legacy.resolve() == target.resolve() or not legacy.is_file():
            return
        payload = legacy.read_text(encoding="utf-8")
        json.loads(payload)
        target.write_text(payload, encoding="utf-8")
    except Exception:
        # Migration is best-effort; failure must degrade to an unconfigured state.
        return


def _config_file() -> Path:
    """配置文件路径。
    开发态与打包态都始终存放在用户主目录的隐藏文件夹中，确保 DMG
    覆盖升级不会丢配置，也避免分享 .app 时携带开发者的 API Key。
    """
    target = _user_config_dir() / CONFIG_FILE_NAME
    _migrate_legacy_project_config(target)
    return target


def load_llm_config() -> dict[str, Any]:
    """从磁盘加载 LLM 配置。

    CONTRACT §2.1 / §7.2: 不做隐式默认值注入。
    - url: 文件缺失或为空 → ""（必须由用户显式填写）
    - model: 同上 → ""
    - provider / agent_id: 是描述性元数据，可保留 fallback

    业务调用方（call_llm / test_llm_config）必须先判 cfg.get("url") 是否为空，
    缺失时立即返回 1001（参数校验错误），不允许静默打 localhost。
    """
    p = _config_file()
    if not p.is_file():
        return {
            "transport": DEFAULT_TRANSPORT,
            "provider": DEFAULT_PROVIDER,
            "url": "",
            "model": "",
            "api_key": "",
            "agent_id": DEFAULT_AGENT_ID,
            "cli_type": "",
            "cli_path": "",
            "cli_args": "",
            "cli_model": "",
            "cli_timeout_sec": DEFAULT_CLI_TIMEOUT_SEC,
            "garmin_region": _normalize_garmin_region(None),
            "coros_region": _normalize_coros_region(None),
        }
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    return {
        "transport": _normalize_transport(data.get("transport")),
        "provider": str(data.get("provider") or DEFAULT_PROVIDER),
        "url": str(data.get("url") or "").strip(),
        "model": str(data.get("model") or "").strip(),
        "api_key": str(data.get("api_key") or ""),
        "agent_id": str(data.get("agent_id") or DEFAULT_AGENT_ID).strip(),
        "cli_type": _normalize_cli_type(data.get("cli_type")),
        "cli_path": str(data.get("cli_path") or "").strip(),
        "cli_args": str(data.get("cli_args") or "").strip(),
        "cli_model": str(data.get("cli_model") or "").strip(),
        "cli_timeout_sec": _normalize_cli_timeout(data.get("cli_timeout_sec")),
        "watch_brand": str(data.get("watch_brand") or "").strip(),
        "garmin_region": _normalize_garmin_region(data.get("garmin_region")),
        "coros_region": _normalize_coros_region(data.get("coros_region")),
        "local_dir": str(data.get("local_dir") or "").strip(),
        "ai_notified": bool(data.get("ai_notified", False)),
        "ai_notified_hash": str(data.get("ai_notified_hash") or "").strip(),
    }


def _normalize_transport(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in VALID_TRANSPORTS else DEFAULT_TRANSPORT


def _normalize_cli_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in VALID_CLI_TYPES else ""


def _normalize_cli_timeout(value: Any) -> int:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return DEFAULT_CLI_TIMEOUT_SEC
    return max(5, min(seconds, 1800))


def _normalize_garmin_region(value: Any) -> str:
    text = str(value or os.environ.get("GARMIN_REGION") or "cn").strip().lower()
    return text if text in VALID_GARMIN_REGIONS else "cn"


def _normalize_coros_region(value: Any) -> str:
    text = str(value or os.environ.get("COROS_REGION") or "cn").strip().lower()
    return text if text in VALID_COROS_REGIONS else "cn"


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


def save_llm_config(
    provider: str,
    url: str,
    model: str,
    api_key: str,
    agent_id: str = "",
    watch_brand: str = "",
    local_dir: str = "",
    ai_notified: bool = False,
    ai_notified_hash: str = "",
    transport: str = DEFAULT_TRANSPORT,
    cli_type: str = "",
    cli_path: str = "",
    cli_args: str = "",
    cli_model: str = "",
    cli_timeout_sec: int = DEFAULT_CLI_TIMEOUT_SEC,
    garmin_region: str = "",
    coros_region: str = "",
) -> None:
    """持久化 LLM 配置。

    CONTRACT §2.1 / §7.2: 严格按调用方传入的 url / model 原样落盘。
    若调用方传入空字符串，表示用户未填写，必须原样保存空值，
    绝不允许在此处用 DEFAULT_URL / DEFAULT_MODEL 隐式回填，
    否则下游 load_llm_config 会再次误以为"已配置"。
    """
    cfg = {
        "transport": _normalize_transport(transport),
        "provider": (provider or DEFAULT_PROVIDER).strip(),
        "url": (url or "").strip(),
        "model": (model or "").strip(),
        "api_key": (api_key or "").strip(),
        "agent_id": (agent_id or "").strip(),
        "cli_type": _normalize_cli_type(cli_type),
        "cli_path": (cli_path or "").strip(),
        "cli_args": (cli_args or "").strip(),
        "cli_model": (cli_model or "").strip(),
        "cli_timeout_sec": _normalize_cli_timeout(cli_timeout_sec),
        "watch_brand": (watch_brand or "").strip(),
        "garmin_region": _normalize_garmin_region(garmin_region),
        "coros_region": _normalize_coros_region(coros_region),
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
    """将轨迹点转为 CSV，便于模型按表阅读。
    CONTRACT §4.5: snapshot 必须 token 可控。max_chars=50_000 约合 ~12.5K tokens。
    此函数仅作为历史兼容防御层，不应成为主要 AI 数据源。"""
    if not points:
        return "(无轨迹点数据)"

    preferred = ["lat", "lon", "alt", "time", "hr", "cadence"]

    columns: list[str] = []
    seen: set[str] = set()
    for row in points:
        if not isinstance(row, dict):
            continue
        for key in row.keys():
            key_text = str(key)
            if key_text not in seen:
                seen.add(key_text)
                columns.append(key_text)

    ordered_columns = [c for c in preferred if c in seen] + [c for c in columns if c not in preferred]

    def _csv_for_rows(rows: list[dict[str, Any]]) -> str:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=[""] + ordered_columns, extrasaction="ignore")
        writer.writeheader()
        for idx, row in enumerate(rows):
            payload = {c: row.get(c, "") if isinstance(row, dict) else "" for c in ordered_columns}
            payload[""] = idx
            writer.writerow(payload)
        return buf.getvalue()

    text = _csv_for_rows(points)
    if len(text) <= max_chars:
        return text
    n = len(points)
    step = max(2, int(math.ceil(len(text) / float(max_chars) * 1.15)))
    sampled = points[::step]
    return (
        f"【说明】原始轨迹共 {n} 行，为控制上下文长度已按步长 {step} 下采样后附表。\n\n"
        + _csv_for_rows(sampled)
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
    context_tags: dict[str, Any] | None = None,
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

    # === V4.0 AI 语境标签注入 (防幻觉) ===
    env_prompt = ""
    if context_tags and isinstance(context_tags, dict):
        env_prompt = "\n\n【⚠️ 系统级环境生理学约束（极其重要）】\n"
        env_prompt += "请在分析本场运动时，严格参考以下环境与设备因素。切勿将环境引起的自然生理代偿（如高心率）误判为用户的耐力不足：\n"
        for key, val in context_tags.items():
            env_prompt += f"- {key}: {val}\n"
        env_prompt += "注意：如果存在 Extreme 或 High 级别的热应激/高海拔缺氧，你的点评必须体现出对环境压力的宽容，切忌因为心率漂移而过度批评用户。\n\n"

    return f"""{env_prompt}你是一位{role}与 AI 户外领队。用户活动类型：【{sport_cn}】。
当前轨迹文件：{track_filename}
{mcp_note}
{snapshot}
【高密度轨迹明细表】
以下为 CSV（含 lat、lon、alt、time、hr、cadence 等列，索引为点序号）：
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
    context_tags: dict[str, Any] | None = None,
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
        context_tags=context_tags,
    )
    report_instruction = ""
    if report_json:
        report_instruction = f"""

【系统隐藏设定】以下是系统基于核心算法自动为您生成的路线深度分析报告 JSON 原稿。用户在 UI 面板上可以看到路线概览、运动数据快照、坡度起伏和活动建议入口。在接下来的对话中，请严格以此报告的数据作为你的'长期记忆'和'回答基准'。如果用户询问补给、装备、天气或体力安排，应优先基于活动建议专用 route facts 谨慎回答，绝不允许在后续对话中给出与此 JSON 矛盾的数据或建议。

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
    return _chat_completions_http(
        url=url,
        api_key=api_key,
        model=model,
        messages=messages,
        session_id=session_id,
        agent_id=agent_id,
        timeout=timeout,
    )


def generate_text(
    *,
    config: dict[str, Any],
    messages: list[dict[str, str]],
    session_id: str,
    timeout: int = 300,
) -> str:
    """Generate text via the configured transport.

    This is the single entry point for AI text generation. CLI mode is handled
    as a first-class transport and never falls back to HTTP implicitly.
    """
    cfg = config if isinstance(config, dict) else {}
    transport = _normalize_transport(cfg.get("transport"))
    if transport == "cli":
        return _run_cli_completion(
            config=cfg,
            messages=messages,
            session_id=session_id,
            timeout=timeout,
        )
    return _chat_completions_http(
        url=str(cfg.get("url") or "").strip(),
        api_key=str(cfg.get("api_key") or ""),
        model=str(cfg.get("model") or "").strip(),
        messages=messages,
        session_id=session_id,
        agent_id=str(cfg.get("agent_id") or "").strip(),
        timeout=timeout,
    )


def serialize_messages_for_cli(messages: list[dict[str, str]]) -> str:
    """Serialize chat messages into one prompt while preserving role boundaries."""
    blocks: list[str] = []
    for idx, msg in enumerate(messages or []):
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "user").strip().lower() or "user"
        if role not in {"system", "user", "assistant"}:
            role = "user"
        content = str(msg.get("content") or "").strip()
        if not content:
            continue
        blocks.append(f"[{role.upper()}]\n{content}")
    return "\n\n".join(blocks).strip()


def _split_cli_args(args_text: str) -> list[str]:
    text = str(args_text or "").strip()
    if not text:
        return []
    try:
        return shlex.split(text)
    except ValueError as exc:
        raise RuntimeError(f"CLI 参数解析失败: {exc}") from exc


def _validate_cli_executable_path(cli_path: str) -> str:
    path = str(cli_path or "").strip()
    if not path:
        return ""
    try:
        parts = shlex.split(path)
    except ValueError:
        parts = [path]
    if len(parts) > 1 and any(part.startswith("-") or part in {"exec", "agent", "-p"} for part in parts[1:]):
        raise RuntimeError("CLI 路径只能填写可执行文件路径，参数请填写到 CLI 参数模板")
    return path


def _expand_cli_template(args: list[str], *, prompt: str, model: str) -> list[str]:
    return [
        str(part).replace("{prompt}", prompt).replace("{model}", model)
        for part in args
    ]


def _ensure_prompt_placeholder(args: list[str]) -> list[str]:
    normalized = [str(part) for part in args]
    if any("{prompt}" in part for part in normalized):
        return normalized
    return normalized + ["{prompt}"]


def _build_cli_command(config: dict[str, Any], prompt: str) -> list[str]:
    cli_type = _normalize_cli_type(config.get("cli_type"))
    cli_path = _validate_cli_executable_path(str(config.get("cli_path") or ""))
    model = str(config.get("cli_model") or config.get("model") or "").strip()
    if cli_type == "codex":
        base = [cli_path or "codex", "exec", "{prompt}"]
    elif cli_type == "claude":
        base = [cli_path or "claude", "-p", "{prompt}"]
    elif cli_type == "openclaw":
        agent_id = str(config.get("agent_id") or "").strip() or "main"
        cli_timeout = str(_normalize_cli_timeout(config.get("cli_timeout_sec")))
        base = [
            cli_path or _default_openclaw_cli_path() or "openclaw",
            "agent",
            "--agent",
            agent_id,
            "--timeout",
            cli_timeout,
            "--json",
            "--message",
            "{prompt}",
        ]
    elif cli_type == "custom":
        if not cli_path:
            raise RuntimeError("自定义 CLI 路径未配置")
        custom_args = _split_cli_args(str(config.get("cli_args") or ""))
        base = [cli_path] + _ensure_prompt_placeholder(custom_args)
    else:
        raise RuntimeError("CLI 类型未配置")
    return _expand_cli_template(base, prompt=prompt, model=model)


def _default_openclaw_cli_path() -> str:
    qclaw_wrapper = Path.home() / "Library/Application Support/QClaw/openclaw/config/bin/openclaw"
    if qclaw_wrapper.is_file():
        return str(qclaw_wrapper)
    return ""


def _cli_not_found_message(cli_type: str) -> str:
    clean = _normalize_cli_type(cli_type)
    if clean == "openclaw":
        return "未找到 OpenClaw CLI，请确认 QClaw 已安装或填写 CLI 路径"
    if clean == "codex":
        return "未找到 Codex CLI，请确认已安装或填写 CLI 路径"
    if clean == "claude":
        return "未找到 Claude CLI，请确认已安装或填写 CLI 路径"
    return "未找到自定义 CLI，请确认 CLI 路径填写正确"


def _is_cli_not_found_error(exc: OSError) -> bool:
    return isinstance(exc, FileNotFoundError) or getattr(exc, "errno", None) == errno.ENOENT


def _is_openclaw_agent_unusable_detail(detail: str) -> bool:
    text = str(detail or "").lower()
    if not text:
        return False
    if "no target session selected" in text:
        return True
    if "agent" in text and any(token in text for token in ("not found", "not exist", "missing", "unavailable", "invalid")):
        return True
    return "agent 不存在" in text or "agent不可用" in text or "agent 不可用" in text


def _build_openclaw_cli_env(config: dict[str, Any], executable: str) -> dict[str, str] | None:
    if _normalize_cli_type(config.get("cli_type")) != "openclaw":
        return None

    env = os.environ.copy()
    changed = False
    if not env.get("QCLAW_CLI_NODE_BINARY"):
        qclaw_node = Path("/Applications/QClaw.app/Contents/Resources/node/node")
        codex_node = Path("/Applications/Codex.app/Contents/Resources/cua_node/bin/node")
        if qclaw_node.is_file():
            env["QCLAW_CLI_NODE_BINARY"] = str(qclaw_node)
            changed = True
        elif codex_node.is_file():
            env["QCLAW_CLI_NODE_BINARY"] = str(codex_node)
            changed = True

    if not env.get("QCLAW_CLI_OPENCLAW_MJS"):
        openclaw_mjs = Path.home() / "Library/Application Support/QClaw/openclaw/node_modules/openclaw/openclaw.mjs"
        if openclaw_mjs.is_file():
            env["QCLAW_CLI_OPENCLAW_MJS"] = str(openclaw_mjs)
            changed = True

    for key, value in _read_qclaw_launchagent_env().items():
        if key in QCLAW_LAUNCHAGENT_ENV_KEYS and value and not env.get(key):
            env[key] = value
            changed = True

    if not env.get("OPENCLAW_STATE_DIR"):
        qclaw_state_dir = Path.home() / ".qclaw"
        if qclaw_state_dir.is_dir():
            env["OPENCLAW_STATE_DIR"] = str(qclaw_state_dir)
            changed = True

    if not env.get("OPENCLAW_CONFIG_PATH"):
        qclaw_config_path = Path.home() / ".qclaw/openclaw.json"
        if qclaw_config_path.is_file():
            env["OPENCLAW_CONFIG_PATH"] = str(qclaw_config_path)
            changed = True

    if changed:
        return env
    return None


def _read_qclaw_launchagent_env() -> dict[str, str]:
    plist_path = Path.home() / "Library/LaunchAgents/ai.openclaw.gateway.plist"
    try:
        with plist_path.open("rb") as f:
            data = plistlib.load(f)
    except (OSError, plistlib.InvalidFileException, ValueError):
        return {}
    raw_env = data.get("EnvironmentVariables") if isinstance(data, dict) else None
    if not isinstance(raw_env, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in raw_env.items()
        if key is not None and value is not None
    }


def _parse_last_json_object(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    for idx, char in enumerate(raw):
        if char != "{":
            continue
        try:
            parsed = json.loads(raw[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _extract_openclaw_agent_text(output: str) -> str:
    def find_text(value: Any) -> str:
        if isinstance(value, dict):
            for key in ("finalAssistantVisibleText", "finalAssistantRawText", "text", "content"):
                text = value.get(key)
                if isinstance(text, str) and text.strip():
                    return text.strip()
            for child in value.values():
                found = find_text(child)
                if found:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = find_text(item)
                if found:
                    return found
        return ""

    parsed = _parse_last_json_object(output)
    if not parsed:
        return str(output or "").strip()
    return find_text(parsed) or str(output or "").strip()


def _run_openclaw_readonly_json(config: dict[str, Any], args: list[str], timeout: int) -> tuple[dict[str, Any] | None, str]:
    cli_path = _validate_cli_executable_path(str(config.get("cli_path") or ""))
    cmd = [cli_path or "openclaw"] + args
    cli_env = _build_openclaw_cli_env(config, cmd[0])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_normalize_cli_timeout(timeout),
            shell=False,
            env=cli_env,
        )
    except Exception as exc:
        return None, str(exc)

    parsed = _parse_last_json_object(result.stdout)
    if parsed is not None:
        return parsed, ""
    detail = _error_snippet(str(result.stderr or result.stdout or "").strip())
    if result.returncode != 0:
        return None, f"exit {result.returncode}: {detail}" if detail else f"exit {result.returncode}"
    return None, detail


def _extract_ws_port(value: Any) -> str:
    match = re.search(r":(\d+)(?:/|$)", str(value or ""))
    return match.group(1) if match else ""


def _extract_gateway_exec_port(value: Any) -> str:
    match = re.search(r"(?:^|\s)--port\s+(\d+)(?:\s|$)", str(value or ""))
    return match.group(1) if match else ""


def diagnose_openclaw_cli(config: dict[str, Any], timeout: int = 15) -> str:
    if _normalize_cli_type((config or {}).get("cli_type")) != "openclaw":
        return ""

    status, status_error = _run_openclaw_readonly_json(config, ["status", "--json"], timeout)
    if status:
        gateway = status.get("gateway") if isinstance(status.get("gateway"), dict) else {}
        service = status.get("gatewayService") if isinstance(status.get("gatewayService"), dict) else {}
        if gateway.get("reachable") is False:
            url = str(gateway.get("url") or "")
            runtime_short = str(service.get("runtimeShort") or "")
            layout = service.get("layout") if isinstance(service.get("layout"), dict) else {}
            exec_start = str(layout.get("execStart") or "")
            configured_port = _extract_ws_port(url)
            exec_port = _extract_gateway_exec_port(exec_start)
            parts = ["OpenClaw Gateway 当前不可达"]
            if url:
                parts.append(f"配置 URL：{url}")
            if runtime_short:
                parts.append(f"服务状态：{runtime_short}")
            if exec_start:
                parts.append(f"启动参数：{exec_start}")
            if configured_port and exec_port and configured_port != exec_port:
                parts.append(f"检测到端口不一致：配置为 {configured_port}，但服务启动参数为 {exec_port}")
            return "；".join(parts)

    models, models_error = _run_openclaw_readonly_json(config, ["models", "status", "--json"], timeout)
    if models:
        auth = models.get("auth") if isinstance(models.get("auth"), dict) else {}
        missing = auth.get("missingProvidersInUse") if isinstance(auth.get("missingProvidersInUse"), list) else []
        routes = auth.get("runtimeAuthRoutes") if isinstance(auth.get("runtimeAuthRoutes"), list) else []
        missing_routes = [
            str(route.get("provider") or route.get("authProvider") or "").strip()
            for route in routes
            if isinstance(route, dict) and str(route.get("status") or "").strip().lower() == "missing"
        ]
        providers = sorted({item for item in [*(str(x) for x in missing), *missing_routes] if item})
        if providers:
            default_model = str(models.get("defaultModel") or models.get("resolvedDefault") or "").strip()
            parts = [f"OpenClaw 模型授权缺失：{', '.join(providers)}"]
            if default_model:
                parts.append(f"默认模型：{default_model}")
            parts.append("请在 OpenClaw/QClaw 中完成模型授权或切换可用模型")
            return "；".join(parts)

    if status_error:
        return f"OpenClaw 状态诊断失败：{status_error}"
    if models_error:
        return f"OpenClaw 模型诊断失败：{models_error}"
    return ""


def _error_snippet(value: str) -> str:
    text = str(value or "").strip()
    if len(text) <= CLI_ERROR_SNIPPET_CHARS:
        return text
    head_chars = CLI_ERROR_SNIPPET_CHARS // 2
    tail_chars = CLI_ERROR_SNIPPET_CHARS - head_chars
    return text[:head_chars] + "\n...\n" + text[-tail_chars:]


def _run_cli_completion(
    *,
    config: dict[str, Any],
    messages: list[dict[str, str]],
    session_id: str,
    timeout: int = 300,
) -> str:
    prompt = serialize_messages_for_cli(messages)
    if not prompt:
        raise RuntimeError("CLI prompt 为空")
    cmd = _build_cli_command(config, prompt)
    effective_timeout = _normalize_cli_timeout(config.get("cli_timeout_sec") or timeout)
    cli_env = _build_openclaw_cli_env(config, cmd[0] if cmd else "")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            shell=False,
            env=cli_env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"CLI 已启动但模型未在超时时间内返回 ({effective_timeout}s)") from exc
    except OSError as exc:
        if _is_cli_not_found_error(exc):
            raise RuntimeError(_cli_not_found_message(str(config.get("cli_type") or ""))) from exc
        raise RuntimeError(f"CLI 启动失败: {exc}") from exc

    stdout = str(result.stdout or "").strip()
    stderr = str(result.stderr or "").strip()
    if result.returncode != 0:
        detail = _error_snippet(stderr or stdout)
        if _normalize_cli_type(config.get("cli_type")) == "openclaw" and _is_openclaw_agent_unusable_detail(detail):
            raise RuntimeError("OpenClaw Agent 不存在或不可用，请检查 Agent ID")
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"CLI 调用失败 (exit {result.returncode}){suffix}")
    if not stdout:
        raise RuntimeError("模型未返回内容")
    if _normalize_cli_type(config.get("cli_type")) == "openclaw":
        return _extract_openclaw_agent_text(stdout)
    return stdout


def _chat_completions_http(
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

    # §OpenClaw 路由契约：默认 model + 有效 agent_id 时，强制把 model 拼成
    # openclaw/agent-{id}，让 OpenClaw 网关正确路由；用户填了非默认 model 时不覆盖。
    # agent_id 完全来自用户配置，不写死具体值。
    clean_agent_id = str(agent_id).strip() if agent_id else ""
    body_model = model
    if clean_agent_id:
        agent_token = clean_agent_id
        if not agent_token.startswith("agent-"):
            agent_token = "agent-" + agent_token
        # 仅在 model 是默认 'openclaw' 时才补齐，避免覆盖用户的自定义 model
        if str(model).strip() == "openclaw":
            body_model = "openclaw/" + agent_token

    body: dict[str, Any] = {
        "model": body_model,
        "messages": messages,
        "temperature": 0.7,
        "stream": False,
        "session_id": session_id,
        "chat_id": session_id,
        "user": session_id,
    }
    if clean_agent_id:
        body["agent_id"] = clean_agent_id
        body["agentId"] = clean_agent_id
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


ACTIVITY_ADVICE_OUTPUT_SCHEMA = """{
  "supply_advice": {"status": "提示|注意|重点关注", "basis": "依据哪些路线事实或用户输入", "advice": "补给建议"},
  "weather_check": {"status": "信息不足|提示|注意|重点关注", "basis": "是否有计划活动时间；没有则明确说明信息不足", "advice": "天气检查建议"},
  "equipment_advice": {"status": "提示|注意|重点关注", "basis": "依据海拔、爬升、坡度、路线环境等", "advice": "装备建议"},
  "physical_plan": {"status": "提示|注意|重点关注", "basis": "依据距离、爬升、坡度、预计耗时等", "advice": "体力安排建议"},
  "disclaimer": "以上建议由 AI 基于当前轨迹和用户填写的计划信息生成，仅供出行准备参考。"
}"""


def _activity_advice_planning_context(planning_context: dict[str, Any] | None = None) -> dict[str, str]:
    ctx = planning_context if isinstance(planning_context, dict) else {}
    user_activity_type = str(ctx.get("user_activity_type") or "").strip()
    planned_start_time = str(ctx.get("planned_start_time") or "").strip()
    return {
        "user_activity_type": user_activity_type,
        "planned_start_time": planned_start_time,
        "activity_type_source": "user_input" if user_activity_type else "missing",
        "planned_time_source": "user_input" if planned_start_time else "missing",
    }


def _activity_advice_payload(snapshot: dict[str, Any] | None, planning_context: dict[str, Any] | None = None) -> str:
    allowed_keys = (
        "activity_id", "distance_km", "distance_display", "duration_sec",
        "elevation_gain_m", "total_descent_m", "max_alt_m", "min_alt_m",
        "avg_grade_pct", "max_slope_pct", "min_slope_pct", "uphill_pct",
        "downhill_pct", "up_count", "down_count", "max_single_climb_m",
        "difficulty_score", "region", "start_lat", "start_lon", "source",
    )
    route_facts: dict[str, Any] = {}
    if isinstance(snapshot, dict):
        route_facts = {key: snapshot.get(key) for key in allowed_keys if key in snapshot}
    return json.dumps(
        {
            "route_facts": route_facts,
            "planning_context": _activity_advice_planning_context(planning_context),
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def build_activity_advice_system_prompt(
    snapshot: dict[str, Any] | None,
    planning_context: dict[str, Any] | None = None,
) -> str:
    payload = _activity_advice_payload(snapshot, planning_context)
    return f"""你是一位专业户外活动准备顾问，只负责基于系统提供的路线事实和用户显式填写的计划信息生成活动建议。

【数据边界 — DATA BOUNDARY（不可逾越）】
以下 JSON 是本功能唯一可用输入。route_facts 来自后端路线事实白名单；planning_context 只来自用户显式填写。你只允许解释和建议，禁止生成或修改事实字段。

【当前活动建议输入】
{payload}

【建议维度】
你必须从以下四个维度生成活动建议：
1. 补给建议：水、能量、电解质、补给节奏
2. 天气检查：出发前需要核对的温度、降雨、风、雷暴、昼夜温差等事项
3. 装备建议：防晒、防雨、保暖、照明、急救、防滑、路线装备
4. 体力安排：爬升压力、距离压力、节奏控制、休息安排

【强制禁止行为】
你 MUST NOT：
- 使用历史 start_time 或 start_time_utc 推断计划天气
- 使用历史天气、weather_json、weather_context 或 _track_weather
- 使用前端 points[]、placemarks[]、DOM 文本或 UI fallback
- 使用 shadow_diff、shadow_diff_json、diff
- 重新计算距离、爬升、坡度或重建 per-point 数据
- 给出医学诊断、安全保证或确定性天气预报
- 生成任何 canonical 指标或写回字段建议
- 输出 markdown 代码块

【天气检查规则】
如果 planning_context.planned_start_time 为空或 planned_time_source 为 "missing"，weather_check 必须说明缺少计划活动时间，只能给出出发前天气检查清单，不得判断具体天气。

【输出格式 — 严格 JSON】
只输出一个合法 JSON 对象，格式必须为：
{ACTIVITY_ADVICE_OUTPUT_SCHEMA}

【状态约束】
status 只能使用 "信息不足"、"提示"、"注意"、"重点关注" 四个值；"信息不足" 优先用于天气时间缺失或整体数据不足场景。
"""


def build_activity_advice_user_prompt() -> str:
    return "请基于系统指令中的路线事实和用户计划上下文生成活动建议 JSON。只输出纯 JSON，不要输出 markdown 标记，不要补充额外解释。"


def empty_activity_advice(error: str = "") -> dict[str, Any]:
    default_basis = "当前路线事实或用户计划信息不足。"
    default_advice = "建议结合实际路线、个人状态和出发前最新信息谨慎准备。"
    return {
        "supply_advice": {"status": "提示", "basis": default_basis, "advice": default_advice},
        "weather_check": {
            "status": "信息不足",
            "basis": "缺少用户显式填写的计划活动时间，无法判断具体天气。",
            "advice": "请在出发前检查温度、降雨、风速、雷暴预警和昼夜温差。",
        },
        "equipment_advice": {"status": "提示", "basis": default_basis, "advice": default_advice},
        "physical_plan": {"status": "提示", "basis": default_basis, "advice": default_advice},
        "disclaimer": "以上建议由 AI 基于当前轨迹和用户填写的计划信息生成，仅供出行准备参考。",
        "error": str(error or ""),
    }


def _normalize_activity_advice_status(status: Any, default: str = "提示") -> str:
    text = str(status or "").strip()
    return text if text in {"信息不足", "提示", "注意", "重点关注"} else default


def _normalize_activity_advice_item(value: Any, default_status: str = "提示") -> dict[str, str]:
    default = "当前数据不足，建议结合实际路线和个人状态谨慎准备。"
    if not isinstance(value, dict):
        value = {}
    return {
        "status": _normalize_activity_advice_status(value.get("status"), default_status),
        "basis": str(value.get("basis") or "当前路线事实或用户计划信息不足。")[:500],
        "advice": str(value.get("advice") or default)[:500],
    }


def normalize_activity_advice_json(raw_text: str) -> dict[str, Any]:
    if not raw_text:
        return empty_activity_advice("LLM 未返回内容")

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
        return empty_activity_advice(f"JSON 解析失败: {text[:120]}")

    if not isinstance(data, dict):
        return empty_activity_advice("活动建议结果格式错误")

    schema = empty_activity_advice(str(data.get("error") or ""))
    schema["supply_advice"] = _normalize_activity_advice_item(data.get("supply_advice"))
    schema["weather_check"] = _normalize_activity_advice_item(data.get("weather_check"), "信息不足")
    schema["equipment_advice"] = _normalize_activity_advice_item(data.get("equipment_advice"))
    schema["physical_plan"] = _normalize_activity_advice_item(data.get("physical_plan"))
    schema["disclaimer"] = str(data.get("disclaimer") or schema["disclaimer"])[:500]
    return schema


RADAR_DIMENSION_INTERPRETATION: dict[str, str] = {
    "endurance": "耐力:基于 Banister 专业训练负荷 + 42 天 PMC 长期负荷(慢性训练负荷),并加入 28 天训练连续性。CTL 衰减模型保持不变,但评分阈值按运动类型区分:running/trail/treadmill 为 20/45/70,cycling/road/mtb 为 30/80/130,hiking/walking/mountaineering 为 10/25/45,unknown/swimming 沿用旧 30/80/150。最终分数=75% CTL 分 + 25% 连续性分;连续性按最近 28 天内 trimp>0 且时长≥10 分钟的训练日期去重。",
    "recovery": "恢复:基于个人恢复状态综合评分,优先使用近期 HRV / 个人 HRV 基线的相对变化,并结合 TSB/ATL 训练压力、平均睡眠、近期静息心率偏移。只有 HRV 基线而无近期趋势时不直接把 HRV 绝对值当分数,而是返回保守估计并标记 low confidence。",
    "stability": "心肺稳定:基于有氧解耦 Pa:Hr,但仅纳入稳定有氧活动样本;短课、间歇、停顿多、强爬坡/大起伏路线和异常 decoupling 会被过滤。90 天内取最近 5 条有效样本均值。decoupling<5%→95 分,5~10%→75 分,10~15%→55 分,≥15%→30 分。stability_confidence 由有效样本数决定:≥5 high,3~4 medium,0~2 low。",
    "threshold": "阈值:跑步沿用阈值心率(20 分钟滑动窗口 × 0.95 或画像阈值心率)与 max_hr 比值评分;骑行优先使用 FTP/20 分钟最佳功率 ×0.95,有体重时按 W/kg 评分,无体重按 W 评分且分数封顶,无功率时才降级为 threshold_hr/max_hr 且可信度较低。LLM 只能解释系统提供的 threshold_source / threshold_confidence,禁止重新计算。",
    "climbing": "爬升:VAM 是 Vertical Ascent Meters per hour,白话就是『每小时爬升速度』,由后端『有效爬坡段』算法计算(m/h = 有效段累计爬升 / 有效段时间 × 3600),经 90 天可信活动过滤(cycling / road_cycling / mountain_biking / running ≥ 20m@1km,trail_running ≥ 30m@1km,hiking ≥ 50m@1km)与 p90 聚合后得到。骑行爬升是复合评分:VAM 表现、爬坡规模、重复稳定性、数据质量共同决定,并受样本数量封顶。climbing_activity_count_90d 是90天该运动活动数,climbing_elevation_activity_count_90d 是有真实爬升且过门槛的活动数,climbing_sample_count 是真正生成 VAM 的连续有效爬坡样本数,三者不能混写。LLM 只能解释系统提供的 canonical snapshot,禁止重新计算或推断。",
    "anaerobic": "无氧爆发:跑步基于过滤下坡/GPS 突刺后的 30 秒速度;骑行优先基于 5/15/30/60 秒短时功率与 W/kg,无有效功率时才降级为速度 fallback。骑行 power_wkg 阈值:<5→20 分,5~7.5→50 分,7.5~10→75 分,≥10→95 分;power_w 或 speed_fallback 会降低可信度,其中速度 fallback 最高封顶 75 分。",
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
- VAM 必须用白话解释为"每小时爬升速度";首次提到 VAM 时写成"VAM(每小时爬升速度)",不要只写缩写。
- 爬升(VAM)阈值按 sport_type 分支:cycling/road_cycling/mountain_biking/running/trail_running 用 300/600/900 m/h,
  hiking/mountaineering 用 150/300/500 m/h。
- 若快照提供 climbing_activity_count_90d / climbing_elevation_activity_count_90d / climbing_sample_count,必须区分:
  · climbing_activity_count_90d = 90 天内该运动活动总数;
  · climbing_elevation_activity_count_90d = 其中有真实爬升且通过门槛的活动数;
  · climbing_sample_count = 生成 VAM 的连续有效爬坡样本数。
- 不得把 climbing_sample_count 直接说成"骑行活动数";若三者差异较大,必须解释"很多活动有累计爬升,但只有少数识别出连续有效爬坡段并生成 VAM"。
- 解读爬升维度时:
  · 必须同时说明 vam 数值和 climbing_confidence。
  · 若 source == "cycling_climb_composite",必须优先引用后端 reason,尤其是 score_cap 与样本封顶原因。
  · 若 climbing_confidence == "low",必须说明"有效爬坡样本偏少,分数不代表长期稳定爬坡能力"。
  · 不得跨运动类比("您比跑步用户的爬升差"——评分体系与运动场景不同)。

【可信度解释契约 — confidence / source / sample_count】
- radar.dimensions 中的 confidence / source / sample_count / reason 是后端权威解释上下文,只能引用,禁止自行补算或改写来源。
- 若任一维度 confidence == "low",对应 comment 必须提醒"样本不足或数据来源较弱,分数仅供参考"。
- 若 source 属于 fallback / legacy / speed_fallback / threshold_hr / no_valid_trimp,必须说明该维度不是最优数据源或当前数据基础较弱。
- sample_count 缺失或为 null 时,不得伪造样本数;只能写"样本数未提供"或不写样本数。
- 维度分数、confidence、source、sample_count 之间如有张力,优先解释可信度和来源,不要把 score 单独解读成长期稳定能力。

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
- 自行生成或修改 confidence / source / sample_count
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


# =============================================================================
# V6.3 复盘覆盖层 AI 洞察 — 独立 sentinel
# 契约:fit-arch-contrac §5.4 规则 1(独立 sentinel)/ §5.6.2 规则 7(empty_xxx)
# =============================================================================

FATIGUE_REVIEW_DIMENSION_ORDER = [
    "overall_stability",
    "fatigue_progression",
    "risk_triggers",
    "context_impact",
]

FATIGUE_REVIEW_DIMENSION_LABELS = {
    "overall_stability": "全程稳定性",
    "fatigue_progression": "疲劳阶段",
    "risk_triggers": "风险触发",
    "context_impact": "外部影响",
}

FATIGUE_REVIEW_DIMENSION_LEGACY_KEY_MAP = {
    "stability": "overall_stability",
    "endurance": "fatigue_progression",
    "bonk_risk": "risk_triggers",
    "environment": "context_impact",
}

FATIGUE_REVIEW_DIMENSION_LEVELS = {"excellent", "good", "warn", "bad", "unknown"}
FATIGUE_REVIEW_LEVEL_LABELS = {
    "excellent": "极佳",
    "good": "良好",
    "warn": "需关注",
    "bad": "风险较高",
    "unknown": "数据不足",
}


def _localize_fatigue_review_ai_text(value: Any) -> str:
    """把用户可见的复盘 AI 文案收敛为中文产品语言。"""
    text = str(value or "")
    if not text:
        return ""
    replacements = [
        (r"\bBONK_WARNING\b", "能量断档风险线索"),
        (r"\bBonk\b", "能量断档"),
        (r"\bbonk\b", "能量断档"),
        (r"Bonk风险", "能量断档风险"),
        (r"bonk_risk", "能量断档风险"),
        (r"\brisk window\b", "风险区间"),
        (r"\bwarning\b", "预警"),
        (r"\bcollapse_events\b", "状态下滑事件"),
        (r"\bcollapse event(s)?\b", "状态下滑事件"),
        (r"\bcollapse\b", "状态下滑"),
        (r"\bdeclining\b", "下降"),
        (r"\bcaution\b", "需谨慎"),
        (r"\bexcellent\b", "极佳"),
        (r"\bgood\b", "良好"),
        (r"\bwarn\b", "需关注"),
        (r"\bbad\b", "风险较高"),
        (r"\bunknown\b", "数据不足"),
        (r"\bstable\b", "稳定"),
        (r"\bmoderate\b", "中等"),
        (r"\bmedium\b", "中等"),
        (r"\blow\b", "低"),
        (r"\bhigh\b", "高"),
        (r"\bvery_high\b", "很高"),
        (r"\bHRR\b", "心率储备占用"),
        (r"\bHR\b", "心率"),
        (r"\bCV\b", "变异系数"),
        (r"\bEI\b", "效率指标"),
        (r"\bkcal\b", "千卡"),
        (r"\bZ([1-5])\b", r"第 \1 心率区间"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def _empty_fatigue_review_dimensions() -> list[dict[str, str]]:
    return [
        {
            "key": key,
            "label": FATIGUE_REVIEW_DIMENSION_LABELS[key],
            "level": "unknown",
            "comment": "暂无足够数据",
        }
        for key in FATIGUE_REVIEW_DIMENSION_ORDER
    ]


FATIGUE_REVIEW_OUTPUT_SCHEMA = """{
  "summary": "120 字以内的中文总评,聚焦本次训练的核心结论(全程稳定性 / 疲劳阶段 / 风险触发 / 外部影响)",
  "sport_type": "running|trail_running|hiking|cycling|swimming",
  "key_dimensions": [
    {
      "key": "overall_stability|fatigue_progression|risk_triggers|context_impact",
      "label": "中文维度名(全程稳定性|疲劳阶段|风险触发|外部影响)",
      "level": "excellent|good|warn|bad|unknown",
      "comment": "30-80 字自然中文解释,不得直接输出英文枚举或原始字段名"
    }
  ],
  "event_interpretation": "针对状态下滑事件的整体中文解读(哪些是真正的风险点,哪些是环境干扰)",
  "training_advice": "针对本场训练的具体改进建议,120 字以内,避免空话",
  "disclaimer": "AI 生成仅供参考,数据基于单次训练快照,需结合长期趋势"
}"""


def empty_fatigue_review_insight(error: str = "") -> dict[str, Any]:
    """V6.3 复盘覆盖层空态:LLM 失败/无数据/降级时使用。§5.6.2 规则 7 强制约束。"""
    return {
        "summary": error or "暂无可解读的复盘数据",
        "sport_type": "",
        "key_dimensions": _empty_fatigue_review_dimensions(),
        "event_interpretation": "",
        "training_advice": "请先完成数据加载后再生成 AI 洞察",
        "disclaimer": "AI 生成仅供参考 · 数据来源：FIT 解析 + 后端算法",
        "error": str(error or ""),
    }


def normalize_fatigue_review_json(raw_text: str) -> dict[str, Any]:
    """V6.3 复盘覆盖层 JSON 标准化:失败时返回 empty_fatigue_review_insight。"""
    if not raw_text:
        return empty_fatigue_review_insight("LLM 未返回内容")
    text = raw_text.strip()

    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return empty_fatigue_review_insight(f"JSON 解析失败: {text[:120]}")

    if not isinstance(data, dict):
        return empty_fatigue_review_insight("洞察结果格式错误")

    schema = empty_fatigue_review_insight()
    schema["summary"] = _localize_fatigue_review_ai_text(data.get("summary") or schema["summary"])[:300]
    schema["sport_type"] = str(data.get("sport_type") or schema["sport_type"])
    schema["event_interpretation"] = _localize_fatigue_review_ai_text(data.get("event_interpretation") or "")[:500]
    schema["training_advice"] = _localize_fatigue_review_ai_text(data.get("training_advice") or schema["training_advice"])[:500]
    schema["disclaimer"] = _localize_fatigue_review_ai_text(data.get("disclaimer") or schema["disclaimer"])[:300]

    raw_dims = data.get("key_dimensions") or []
    by_key: dict[str, dict[str, str]] = {}
    if isinstance(raw_dims, list):
        for d in raw_dims:
            if not isinstance(d, dict):
                continue
            raw_key = str(d.get("key") or "").strip()
            normalized_key = FATIGUE_REVIEW_DIMENSION_LEGACY_KEY_MAP.get(raw_key, raw_key)
            if normalized_key not in FATIGUE_REVIEW_DIMENSION_LABELS or normalized_key in by_key:
                continue
            level = str(d.get("level") or "unknown").strip().lower()
            if level not in FATIGUE_REVIEW_DIMENSION_LEVELS:
                level = "unknown"
            by_key[normalized_key] = {
                "key": normalized_key,
                "label": FATIGUE_REVIEW_DIMENSION_LABELS[normalized_key],
                "level": level,
                "comment": _localize_fatigue_review_ai_text(d.get("comment") or "")[:200],
            }
    schema["key_dimensions"] = [
        by_key.get(key, {
            "key": key,
            "label": FATIGUE_REVIEW_DIMENSION_LABELS[key],
            "level": "unknown",
            "comment": "暂无足够数据",
        })
        for key in FATIGUE_REVIEW_DIMENSION_ORDER
    ]

    return schema


def build_fatigue_review_messages(
    snapshot: dict[str, Any],
    sport_type: str,
    sport_cn: str,
) -> list[dict[str, str]]:
    """V6.3 复盘覆盖层 LLM messages 构造器。

    契约:§5.4 规则 3 — 后端从 _ai_snapshot 构建 prompt,前端不参与。
    """
    payload = json.dumps(snapshot or {}, ensure_ascii=False, indent=2, default=str)
    sport_mode_map = {
        "running": "running", "trail_running": "running", "treadmill_running": "running",
        "hiking": "general", "mountaineering": "general",
        "cycling": "cycling", "road_cycling": "cycling", "mountain_biking": "cycling",
        "swimming": "swimming", "lap_swimming": "swimming", "open_water": "swimming",
    }
    mode = sport_mode_map.get(sport_type, "general")

    system = f"""你是一位资深运动表现分析师与训练科学专家,专长于{sport_cn}单次训练复盘分析。

【数据边界 — DATA BOUNDARY(不可逾越)】
以下数据由脉图系统从 SQLite canonical DB / 复盘后端引擎(V4.0)/ MetricsResolver 预计算,**绝对权威**。你只允许解释(interpret),禁止任何形式的重新推导、估算、推断。

【当前功能区权威快照 — 单次训练复盘】
```json
{payload}
```

【运动专项约束(基于 {mode} 模式)】
本次活动唯一运动类型为: {sport_cn}({sport_type})。所有解释、措辞和场景判断必须服务于这个运动类型,不得因为地形、配速或历史上下文切换成其他运动。
- running:重点解读有氧解耦(decoupling)、心率漂移(PA:Hr)、Bonk 撞墙(累计 kcal > 1600 + 后半程效率骤降)
- cycling:优先解释功率输出、踏频组织、心率反应与地形/爬升关系;必须先看 summary.power_data_quality / summary.normalized_power(NP) / summary.avg_power / summary.power_points_count 或 curves_summary.power_points_count / summary.cadence_data_quality / summary.avg_cadence / curves_summary.has_power / curves_summary.has_cadence,再把心率、爬升、坡度、速度作为辅助事实。
- swimming:重点解读耐力持续性;Bonk 阈值与陆上有差异
- general:均衡解读 4 维度
若运动类型为 running / trail_running / treadmill_running,禁止出现"徒步"、"骑行"、"游泳"等跨运动称呼;地形导致的波动应写作跑步赛道、路况或路线变化。
若运动类型为 cycling / road_cycling / mountain_biking,必须遵守以下骑行专项边界:
- 若 snapshot 含 cycling_explanation_signals,骑行解释信号必须以该后端字段为唯一依据;只能解释 intensity_signal / aerobic_drift_signal / power_retention_signal / pacing_signal / cadence_signal 的 status、level、summary、evidence、reasons,不得从 summary / metrics / curves_summary / DOM / ECharts / points 自行构造或补算新的骑行解释信号。
- 对 status=unavailable 或 partial 的骑行解释信号必须温和降级,不得输出完整确定性结论;无 FTP 不得编造 FTP、IF、TSS、训练负荷或阈值强度,无功率不得输出功率强度、后程功率保持或 pacing 结论,无心率不得输出有氧漂移结论。
- 有功率:若 summary.power_data_quality == "available" 或 summary.power_available == true,可解释 normalized_power 与 avg_power 共同反映的输出强度和波动倾向,并结合心率、坡度、爬升说明功率输出与身体反应是否一致;不得自行计算 VI、FTP、IF、TSS、W/kg、功率区间或 FTP 推断。
- 无功率或功率质量不足:若 summary.power_data_quality 属于 missing / insufficient_points / invalid_values / length_mismatch / unavailable,必须说明缺少足够可用功率数据,功率相关判断置信度受限;只能基于心率、速度/车速、爬升、坡度、fatigue_zones、collapse_events 和环境背景做辅助复盘;不能输出完整功率复盘,不能写"功率稳定"、"后段功率下降"、"输出过猛"、"功率耐久不足"等缺少后端指标支撑的结论。
- 踏频可用:若 summary.cadence_data_quality == "available" 或 summary.cadence_available == true,avg_cadence 只能作为踩踏组织和输出稳定性的辅助证据;不得推断左右平衡、扭矩、齿比、低踏高扭矩或踏频衰减,除非 snapshot 明确提供。
- 踏频缺失或质量不足:若 summary.cadence_data_quality 属于 missing / insufficient_points / invalid_values / length_mismatch / unavailable,必须避免踏频稳定性、踏频衰减、踩踏效率等结论;可简短说明踏频数据不足,无法评估踩踏组织。
- 骑行不得把"配速"、"步频"、"跑姿"、"触地"、"步幅"、"跑步节奏"、"恢复跑"、"跑步赛道"作为核心解释框架;若需要描述速度,写"速度"或"车速",且说明速度受坡度、风、滑行、停顿和路况影响,不能替代功率判断训练输出。
- 骑行不得自行计算或推断 VI、FTP、IF、TSS、W/kg、左右平衡、扭矩或齿比;除非 snapshot 明确提供,否则这些维度必须视为不可用。
- 不得编造补给、天气、设备、路况等 snapshot 未提供的缺失事实;若 environment_context 或 context_tags 未提供依据,只能说明外部因素证据不足。

【必须输出维度】
key_dimensions 数组必须严格包含 overall_stability / fatigue_progression / risk_triggers / context_impact 四个维度(无数据时 comment 写"暂无足够数据"而非略过)。
- overall_stability / 全程稳定性:按运动类型解释整体稳定性;跑步解释心率、配速、效率、步频和节奏;骑行解释功率输出、心率反应、踏频组织、坡度/爬升背景下的节奏,无可用功率时必须说明稳定性判断受限;游泳/通用运动均衡解释心率、速度/节奏与环境背景。可指出波动发生在前段/中段/后段,但禁止重新计算。
- fatigue_progression / 疲劳阶段:解释 fatigue_zones 中疲劳是否出现、从哪里出现、是否持续或加重。
- risk_triggers / 风险触发:解释 bonk_risk、collapse_events、训练负荷或后端已识别事件中真正值得注意的风险线索。
- context_impact / 外部影响:同时参考 environment_context 的环境事实摘要与 context_tags 的压力标签。context_tags 表示已识别的影响因素/压力标签,environment_context 表示天气、温度、湿度、风速等事实。若 environment_context.has_weather=true 且 context_tags 为空,不得写"未提供环境标签数据"、"无法评估天气温度湿度"或同义表达,应说明"已有天气快照,但未识别到明显外部环境压力"。只有 environment_context.has_weather=false 且 context_tags 为空时,才允许表达环境数据不足。

【强行约束 — 绝对禁止行为】
你 MUST NOT:
- 重新计算距离、时间、配速/速度、心率、爬升、功率、踏频
- 还原或推断 per-point 曲线
- 重新计算有氧解耦率 / Bonk 风险
- 计算或推断 VI / FTP / IF / TSS / W/kg / 功率区间 / 左右平衡 / 扭矩 / 齿比
- 使用前端 DOM 推导值或 UI fallback 值
- 使用 shadow_diff / shadow_diff_json / diff / 任何 debug-only 字段
- 生成任何 canonical 指标或写回字段建议
- 跨运动类比或跨运动误称(例如把跑步写成徒步/骑行,把骑行写成跑步)
- 输出 markdown 代码块标记
- 凭空捏造事件或数值

【输出格式 — 严格 JSON】
只输出一个合法 JSON 对象,格式必须严格遵循:
{FATIGUE_REVIEW_OUTPUT_SCHEMA}

【铁律】
1. 只使用上方【权威快照】中的数值,禁止重新计算
2. key_dimensions 数组必须覆盖 4 维度
3. 输出必须是纯 JSON,不要包含 markdown 代码块标记
4. 所有数值字段必须填数字,文本字段必须是自然中文
5. event_interpretation 必须结合 context_tags 与 environment_context 中环境背景,体现宽容度
6. training_advice 必须针对本场数据,避免泛泛而谈
7. 用户可见文本不得直接输出 good / warn / bad / unknown / declining / caution / Bonk / collapse 等英文枚举、原始字段名或代码词；如需表达,请写成 良好 / 需关注 / 风险较高 / 数据不足 / 下降 / 需谨慎 / 能量断档 / 状态下滑
"""
    user = (
        f"请基于系统指令中提供的本次{sport_cn}单次训练复盘快照,"
        f"生成结构化 JSON 复盘解读。只输出纯 JSON,不要输出 markdown 标记,"
        f"不要补充额外解释,不要寒暄。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
