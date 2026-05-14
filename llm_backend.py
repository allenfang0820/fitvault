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


def _config_file() -> Path:
    """配置文件路径。
    打包后（sys.frozen）始终存放在用户主目录的隐藏文件夹中，
    确保分享 .app 程序时不会携带开发者的 API Key。
    """
    if getattr(sys, "frozen", False):
        # 打包模式：始终保存在用户主目录
        d = Path.home() / ".hiking_track_ai"
    else:
        # 开发模式：优先检查用户目录，没有则用项目本地（方便开发调试）
        home_d = Path.home() / ".hiking_track_ai"
        if (home_d / "llm_config.json").is_file():
            d = home_d
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
    }


def save_llm_config(provider: str, url: str, model: str, api_key: str) -> None:
    cfg = {
        "provider": (provider or DEFAULT_PROVIDER).strip(),
        "url": (url or DEFAULT_URL).strip(),
        "model": (model or DEFAULT_MODEL).strip(),
        "api_key": (api_key or "").strip(),
    }
    p = _config_file()
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def points_to_dataframe_csv(points: list[dict[str, Any]], max_chars: int = 420_000) -> str:
    """将轨迹点转为 pandas DataFrame 再输出 CSV，便于模型按表阅读。"""
    import pandas as pd

    if not points:
        return "(无轨迹点数据)"
    df = pd.DataFrame(points)
    preferred = ["dist", "lat", "lon", "alt", "time", "hr", "slope_pct"]
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
    if sport_type == "trail_running":
        return "越野跑", "顶级的越野跑教练"
    return "徒步", "资深的户外徒步领队"


def build_base_system_block(
    *,
    sport_type: str,
    provider: str,
    track_filename: str,
    points: list[dict[str, Any]],
    placemarks: list[dict[str, Any]],
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
    return f"""你是一位{role}与 AI 户外领队。用户活动类型：【{sport_cn}】。
当前轨迹文件：{track_filename}
{mcp_note}
【高密度轨迹明细表】
以下为 pandas 导出 CSV（含 dist 累计距离 km、lat、lon、alt、time、hr、slope_pct 等列，索引为点序号）：
```
{table}
```

【路点 / 打卡点 JSON】
```json
{wpts}
```

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
    )
    return (
        base
        + f"\n用户计划或已完成【{sport_cn}】。若问及地理位置，可根据经纬度推断；禁止保存文件。\n"
    )


def chat_completions(
    *,
    url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    session_id: str,
    timeout: int = 300,
) -> str:
    headers = {"Content-Type": "application/json"}
    if api_key and api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "stream": False,
        "session_id": session_id,
        "chat_id": session_id,
        "user": session_id,
    }
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
