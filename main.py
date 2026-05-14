#!/usr/bin/env python3
"""使用 pywebview 在桌面窗口中加载「徒步轨迹AI分析仪」单页 HTML。"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import llm_backend  # noqa: F401 -- PyInstaller bundles LLM 模块
import track_backend  # noqa: F401 -- PyInstaller bundles track_backend

HTML_FILENAME = "徒步轨迹AI分析仪-0514.html"


def app_base_dir() -> Path:
    """开发模式为脚本所在目录；PyInstaller 打包后为 _MEIPASS。"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def html_file() -> Path:
    path = app_base_dir() / HTML_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"未找到页面文件: {path}")
    return path


class Api:
    """pywebview js_api：轨迹文件、导出、大模型（OpenAI 兼容）等。"""

    REPORT_TERRAIN = "__REPORT_TERRAIN__"
    REPORT_PERSONALIZED = "__REPORT_PERSONALIZED__"

    def __init__(self) -> None:
        self._track_points: list | None = None
        self._track_placemarks: list | None = None
        self._track_filename: str = ""
        self._chat_messages: list[dict[str, str]] = []
        self._session_id = "session_" + uuid.uuid4().hex[:16]

    def on_loaded(self) -> None:
        """页面加载完成后显示窗口，解决白屏感。"""
        import webview
        if webview.windows:
            webview.windows[0].show()

    def _new_session_id(self) -> None:
        self._session_id = "session_" + uuid.uuid4().hex[:16]

    def sync_track_context(self, payload_json: str) -> dict:
        """前端完成渲染与 calculateStats 后同步轨迹（含 dist 等），供 call_llm 拼表。"""
        try:
            obj = json.loads(payload_json)
        except json.JSONDecodeError as e:
            return {"ok": False, "error": f"JSON 无效: {e}"}
        self._track_points = obj.get("points") or []
        self._track_placemarks = obj.get("placemarks") or []
        self._track_filename = str(obj.get("filename") or "轨迹")
        self._chat_messages = []
        self._new_session_id()
        return {"ok": True}

    def reset_llm_session(self) -> dict:
        self._chat_messages = []
        self._new_session_id()
        return {"ok": True}

    def get_llm_config(self) -> dict:
        cfg = llm_backend.load_llm_config()
        return {"ok": True, **cfg}

    def save_llm_config(self, provider: str, url: str, model: str, api_key: str) -> dict:
        try:
            llm_backend.save_llm_config(provider, url, model, api_key)
        except OSError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True}

    def call_llm(self, prompt: str, sport_type: str = "hiking") -> dict:
        """对话或路书：prompt 为普通用户文本，或魔法串 __REPORT_TERRAIN__ / __REPORT_PERSONALIZED__。"""
        cfg = llm_backend.load_llm_config()
        url = (cfg.get("url") or "").strip()
        if not url:
            return {"ok": False, "error": "API 接口地址为空，请在设置中配置"}

        provider = str(cfg.get("provider") or "local_mcp")
        model = str(cfg.get("model") or "openclaw").strip()
        api_key = str(cfg.get("api_key") or "")
        sid = self._session_id

        pts = self._track_points or []
        pms = self._track_placemarks or []
        fn = self._track_filename or "轨迹"

        try:
            if prompt == self.REPORT_TERRAIN:
                sys_b = llm_backend.build_base_system_block(
                    sport_type=sport_type,
                    provider=provider,
                    track_filename=fn,
                    points=pts,
                    placemarks=pms,
                )
                usr = llm_backend.build_report_user_prompt_terrain(sport_type)
                messages = [{"role": "system", "content": sys_b}, {"role": "user", "content": usr}]
                text = llm_backend.chat_completions(
                    url=url,
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    session_id=sid,
                )
                self._chat_messages = []
                self._new_session_id()
                return {"ok": True, "content": text}

            if prompt == self.REPORT_PERSONALIZED:
                sys_b = llm_backend.build_base_system_block(
                    sport_type=sport_type,
                    provider=provider,
                    track_filename=fn,
                    points=pts,
                    placemarks=pms,
                )
                usr = llm_backend.build_report_user_prompt_personalized(sport_type, provider)
                messages = [{"role": "system", "content": sys_b}, {"role": "user", "content": usr}]
                text = llm_backend.chat_completions(
                    url=url,
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    session_id=sid,
                )
                self._chat_messages = []
                self._new_session_id()
                return {"ok": True, "content": text}

            user_text = prompt
            if not self._chat_messages:
                sys_c = llm_backend.build_chat_system_block(
                    sport_type=sport_type,
                    provider=provider,
                    track_filename=fn,
                    points=pts,
                    placemarks=pms,
                )
                self._chat_messages = [{"role": "system", "content": sys_c}]
            self._chat_messages.append({"role": "user", "content": user_text})
            try:
                text = llm_backend.chat_completions(
                    url=url,
                    api_key=api_key,
                    model=model,
                    messages=list(self._chat_messages),
                    session_id=sid,
                )
            except Exception:
                if self._chat_messages and self._chat_messages[-1].get("role") == "user":
                    self._chat_messages.pop()
                raise
            self._chat_messages.append({"role": "assistant", "content": text})
            return {"ok": True, "content": text}

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def pick_and_parse_track(self) -> dict:
        import webview
        from webview import FileDialog

        from track_backend import parse_track_file

        if not webview.windows:
            return {"ok": False, "error": "窗口未就绪"}

        paths = webview.windows[0].create_file_dialog(
            FileDialog.OPEN,
            file_types=("Track files (*.fit;*.gpx;*.kml)",),
        )
        if not paths:
            return {"ok": False, "cancelled": True}

        src = paths[0] if isinstance(paths, (list, tuple)) else paths
        try:
            data = parse_track_file(src)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "filename": Path(src).name, "data": data}

    def parse_track_at_path(self, file_path: str) -> dict:
        from track_backend import parse_track_file

        try:
            data = parse_track_file(file_path)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "filename": Path(file_path).name, "data": data}

    def save_text_file(self, suggested_filename: str, content: str) -> dict:
        import webview
        from webview import FileDialog

        if not webview.windows:
            return {"ok": False, "error": "窗口未就绪"}

        win = webview.windows[0]
        suffix = Path(suggested_filename).suffix.lower()
        if suffix == ".gpx":
            file_types = ("GPX (*.gpx)",)
        elif suffix == ".kml":
            file_types = ("KML (*.kml)",)
        else:
            file_types = ("所有文件 (*.*)",)

        try:
            paths = win.create_file_dialog(
                FileDialog.SAVE,
                save_filename=suggested_filename,
                file_types=file_types,
            )
        except OSError as e:
            return {"ok": False, "error": str(e)}

        if not paths:
            return {"ok": False, "cancelled": True}

        dest = paths[0] if isinstance(paths, (list, tuple)) else paths
        try:
            Path(dest).write_text(content, encoding="utf-8")
        except OSError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "path": str(dest)}


def main() -> None:
    import webview

    url = str(html_file().resolve())
    webview.create_window(
        "3D 轨迹分析仪 - AI 增强版",
        url=url,
        js_api=Api(),
        width=1280,
        height=800,
        min_size=(800, 600),
        background_color='#0f172a',  # 匹配 HTML 背景色，消除白色闪烁
    )
    webview.start(debug=False)


if __name__ == "__main__":
    main()
