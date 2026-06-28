"""Garmin 认证与客户端构建工具。

v1.0.3 重点：
- 大陆区和国际区 token 分目录保存，避免区域混用。
- 运行同步/下载时只加载已有 token，不自动账号密码重登。
- 登录时支持 Garmin MFA 输入，并在成功后 dump token。
- 使用 Python 标准库获取 OAuth consumer 配置，减少 Windows 对系统 curl 的依赖。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Optional, Union

hermes_libs = os.path.expanduser("~/Library/Application Support/QClaw/hermes/libs")
if hermes_libs in sys.path:
    sys.path.remove(hermes_libs)

WORKSPACE_DIR = Path(
    os.environ.get("QCLAW_WORKSPACE_DIR", str(Path.home() / ".qclaw" / "workspace"))
).expanduser()
DEFAULT_AUTH_DIRS = {
    "cn": WORKSPACE_DIR / "garmin_auth_cn",
    "global": WORKSPACE_DIR / "garmin_auth_global",
}
LEGACY_AUTH_PATH = WORKSPACE_DIR / "garmin_auth.json"


class GarminStatsAuthError(RuntimeError):
    """认证或区域配置错误。"""


def normalize_region(region: Optional[str]) -> str:
    value = (region or os.environ.get("GARMIN_REGION") or "cn").strip().lower()
    if value not in {"cn", "global"}:
        raise GarminStatsAuthError("region 只能是 cn 或 global")
    return value


def default_tokenstore(region: str) -> Path:
    region = normalize_region(region)
    preferred = DEFAULT_AUTH_DIRS[region]
    if preferred.exists():
        return preferred
    if region == "cn" and LEGACY_AUTH_PATH.exists():
        return LEGACY_AUTH_PATH
    return preferred


def tokenstore_has_tokens(path: Path) -> bool:
    return (
        path.exists()
        and path.is_dir()
        and (path / "oauth1_token.json").is_file()
        and (path / "oauth2_token.json").is_file()
    )


def patch_garth_ssl_consumer() -> None:
    import garth

    try:
        request = urllib.request.Request(
            "https://thegarth.s3.amazonaws.com/oauth_consumer.json",
            headers={"User-Agent": "garmin-stats/1.0"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = response.read().decode("utf-8").strip()
        if payload.startswith("{"):
            garth.sso.OAUTH_CONSUMER = json.loads(payload)
    except Exception:
        pass


def is_rate_limited_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "429" in text or "too many requests" in text or "rate limit" in text


def auth_error_message(region: str, tokenstore: Path, exc: BaseException) -> str:
    if is_rate_limited_error(exc):
        return (
            "Garmin 返回 429/Too Many Requests。请停止重试，等待一段时间后再试；"
            "国际区账号尤其不要频繁重新登录。"
        )
    return (
        f"Garmin 认证失败（region={region}, tokenstore={tokenstore}）。"
        "请先运行 login.py 登录对应区域账号；国际区账号使用 --region global。"
    )


def build_client(region: str = "cn", tokenstore: Optional[Union[str, Path]] = None):
    import garminconnect

    region = normalize_region(region)
    token_path = Path(tokenstore).expanduser() if tokenstore else default_tokenstore(region)
    if not tokenstore_has_tokens(token_path):
        raise GarminStatsAuthError(
            f"未找到 Garmin token: {token_path}。请先运行 login.py --region {region}"
        )

    patch_garth_ssl_consumer()
    client = garminconnect.Garmin(is_cn=(region == "cn"))
    try:
        client.login(tokenstore=str(token_path))
    except Exception as exc:
        raise GarminStatsAuthError(auth_error_message(region, token_path, exc)) from exc
    return client, client.garth, token_path


def login_and_save(
    email: str,
    password: str,
    region: str = "cn",
    tokenstore: Optional[Union[str, Path]] = None,
) -> Path:
    import garminconnect

    region = normalize_region(region)
    token_path = Path(tokenstore).expanduser() if tokenstore else DEFAULT_AUTH_DIRS[region]
    token_path.mkdir(parents=True, exist_ok=True)

    patch_garth_ssl_consumer()
    client = garminconnect.Garmin(email=email, password=password, is_cn=(region == "cn"))
    try:
        client.login()
        client.garth.dump(str(token_path))
    except Exception as exc:
        raise GarminStatsAuthError(auth_error_message(region, token_path, exc)) from exc
    return token_path
