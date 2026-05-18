#!/usr/bin/env python3
"""使用 pywebview 在桌面窗口中加载「徒步轨迹AI分析仪」单页 HTML。"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import llm_backend  # noqa: F401 -- PyInstaller bundles LLM 模块
import track_backend  # noqa: F401 -- PyInstaller bundles track_backend
import profile_backend  # noqa: F401 -- PyInstaller bundles profile 模块

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

    def save_llm_config(self, provider: str, url: str, model: str, api_key: str, agent_id: str = "", watch_brand: str = "") -> dict:
        try:
            llm_backend.save_llm_config(provider, url, model, api_key, agent_id, watch_brand)
        except OSError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True}

    def test_llm_config(self, provider: str, url: str, model: str, api_key: str, agent_id: str = "") -> dict:
        try:
            text = llm_backend.test_llm_connection(
                provider=provider,
                url=url,
                model=model,
                api_key=api_key,
                agent_id=agent_id,
            )
            return {"ok": True, "message": text}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def call_llm(self, prompt: str, sport_type: str = "hiking") -> dict:
        """对话或路书：prompt 为普通用户文本，或魔法串 __REPORT_TERRAIN__ / __REPORT_PERSONALIZED__。"""
        cfg = llm_backend.load_llm_config()
        url = (cfg.get("url") or "").strip()
        if not url:
            return {"ok": False, "error": "API 接口地址为空，请在设置中配置"}

        provider = str(cfg.get("provider") or "local_mcp")
        model = str(cfg.get("model") or "openclaw").strip()
        api_key = str(cfg.get("api_key") or "")
        agent_id = str(cfg.get("agent_id") or "")
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
                    agent_id=agent_id,
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
                    agent_id=agent_id,
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
                    agent_id=agent_id,
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
        result = {"ok": True, "filename": Path(src).name, "data": data, "_src_path": src}
        return result

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

    def get_user_profile(self) -> dict:
        prof = profile_backend.get_profile()
        zones = profile_backend.compute_hrr_zones(
            prof.resting_hr or 60, prof.max_hr or 190
        )
        return {"ok": True, "profile": prof.to_dict(), "hrr_zones": zones}

    def save_user_profile(self, data: dict) -> dict:
        try:
            profile_backend.upsert_profile(data)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True}

    def fetch_mcp_persona(self, platform: str) -> dict:
        result = profile_backend.fetch_mcp_persona(platform)
        if result.get("ok"):
            prof = profile_backend.get_profile()
            zones = profile_backend.compute_hrr_zones(
                prof.resting_hr or 60, prof.max_hr or 190
            )
            return {"ok": True, "profile": prof.to_dict(), "hrr_zones": zones}
        return result

    def get_activity_history(self) -> dict:
        """返回按时间倒序的历史运动记录列表。"""
        try:
            history = profile_backend.get_activity_history(limit=50)
            return {"ok": True, "history": history}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def calculate_advanced_radar_metrics(self) -> dict:
        """计算六维个人运动能力雷达图数据。"""
        import math
        import json
        import pandas as pd
        from datetime import datetime, timedelta

        default_metrics = {
            "endurance": 50.0, "speed": 50.0, "threshold": 50.0,
            "climbing": 50.0, "stability": 50.0, "recovery": 50.0
        }

        try:
            prof = profile_backend.get_profile()
            conn = profile_backend._conn()

            ninety_days_ago = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')
            rows = conn.execute(
                "SELECT * FROM activities WHERE updated_at >= ? ORDER BY updated_at DESC",
                (ninety_days_ago,)
            ).fetchall()
            conn.close()

            acts = [dict(r) for r in rows]

            # 1. 耐力容量 (Endurance)
            total_dist = sum([a.get("dist_km") or 0.0 for a in acts])
            endurance = min((total_dist / 500.0) * 100.0, 100.0)
            if not acts: endurance = 50.0

            # 2. 速度爆发 (Speed)
            max_speed_kmh = 0.0
            for a in acts:
                pts_str = a.get("points_json")
                if pts_str:
                    try:
                        pts = json.loads(pts_str)
                        if len(pts) > 60:
                            df = pd.DataFrame(pts)
                            if 'speed' in df.columns:
                                window_max = df['speed'].rolling(60).mean().max() * 3.6
                                max_speed_kmh = max(max_speed_kmh, window_max)
                    except Exception:
                        pass
                if max_speed_kmh == 0.0:
                    dist = a.get("dist_km") or 0.0
                    dur = a.get("duration_sec") or 0.0
                    if dur > 0:
                        max_speed_kmh = max(max_speed_kmh, (dist / (dur / 3600.0)) * 1.5)
            
            age = prof.age or 30
            limit_speed = 22.0 - (age - 20) * 0.1 if age > 20 else 22.0
            speed = min((max_speed_kmh / limit_speed) * 100.0, 100.0) if max_speed_kmh > 0 else 50.0

            # 3. 乳酸阈值 (Threshold)
            if prof.lactate_threshold_hr:
                threshold = max(0.0, min(((prof.lactate_threshold_hr - 130) / 50.0) * 100.0, 100.0))
            else:
                lthr = (prof.max_hr * 0.85) if prof.max_hr else 165.0
                threshold = max(0.0, min(((lthr - 130) / 50.0) * 100.0, 100.0))

            # 4. 坡度爬升 (Climbing)
            max_vam = 0.0
            for a in acts:
                gain = a.get("gain_m") or 0.0
                dur = a.get("duration_sec") or 0.0
                stype = a.get("sport_type") or ""
                if gain > 200 or stype.lower() in ["trail", "trail_running", "hiking"]:
                    if dur > 0:
                        vam = gain / (dur / 3600.0)
                        max_vam = max(max_vam, vam)
            climbing = min((max_vam / 800.0) * 100.0, 100.0) if max_vam > 0 else 50.0

            # 5. 心肺稳定 (Stability)
            decoup_scores = []
            for a in acts:
                if a.get("hr_decoupling") is not None:
                    decoup_scores.append(a.get("hr_decoupling"))
            if decoup_scores:
                recent_3 = decoup_scores[:3]
                avg_decoup = sum(recent_3) / len(recent_3)
                if avg_decoup <= 3.0:
                    stability = 100.0
                else:
                    stability = max(0.0, 100.0 - (avg_decoup - 3.0) * 6.0)
            else:
                stability = 50.0

            # 6. 恢复效能 (Recovery)
            hrv = prof.hrv_baseline or 45.0
            rhr = prof.resting_hr or 60.0
            rec_score = (hrv / 70.0) * 60.0 + ((75.0 - rhr) / 25.0) * 40.0
            recovery = max(0.0, min(rec_score, 100.0))

            return {
                "ok": True,
                "endurance": round(endurance, 1),
                "speed": round(speed, 1),
                "threshold": round(threshold, 1),
                "climbing": round(climbing, 1),
                "stability": round(stability, 1),
                "recovery": round(recovery, 1)
            }
        except Exception as e:
            return {"ok": True, **default_metrics}

    def load_local_track(self, file_path: str) -> dict:
        """根据本地路径读取并解析轨迹文件，返回与 parse_track_file 一致的结构。"""
        try:
            return profile_backend.load_local_track(file_path)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_activity(self, data: dict) -> dict:
        """保存运动记录，自动将源文件复制到 local_tracks 目录。"""
        try:
            src = data.get("_src_path")
            if src:
                local_path = profile_backend.copy_track_to_local(src)
                data["file_path"] = local_path
            else:
                data["file_path"] = None
            profile_backend.save_activity(data)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True}


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
