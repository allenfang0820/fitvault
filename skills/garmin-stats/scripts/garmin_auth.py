"""Garmin authentication and client construction for python-garminconnect 0.3.6.

The app-level contract intentionally targets the new native-auth stack in
python-garminconnect 0.3.6. Do not reintroduce direct legacy session internals
here; callers should interact through the Garmin object and its 0.3.x client.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional, Union

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
TOKEN_FILE_NAME = "garmin_tokens.json"
DEFAULT_HTTP_TIMEOUT_SEC = 30
SUPPORTED_GARMINCONNECT_VERSION = "0.3.6"


class GarminStatsAuthError(RuntimeError):
    """Authentication or region configuration error."""


class GarminStatsMFARequired(GarminStatsAuthError):
    """Garmin login requires an MFA code."""

    def __init__(self, message: str, client_state: Any = None) -> None:
        super().__init__(message)
        self.client_state = client_state


class GarminStatsRateLimited(GarminStatsAuthError):
    """Garmin rejected login due to rate limiting."""


class GarminStatsNetworkOrWafError(GarminStatsAuthError):
    """Network, Cloudflare, WAF, or transient Garmin SSO failure."""


class GarminStatsProviderIncompatible(GarminStatsAuthError):
    """Installed Garmin provider dependency does not match this adapter."""


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


def _token_file(path: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_dir() or not expanded.name.endswith(".json"):
        return expanded / TOKEN_FILE_NAME
    return expanded


def tokenstore_has_tokens(path: Path) -> bool:
    token_file = _token_file(path)
    return token_file.is_file()


def garmin_http_timeout() -> int:
    raw = os.environ.get("GARMIN_HTTP_TIMEOUT", "").strip()
    if not raw:
        return DEFAULT_HTTP_TIMEOUT_SEC
    try:
        return max(10, int(raw))
    except ValueError:
        return DEFAULT_HTTP_TIMEOUT_SEC


def _garminconnect_version() -> str:
    try:
        from importlib import metadata

        return metadata.version("garminconnect")
    except Exception:
        return ""


def _assert_supported_provider(garminconnect_module: Any) -> None:
    version = _garminconnect_version()
    if version and version != SUPPORTED_GARMINCONNECT_VERSION:
        raise GarminStatsProviderIncompatible(
            f"Garmin provider 依赖版本不兼容：检测到 garminconnect {version}，"
            f"当前应用要求 {SUPPORTED_GARMINCONNECT_VERSION}。请重新安装应用依赖。"
        )
    garmin_cls = getattr(garminconnect_module, "Garmin", None)
    if garmin_cls is None:
        raise GarminStatsProviderIncompatible("garminconnect 缺少 Garmin 类。")


def _new_garmin(
    garminconnect_module: Any,
    *,
    email: str | None = None,
    password: str | None = None,
    region: str = "cn",
    prompt_mfa: Any = None,
    return_on_mfa: bool = False,
) -> Any:
    _assert_supported_provider(garminconnect_module)
    try:
        return garminconnect_module.Garmin(
            email=email,
            password=password,
            is_cn=(normalize_region(region) == "cn"),
            prompt_mfa=prompt_mfa,
            return_on_mfa=return_on_mfa,
        )
    except TypeError as exc:
        raise GarminStatsProviderIncompatible(
            "garminconnect Garmin 构造函数不兼容：当前代码需要 0.3.6 的 "
            "prompt_mfa / return_on_mfa API。"
        ) from exc


def _client_dump(client: Any, token_path: Path) -> None:
    api_client = getattr(client, "client", None)
    dump_fn = getattr(api_client, "dump", None)
    if callable(dump_fn):
        dump_fn(str(token_path))


def _profile(client: Any) -> dict[str, Any]:
    profile = getattr(client, "profile", None)
    if isinstance(profile, dict):
        return profile
    display_name = getattr(client, "display_name", None)
    full_name = getattr(client, "full_name", None)
    return {
        "displayName": display_name,
        "fullName": full_name,
    }


def client_display_name(client: Any) -> str:
    return str(getattr(client, "display_name", None) or _profile(client).get("displayName") or "")


def client_full_name(client: Any) -> str:
    return str(getattr(client, "full_name", None) or _profile(client).get("fullName") or "")


def client_connectapi(client: Any, endpoint: str, **kwargs: Any) -> Any:
    connectapi = getattr(client, "connectapi", None)
    if callable(connectapi):
        return connectapi(endpoint, **kwargs)
    api_client = getattr(client, "client", None)
    connectapi = getattr(api_client, "connectapi", None)
    if callable(connectapi):
        return connectapi(endpoint, **kwargs)
    raise GarminStatsProviderIncompatible("Garmin client 缺少 connectapi 可调用入口。")


def _classify_error(region: str, tokenstore: Path, exc: BaseException) -> GarminStatsAuthError:
    text = str(exc or "")
    lower = text.lower()
    if "no attribute 'garth'" in lower or 'no attribute "garth"' in lower:
        return GarminStatsProviderIncompatible(
            "Garmin provider API 不兼容：当前代码不应访问旧版 session 属性。"
        )
    if "mfa" in lower or "one-time" in lower or "verification code" in lower or "验证码" in lower:
        return GarminStatsMFARequired("Garmin 账号需要 MFA 验证码")
    if "429" in lower or "too many" in lower or "rate limit" in lower:
        return GarminStatsRateLimited(
            "Garmin 返回 429/Too Many Requests。请停止重试，等待一段时间后再试。"
        )
    if "cloudflare" in lower or "captcha" in lower or "waf" in lower or "bot" in lower or "403" in lower:
        return GarminStatsNetworkOrWafError(
            f"Garmin 登录被网络/WAF 拦截或暂不可用（region={region}, tokenstore={tokenstore}）。原始错误：{text}"
        )
    if "401" in lower or "unauthorized" in lower or "invalid username" in lower or "incorrect" in lower:
        return GarminStatsAuthError(
            f"Garmin 认证失败（region={region}, tokenstore={tokenstore}）。"
            f" 原始错误：{text}"
        )
    return GarminStatsNetworkOrWafError(
        f"Garmin 登录失败（region={region}, tokenstore={tokenstore}）。原始错误：{text}"
    )


def build_client(region: str = "cn", tokenstore: Optional[Union[str, Path]] = None):
    import garminconnect

    region = normalize_region(region)
    token_path = Path(tokenstore).expanduser() if tokenstore else default_tokenstore(region)
    if not tokenstore_has_tokens(token_path):
        raise GarminStatsAuthError(
            f"未找到 Garmin token: {token_path}。请先运行 login.py --region {region}"
        )

    client = _new_garmin(garminconnect, region=region)
    try:
        client.login(tokenstore=str(token_path))
    except Exception as exc:
        raise _classify_error(region, token_path, exc) from exc
    return client, token_path


def login_and_save(
    email: str,
    password: str,
    region: str = "cn",
    tokenstore: Optional[Union[str, Path]] = None,
) -> Path:
    return login_and_save_app(
        email=email,
        password=password,
        region=region,
        tokenstore=tokenstore,
    )


def login_and_save_app(
    email: str,
    password: str,
    region: str = "cn",
    tokenstore: Optional[Union[str, Path]] = None,
    mfa_code: Optional[str] = None,
    mfa_state: Any = None,
) -> Path:
    """App Garmin login entry point.

    MFA is supplied by the desktop form. No terminal prompt is allowed here.
    """
    import garminconnect

    region = normalize_region(region)
    token_path = Path(tokenstore).expanduser() if tokenstore else DEFAULT_AUTH_DIRS[region]
    token_path.mkdir(parents=True, exist_ok=True)
    clean_mfa = str(mfa_code or "").strip()

    if clean_mfa and mfa_state is not None:
        client = _new_garmin(garminconnect, region=region)
        try:
            client.resume_login(mfa_state, clean_mfa)
            _client_dump(client, token_path)
        except Exception as exc:
            raise _classify_error(region, token_path, exc) from exc
        return token_path

    def prompt_mfa() -> str:
        if not clean_mfa:
            raise GarminStatsMFARequired("Garmin 账号需要 MFA 验证码")
        return clean_mfa

    client = _new_garmin(
        garminconnect,
        email=email,
        password=password,
        region=region,
        prompt_mfa=prompt_mfa,
        return_on_mfa=not bool(clean_mfa),
    )
    try:
        status, client_state = client.login(tokenstore=str(token_path))
        if status == "needs_mfa":
            raise GarminStatsMFARequired("Garmin 账号需要 MFA 验证码", client_state=client_state)
        _client_dump(client, token_path)
    except GarminStatsMFARequired:
        raise
    except Exception as exc:
        raise _classify_error(region, token_path, exc) from exc
    return token_path
