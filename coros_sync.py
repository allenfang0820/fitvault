"""COROS skill script provider.

This module is intentionally limited to locating bundled coros-stats scripts
and checking/launching local authorization helpers. It does not call LLM
backends, read token contents, or mutate application state.
"""

from __future__ import annotations

import json
import base64
import importlib.util
import ntpath
import os
import re
import shutil
import shlex
import subprocess
import sys
import uuid
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterator

from subprocess_utils import popen_hidden, run_hidden


VALID_COROS_REGIONS = {"cn", "us", "eu"}
DEFAULT_TIMEOUT_SEC = 300
ERROR_SNIPPET_CHARS = 800
MAX_COROS_FIT_DOWNLOAD_LIMIT = 10


class CorosSyncError(RuntimeError):
    """Base error for COROS provider failures."""

    def __init__(self, message: str, *, code: str = "coros_sync_error") -> None:
        super().__init__(message)
        self.code = code


class CorosSkillNotFoundError(CorosSyncError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="coros_skill_not_found")


class CorosScriptFailed(CorosSyncError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="coros_script_failed")


class CorosAuthRequiredError(CorosSyncError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="coros_auth_required")


class CorosJsonParseError(CorosSyncError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="coros_json_parse_error")


class CorosFitDownloadError(CorosSyncError):
    def __init__(self, message: str, *, code: str = "coros_fit_download_failed") -> None:
        super().__init__(message, code=code)


COROS_ACTION_HINTS = {
    "invalid_coros_region": "请检查 COROS 区域配置，仅支持 cn、us 或 eu。",
    "coros_auth_required": "请回配置页重新连接 COROS 账号。",
    "coros_node_missing": "请安装包含 Node.js runtime 的脉图安装包，或回配置页重新检查账号连接。",
    "coros_skill_not_found": "请确认 coros-stats skill 已随应用正确安装，然后重试。",
    "coros_keepalive_invalid": "请回配置页检查 COROS 账号连接状态并重新连接。",
    "coros_mcp_unavailable": "请稍后重试，或重新打开 COROS 授权页面完成登录。",
    "coros_fit_download_failed": "请确认网络可用、授权有效，并尝试缩小日期范围后重试。",
    "coros_fit_download_limit": "请缩小日期范围后分批同步。",
    "coros_sync_partial": "请查看失败列表并分批重试。",
    "coros_import_failed": "FIT 文件已下载，但导入活动库失败，请稍后重试或使用本地导入。",
    "coros_profile_sync_failed": "请回配置页检查 COROS 授权状态，然后重试画像同步。",
    "coros_json_parse_error": "COROS 返回格式异常，请更新 coros-stats skill 后重试。",
    "unknown": "COROS 同步出现未知异常，请稍后重试。",
}

COROS_USER_MESSAGES = {
    "invalid_coros_region": "COROS 区域配置无效。",
    "coros_auth_required": "COROS 授权不可用或已失效，请到配置页完成授权。",
    "coros_node_missing": "未检测到 COROS 同步所需的 Node.js runtime。",
    "coros_skill_not_found": "未找到 COROS 同步所需的 coros-stats skill。",
    "coros_keepalive_invalid": "COROS keepalive 配置不可用。",
    "coros_mcp_unavailable": "COROS MCP 服务暂不可用。",
    "coros_fit_download_failed": "COROS FIT 下载失败。",
    "coros_fit_download_limit": "COROS 单次下载数量超过限制。",
    "coros_sync_partial": "COROS 部分活动同步失败。",
    "coros_import_failed": "COROS FIT 导入失败。",
    "coros_profile_sync_failed": "COROS 画像同步失败。",
    "coros_json_parse_error": "COROS 返回内容无法解析。",
    "unknown": "COROS 同步出现未知异常。",
}

SENSITIVE_COROS_KEYS = {
    "password",
    "passwd",
    "mfa",
    "mfa_code",
    "otp",
    "cookie",
    "set-cookie",
    "authorization",
    "access_token",
    "refresh_token",
    "id_token",
    "api_key",
    "apikey",
    "secret",
}


@dataclass(frozen=True)
class CorosSkillPaths:
    skill_dir: Path
    profile_runner: Path
    install_mcp: Path
    install_mcp_cmd: Path


@dataclass(frozen=True)
class CorosScriptResult:
    command: list[str]
    stdout: str
    stderr: str
    returncode: int


@dataclass(frozen=True)
class CorosAuthStatus:
    ok: bool
    region: str
    status: str
    token_path: str
    message: str
    login_command: list[str]
    mcp_authorized: bool
    node_available: bool
    skill_available: bool = False
    node_path: str = ""
    openclaw_node_binary: str = ""
    openclaw_mjs: str = ""
    keepalive_region: str = ""
    keepalive_mcp_url: str = ""
    keepalive_token_path: str = ""
    diagnostics: list[dict[str, str]] | None = None


@dataclass(frozen=True)
class CorosLoginResult:
    ok: bool
    region: str
    status: str
    command: list[str]
    stdout: str
    stderr: str
    message: str


@dataclass(frozen=True)
class CorosConnectionStepResult:
    ok: bool
    status: str
    message: str
    node_path: str = ""
    npm_path: str = ""
    coros_mcp_path: str = ""
    token_path: str = ""
    diagnostics: list[dict[str, str]] | None = None


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        exe_dir = Path(sys.executable).resolve().parent
        candidates = [
            meipass.parent / "Resources",
            exe_dir.parent / "Resources",
            meipass,
            meipass / "Resources",
            exe_dir,
            exe_dir / "Resources",
            exe_dir / "_internal",
            exe_dir / "_internal" / "Resources",
        ]
        for candidate in candidates:
            if (candidate / "skills" / "coros-stats" / "scripts" / "coros_runner_profile.py").is_file():
                return candidate
        return meipass if (meipass / "skills").exists() else candidates[0]
    return Path(__file__).resolve().parent


def resolve_coros_region(region: str | None = None) -> str:
    value = str(region or os.environ.get("COROS_REGION") or "cn").strip().lower()
    if value not in VALID_COROS_REGIONS:
        allowed = ", ".join(sorted(VALID_COROS_REGIONS))
        raise CorosSyncError(f"不支持的 COROS 区域: {value or '(empty)'}，仅支持 {allowed}", code="invalid_coros_region")
    return value


def get_coros_skill_paths(base_dir: Path | str | None = None) -> CorosSkillPaths:
    root = Path(base_dir).expanduser().resolve() if base_dir is not None else app_base_dir()
    skill_dir = root / "skills" / "coros-stats"
    scripts_dir = skill_dir / "scripts"
    paths = CorosSkillPaths(
        skill_dir=skill_dir,
        profile_runner=scripts_dir / "coros_runner_profile.py",
        install_mcp=scripts_dir / "install_coros_mcp.sh",
        install_mcp_cmd=scripts_dir / "install_coros_mcp.cmd",
    )
    missing = [
        str(path)
        for path in (paths.profile_runner, paths.install_mcp)
        if not path.is_file()
    ]
    if missing:
        raise CorosSkillNotFoundError("未找到 COROS skill 脚本: " + "; ".join(missing))
    return paths


def default_mcp_token_path(
    region: str | None = None,
    token_root: Path | str | None = None,
) -> Path:
    resolved_region = resolve_coros_region(region)
    root = default_mcp_token_root(token_root)
    return root / resolved_region / "token.json"


def default_mcp_token_root(token_root: Path | str | None = None) -> Path:
    if token_root is not None:
        return Path(token_root).expanduser()
    env_root = str(os.environ.get("COROS_MCP_TOKEN_ROOT") or "").strip()
    if env_root:
        return Path(env_root).expanduser()
    return Path.home() / ".coros-mcp-skill-gateway-ts"


def default_mcp_pending_login_path(region: str | None = None, token_root: Path | str | None = None) -> Path:
    return default_mcp_token_path(region, token_root).with_name("pending-login.json")


def default_node_global_prefix() -> Path:
    return Path(os.environ.get("MAITU_NODE_GLOBAL_PREFIX", str(Path.home() / ".maitu" / "node-global"))).expanduser()


def default_node_global_bin_dir(prefix: Path | str | None = None) -> Path:
    root = Path(prefix).expanduser() if prefix is not None else default_node_global_prefix()
    return root if sys.platform.startswith("win") else root / "bin"


def open_url_in_system_browser(url: str) -> bool:
    safe_url = str(url or "").strip()
    if not safe_url:
        return False
    try:
        if sys.platform == "darwin":
            completed = run_hidden(
                ["open", safe_url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            return int(completed.returncode) == 0
        if os.name == "nt":
            os.startfile(safe_url)  # type: ignore[attr-defined]
            return True
        completed = run_hidden(
            ["xdg-open", safe_url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        return int(completed.returncode) == 0
    except Exception:
        return False


def _is_executable_file(path: Path) -> bool:
    return path.is_file() and os.access(str(path), os.X_OK)


def _nvm_node_candidates(home: Path) -> list[Path]:
    root = home / ".nvm" / "versions" / "node"
    if not root.is_dir():
        return []
    return sorted(root.glob("*/bin/node"), reverse=True)


def _bundled_node_candidates() -> list[Path]:
    candidates: list[Path] = []
    env_dir = str(os.environ.get("MAITU_BUNDLED_NODE_DIR") or "").strip()
    if env_dir:
        env_root = Path(env_dir).expanduser()
        candidates.extend([
            env_root / "bin" / "node",
            env_root / "node.exe",
        ])

    base = app_base_dir()
    exe_dir = Path(sys.executable).resolve().parent
    candidates.extend([
        base / "node" / "bin" / "node",
        base / "node" / "bin" / "node.exe",
        base / "node" / "node.exe",
        base / "Resources" / "node" / "bin" / "node",
        base / "Resources" / "node" / "bin" / "node.exe",
        base / "Resources" / "node" / "node.exe",
        exe_dir / "node" / "bin" / "node",
        exe_dir / "node" / "bin" / "node.exe",
        exe_dir / "node" / "node.exe",
        exe_dir / "Resources" / "node" / "node.exe",
        exe_dir / "Resources" / "node" / "bin" / "node.exe",
        exe_dir / "Resources" / "node" / "bin" / "node",
        exe_dir / "_internal" / "node" / "node.exe",
        exe_dir / "_internal" / "node" / "bin" / "node.exe",
        exe_dir / "_internal" / "node" / "bin" / "node",
        exe_dir / "_internal" / "Resources" / "node" / "node.exe",
        exe_dir / "_internal" / "Resources" / "node" / "bin" / "node.exe",
        exe_dir / "_internal" / "Resources" / "node" / "bin" / "node",
        exe_dir.parent / "Resources" / "node" / "bin" / "node",
        exe_dir.parent / "Resources" / "node" / "bin" / "node.exe",
        exe_dir.parent / "Resources" / "node" / "node.exe",
    ])
    return candidates


def discover_node_binary(home: Path | str | None = None) -> str:
    env_node = str(os.environ.get("QCLAW_CLI_NODE_BINARY") or "").strip()
    if env_node and _is_executable_file(Path(env_node).expanduser()):
        return str(Path(env_node).expanduser())

    for candidate in _bundled_node_candidates():
        if _is_executable_file(candidate):
            return str(candidate)

    path_node = shutil.which("node")
    if path_node:
        return path_node

    home_path = Path(home).expanduser() if home is not None else Path.home()
    candidates = [
        *_nvm_node_candidates(home_path),
        Path("/opt/homebrew/bin/node"),
        Path("/usr/local/bin/node"),
        home_path / "Library" / "Application Support" / "QClaw" / "openclaw" / "config" / "bin" / "node",
    ]
    for candidate in candidates:
        if _is_executable_file(candidate):
            return str(candidate)
    return ""


def discover_openclaw_mjs(home: Path | str | None = None) -> str:
    env_mjs = str(os.environ.get("QCLAW_CLI_OPENCLAW_MJS") or "").strip()
    if env_mjs and Path(env_mjs).expanduser().is_file():
        return str(Path(env_mjs).expanduser())

    home_path = Path(home).expanduser() if home is not None else Path.home()
    candidates = [
        home_path / "Library" / "Application Support" / "QClaw" / "openclaw" / "node_modules" / "openclaw" / "openclaw.mjs",
        home_path / "Library" / "Application Support" / "QClaw" / "openclaw" / "openclaw.mjs",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return ""


def build_coros_runtime_env(
    env: dict[str, str] | None = None,
    *,
    token_root: Path | str | None = None,
) -> dict[str, str]:
    runtime_env = dict(env or os.environ)
    resolved_token_root = default_mcp_token_root(token_root or runtime_env.get("COROS_MCP_TOKEN_ROOT")).resolve()
    runtime_env["COROS_MCP_TOKEN_ROOT"] = str(resolved_token_root)
    if os.name == "nt":
        user_home = str(Path.home())
        runtime_env.setdefault("USERPROFILE", user_home)
        runtime_env.setdefault("HOME", runtime_env.get("USERPROFILE") or user_home)
    node_global_prefix = Path(str(runtime_env.get("NPM_CONFIG_PREFIX") or default_node_global_prefix())).expanduser()
    node_global_bin = default_node_global_bin_dir(node_global_prefix)
    node_path = discover_node_binary()
    if node_path:
        node_text = str(Path(node_path).expanduser())
        if "\\" in node_text:
            node_name = ntpath.basename(node_text).lower()
            node_dir = ntpath.dirname(node_text)
            node_root = node_dir if node_name == "node.exe" else ntpath.dirname(node_dir)
        else:
            node_file = Path(node_text)
            node_dir = str(node_file.parent)
            node_root = str(node_file.parent if node_file.name.lower() == "node.exe" else node_file.parent.parent)
        runtime_env["PATH"] = node_dir + os.pathsep + str(node_global_bin) + os.pathsep + runtime_env.get("PATH", "")
        runtime_env.setdefault("QCLAW_CLI_NODE_BINARY", node_path)
        runtime_env.setdefault("MAITU_BUNDLED_NODE_DIR", node_root)
    else:
        runtime_env["PATH"] = str(node_global_bin) + os.pathsep + runtime_env.get("PATH", "")
    runtime_env.setdefault("NPM_CONFIG_PREFIX", str(node_global_prefix))
    openclaw_mjs = discover_openclaw_mjs()
    if openclaw_mjs:
        runtime_env.setdefault("QCLAW_CLI_OPENCLAW_MJS", openclaw_mjs)
    return runtime_env


def coros_issuer_for_region(region: str | None = None) -> str:
    return {
        "cn": "https://mcpcn.coros.com",
        "us": "https://mcpus.coros.com",
        "eu": "https://mcpeu.coros.com",
    }[resolve_coros_region(region)]


def discover_npm_binary(env: dict[str, str] | None = None) -> str:
    runtime_env = build_coros_runtime_env(env)
    npm_name = "npm.cmd" if sys.platform.startswith("win") else "npm"
    return shutil.which(npm_name, path=runtime_env.get("PATH", ""))


def discover_coros_mcp_binary(env: dict[str, str] | None = None) -> str:
    runtime_env = build_coros_runtime_env(env)
    names = ["coros-mcp.cmd", "coros-mcp"] if sys.platform.startswith("win") else ["coros-mcp"]
    for name in names:
        found = shutil.which(name, path=runtime_env.get("PATH", ""))
        if found:
            return found
        candidate = default_node_global_bin_dir(runtime_env.get("NPM_CONFIG_PREFIX")) / name
        if _is_executable_file(candidate):
            return str(candidate)
    return ""


def prepare_coros_connection_runtime(
    *,
    region: str | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> CorosConnectionStepResult:
    resolved_region = resolve_coros_region(region)
    diagnostics = [_diag("region", "ok", f"COROS 区域有效: {resolved_region}")]
    runtime_env = build_coros_runtime_env(env)
    token_path = default_mcp_token_path(resolved_region, runtime_env.get("COROS_MCP_TOKEN_ROOT"))
    node_path = discover_node_binary()
    if not node_path:
        diagnostics.append(_diag("node", "failed", "未检测到 Node.js"))
        return CorosConnectionStepResult(
            ok=False,
            status="failed",
            message="未检测到 Node.js，无法启动 COROS OAuth 连接向导。",
            node_path="",
            token_path=str(token_path),
            diagnostics=diagnostics,
        )
    diagnostics.append(_diag("node", "ok", f"Node.js 可用: {node_path}"))
    try:
        Path(runtime_env["NPM_CONFIG_PREFIX"]).expanduser().mkdir(parents=True, exist_ok=True)
        default_node_global_bin_dir(runtime_env["NPM_CONFIG_PREFIX"]).mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    npm_path = discover_npm_binary(runtime_env)
    if not npm_path:
        diagnostics.append(_diag("npm", "failed", "未检测到 npm"))
        return CorosConnectionStepResult(
            ok=False,
            status="failed",
            message="未检测到 npm。请使用包含完整 Node.js runtime 的脉图安装包。",
            node_path=node_path,
            token_path=str(token_path),
            diagnostics=diagnostics,
        )
    diagnostics.append(_diag("npm", "ok", f"npm 可用: {npm_path}"))

    coros_mcp_path = discover_coros_mcp_binary(runtime_env)
    if not coros_mcp_path:
        diagnostics.append(_diag("coros_mcp", "checking", "正在安装 coros-mcp"))
        try:
            completed = run_hidden(
                [npm_path, "install", "-g", "coros-mcp"],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=runtime_env,
            )
        except subprocess.TimeoutExpired:
            diagnostics.append(_diag("coros_mcp", "failed", "coros-mcp 安装超时"))
            return CorosConnectionStepResult(False, "failed", "coros-mcp 安装超时。", node_path, npm_path, "", str(token_path), diagnostics)
        except OSError as exc:
            diagnostics.append(_diag("coros_mcp", "failed", f"coros-mcp 安装启动失败: {exc}"))
            return CorosConnectionStepResult(False, "failed", f"coros-mcp 安装启动失败: {exc}", node_path, npm_path, "", str(token_path), diagnostics)
        if int(completed.returncode) != 0:
            detail = _error_snippet(str(completed.stderr or completed.stdout or ""))
            diagnostics.append(_diag("coros_mcp", "failed", f"coros-mcp 安装失败: {detail}"))
            return CorosConnectionStepResult(False, "failed", "coros-mcp 安装失败。", node_path, npm_path, "", str(token_path), diagnostics)
        coros_mcp_path = discover_coros_mcp_binary(runtime_env)
    if not coros_mcp_path:
        diagnostics.append(_diag("coros_mcp", "failed", "未找到 coros-mcp 命令"))
        return CorosConnectionStepResult(False, "failed", "coros-mcp 安装后仍不可用。", node_path, npm_path, "", str(token_path), diagnostics)
    diagnostics.append(_diag("coros_mcp", "ok", f"coros-mcp 可用: {coros_mcp_path}"))
    return CorosConnectionStepResult(
        ok=True,
        status="checking",
        message="COROS MCP 运行环境已就绪。",
        node_path=node_path,
        npm_path=npm_path,
        coros_mcp_path=coros_mcp_path,
        token_path=str(token_path),
        diagnostics=diagnostics,
    )


def start_coros_oauth_login(
    *,
    region: str | None = None,
    coros_mcp_path: str | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 30,
) -> CorosConnectionStepResult:
    resolved_region = resolve_coros_region(region)
    runtime_env = build_coros_runtime_env(env)
    binary = str(coros_mcp_path or discover_coros_mcp_binary(runtime_env) or "coros-mcp")
    token_root = runtime_env.get("COROS_MCP_TOKEN_ROOT")
    token_path = default_mcp_token_path(resolved_region, token_root)
    pending_path = default_mcp_pending_login_path(resolved_region, token_root)
    try:
        completed = run_hidden(
            [binary, "--issuer", coros_issuer_for_region(resolved_region), "login-start"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=runtime_env,
        )
    except subprocess.TimeoutExpired:
        return CorosConnectionStepResult(False, "failed", "COROS OAuth 登录链接创建超时。", coros_mcp_path=binary, token_path=str(token_path))
    except OSError as exc:
        return CorosConnectionStepResult(False, "failed", f"COROS OAuth 登录启动失败: {exc}", coros_mcp_path=binary, token_path=str(token_path))

    if int(completed.returncode) != 0:
        detail = _error_snippet(str(completed.stderr or completed.stdout or ""))
        return CorosConnectionStepResult(False, "failed", f"COROS OAuth 登录链接创建失败: {detail}", coros_mcp_path=binary, token_path=str(token_path))

    output = str(completed.stdout or "")
    login_url = ""
    match = re.search(r"https?://\S+", output)
    if match:
        login_url = match.group(0).strip()
    if not login_url and pending_path.is_file():
        try:
            pending = json.loads(pending_path.read_text(encoding="utf-8"))
            login_url = str(pending.get("login_url") or pending.get("authorize_url") or "").strip()
        except Exception:
            login_url = ""
    if login_url:
        opened = open_url_in_system_browser(login_url)
        message = (
            "已打开系统浏览器，请在 COROS 页面完成 OAuth 授权。"
            if opened else
            f"COROS OAuth 登录链接已创建，但未能自动打开浏览器。请复制此链接完成授权：{login_url}"
        )
        return CorosConnectionStepResult(
            True,
            "waiting_callback",
            message,
            coros_mcp_path=binary,
            token_path=str(token_path),
            diagnostics=[_diag("oauth", "waiting", f"COROS OAuth 登录链接已创建: {login_url}")],
        )
    return CorosConnectionStepResult(
        True,
        "waiting_callback",
        "COROS OAuth 登录链接已创建；如果浏览器未打开，请稍后重试连接。",
        coros_mcp_path=binary,
        token_path=str(token_path),
        diagnostics=[_diag("oauth", "warning", "未从 coros-mcp 输出中解析到登录链接")],
    )


def finish_coros_oauth_login(
    *,
    region: str | None = None,
    coros_mcp_path: str | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 3,
) -> CorosConnectionStepResult:
    resolved_region = resolve_coros_region(region)
    runtime_env = build_coros_runtime_env(env)
    binary = str(coros_mcp_path or discover_coros_mcp_binary(runtime_env) or "coros-mcp")
    token_path = default_mcp_token_path(resolved_region, runtime_env.get("COROS_MCP_TOKEN_ROOT"))
    if token_path.is_file():
        return CorosConnectionStepResult(True, "authorized", "COROS 授权成功。", coros_mcp_path=binary, token_path=str(token_path))
    try:
        completed = run_hidden(
            [binary, "--issuer", coros_issuer_for_region(resolved_region), "login-finish"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=runtime_env,
        )
    except subprocess.TimeoutExpired:
        return CorosConnectionStepResult(True, "waiting_callback", "等待你在浏览器中完成 COROS OAuth 授权...", coros_mcp_path=binary, token_path=str(token_path))
    except OSError as exc:
        return CorosConnectionStepResult(False, "failed", f"COROS OAuth 授权状态读取失败: {exc}", coros_mcp_path=binary, token_path=str(token_path))

    if token_path.is_file():
        return CorosConnectionStepResult(True, "authorized", "COROS 授权成功。", coros_mcp_path=binary, token_path=str(token_path))
    output = _error_snippet(str(completed.stderr or completed.stdout or ""))
    if int(completed.returncode) == 0:
        return CorosConnectionStepResult(True, "waiting_callback", "等待你在浏览器中完成 COROS OAuth 授权...", coros_mcp_path=binary, token_path=str(token_path))
    lower = output.lower()
    if "pending" in lower or "not complete" in lower or "waiting" in lower or "timeout" in lower:
        return CorosConnectionStepResult(True, "waiting_callback", "等待你在浏览器中完成 COROS OAuth 授权...", coros_mcp_path=binary, token_path=str(token_path))
    return CorosConnectionStepResult(False, "failed", f"COROS OAuth 授权失败: {output or '未返回授权结果'}", coros_mcp_path=binary, token_path=str(token_path))


def apply_coros_openclaw_optional(
    *,
    region: str | None = None,
    coros_mcp_path: str | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 30,
) -> dict[str, str]:
    resolved_region = resolve_coros_region(region)
    runtime_env = build_coros_runtime_env(env)
    binary = str(coros_mcp_path or discover_coros_mcp_binary(runtime_env) or "coros-mcp")
    if not shutil.which("openclaw", path=runtime_env.get("PATH", "")) and not shutil.which("openclaw.cmd", path=runtime_env.get("PATH", "")):
        return _diag("openclaw", "warning", "未检测到 openclaw 命令，已跳过 OpenClaw 注册。")
    try:
        completed = run_hidden(
            [binary, "--issuer", coros_issuer_for_region(resolved_region), "apply-openclaw"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=runtime_env,
        )
    except Exception as exc:
        return _diag("openclaw", "warning", f"OpenClaw 注册失败或被跳过: {exc}")
    if int(completed.returncode) != 0:
        return _diag("openclaw", "warning", "OpenClaw 注册失败或被跳过；这不会影响脉图同步。")
    return _diag("openclaw", "ok", "OpenClaw 注册成功。")


def login_command(*, region: str | None = None, base_dir: Path | str | None = None) -> list[str]:
    resolved_region = resolve_coros_region(region)
    paths = get_coros_skill_paths(base_dir)
    if sys.platform.startswith("win"):
        if not paths.install_mcp_cmd.is_file():
            raise CorosSkillNotFoundError(f"未找到 COROS Windows 授权脚本: {paths.install_mcp_cmd}")
        return [str(paths.install_mcp_cmd), "--region", resolved_region]
    return ["bash", str(paths.install_mcp), "--region", resolved_region]


def _diag(name: str, status: str, message: str) -> dict[str, str]:
    return {"name": name, "status": status, "message": _sanitize_coros_text(message)}


def _sanitize_coros_text(value: Any, *, max_chars: int | None = None) -> str:
    text = str(value or "")
    if not text:
        return ""
    text = re.sub(
        r"(?i)(access_token|refresh_token|id_token|authorization|api[_-]?key|password|passwd|mfa_code|mfa|otp|cookie|secret)(\s*[:=]\s*)([^\s,;\"'}]+)",
        "[redacted]",
        text,
    )
    text = re.sub(
        r'(?i)("?(?:access_token|refresh_token|id_token|authorization|api[_-]?key|password|passwd|mfa_code|mfa|otp|cookie|secret)"?\s*:\s*")[^"]*(")',
        '"[redacted]"',
        text,
    )
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1***", text)
    text = re.sub(r"(?i)\b(traceback|stacktrace)\b", "[trace redacted]", text)
    text = re.sub(
        r"(?i)([?&])(?:access_token|refresh_token|id_token|authorization|api_key|password|mfa|otp|cookie|secret)=[^&\s]+",
        r"\1[redacted]",
        text,
    )
    if max_chars is not None and len(text) > max_chars:
        head = max_chars // 2
        tail = max_chars - head
        text = text[:head] + "\n...\n" + text[-tail:]
    return text


def sanitize_coros_value(value: Any, *, max_text_chars: int | None = ERROR_SNIPPET_CHARS) -> Any:
    if isinstance(value, str):
        return _sanitize_coros_text(value, max_chars=max_text_chars)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [sanitize_coros_value(item, max_text_chars=max_text_chars) for item in value]
    if isinstance(value, tuple):
        return [sanitize_coros_value(item, max_text_chars=max_text_chars) for item in value]
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in SENSITIVE_COROS_KEYS:
                continue
            clean[key_text] = sanitize_coros_value(item, max_text_chars=max_text_chars)
        return clean
    return value


def _run_keepalive_print_config(
    paths: CorosSkillPaths,
    region: str,
    timeout: int = 5,
    *,
    node_binary: str = "node",
    token_root: Path | str | None = None,
) -> tuple[str, str, str, dict[str, str]]:
    command = [node_binary or "node", str(paths.skill_dir / "scripts" / "coros-mcp-keepalive.js"), "--region", region, "--print-config"]
    try:
        completed = run_hidden(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=build_coros_runtime_env(token_root=token_root),
            cwd=str((paths.skill_dir / "scripts").resolve()),
        )
    except subprocess.TimeoutExpired:
        return "", "", "", _diag("keepalive_config", "failed", "COROS keepalive 区域配置检查超时")
    except OSError as exc:
        return "", "", "", _diag("keepalive_config", "failed", f"COROS keepalive 区域配置检查失败: {exc}")

    if int(completed.returncode) != 0:
        detail = _error_snippet(str(completed.stderr or completed.stdout or ""))
        suffix = f": {detail}" if detail else ""
        return "", "", "", _diag("keepalive_config", "failed", f"COROS keepalive 区域配置不可用{suffix}")
    try:
        payload = json.loads(str(completed.stdout or "").strip())
    except json.JSONDecodeError:
        return "", "", "", _diag("keepalive_config", "failed", "COROS keepalive --print-config 未返回合法 JSON")

    keepalive_region = str(payload.get("region") or "")
    keepalive_mcp_url = str(payload.get("mcpUrl") or "")
    keepalive_token_path = str(payload.get("tokenPath") or "")
    expected_token_path = str(default_mcp_token_path(region, token_root))
    if keepalive_region != region:
        return keepalive_region, keepalive_mcp_url, keepalive_token_path, _diag(
            "keepalive_config",
            "failed",
            f"COROS keepalive 区域不一致: 配置 {region}，脚本 {keepalive_region}",
        )
    if keepalive_token_path and Path(keepalive_token_path).expanduser() != Path(expected_token_path).expanduser():
        return keepalive_region, keepalive_mcp_url, keepalive_token_path, _diag(
            "keepalive_config",
            "failed",
            f"COROS keepalive token 路径不一致: Python {expected_token_path}，Node {keepalive_token_path}",
        )
    return keepalive_region, keepalive_mcp_url, keepalive_token_path, _diag(
        "keepalive_config",
        "ok",
        f"COROS keepalive 已按 {region} 区域解析 token 路径: {expected_token_path}",
    )


def check_auth_status(
    *,
    region: str | None = None,
    base_dir: Path | str | None = None,
    token_root: Path | str | None = None,
    keepalive_timeout: int = 5,
) -> CorosAuthStatus:
    try:
        resolved_region = resolve_coros_region(region)
    except CorosSyncError as exc:
        return CorosAuthStatus(
            ok=False,
            region=str(region or os.environ.get("COROS_REGION") or "").strip().lower(),
            status="invalid_region",
            token_path="",
            message=str(exc),
            login_command=[],
            mcp_authorized=False,
            node_available=False,
            skill_available=False,
            diagnostics=[_diag("region", "failed", str(exc))],
        )

    token_path = default_mcp_token_path(resolved_region, token_root)
    diagnostics = [_diag("region", "ok", f"COROS 区域有效: {resolved_region}")]
    try:
        command = login_command(region=resolved_region, base_dir=base_dir)
        paths = get_coros_skill_paths(base_dir)
        diagnostics.append(_diag("skill", "ok", "已找到 COROS skill 脚本"))
    except CorosSkillNotFoundError as exc:
        diagnostics.append(_diag("skill", "failed", str(exc)))
        return CorosAuthStatus(
            ok=False,
            region=resolved_region,
            status="skill_missing",
            token_path=str(token_path),
            message=str(exc),
            login_command=[],
            mcp_authorized=False,
            node_available=bool(discover_node_binary()),
            skill_available=False,
            diagnostics=diagnostics,
        )

    node_path = discover_node_binary()
    node_available = bool(node_path)
    if not node_available:
        diagnostics.append(_diag("node", "failed", "未检测到 Node.js"))
        diagnostics.append(_diag("mcp_token", "failed" if not token_path.is_file() else "ok", f"MCP token 路径: {token_path}"))
        return CorosAuthStatus(
            ok=False,
            region=resolved_region,
            status="node_missing",
            token_path=str(token_path),
            message="未检测到 Node.js，无法运行 COROS 授权和 MCP 脚本。",
            login_command=command,
            mcp_authorized=False,
            node_available=False,
            skill_available=True,
            node_path="",
            openclaw_node_binary="",
            openclaw_mjs=discover_openclaw_mjs(),
            diagnostics=diagnostics,
        )

    diagnostics.append(_diag("node", "ok", f"Node.js 可用: {node_path}"))
    openclaw_node_binary = str(os.environ.get("QCLAW_CLI_NODE_BINARY") or node_path)
    openclaw_mjs = discover_openclaw_mjs()
    if openclaw_mjs:
        diagnostics.append(_diag("openclaw_runtime", "ok", f"OpenClaw runtime 可注入: node={openclaw_node_binary}, mjs={openclaw_mjs}"))
    else:
        diagnostics.append(_diag("openclaw_runtime", "warning", "未找到 QCLAW_CLI_OPENCLAW_MJS；COROS 授权仍可完成，但注册 OpenClaw 可能需要手动配置。"))
    keepalive_region, keepalive_mcp_url, keepalive_token_path, keepalive_diag = _run_keepalive_print_config(
        paths,
        resolved_region,
        timeout=keepalive_timeout,
        node_binary=node_path,
        token_root=token_root,
    )
    diagnostics.append(keepalive_diag)
    mcp_authorized = token_path.is_file()
    diagnostics.append(_diag(
        "mcp_token",
        "ok" if mcp_authorized else "failed",
        f"{'已检测到' if mcp_authorized else '未检测到'} COROS MCP token: {token_path}",
    ))
    if keepalive_diag.get("status") != "ok":
        return CorosAuthStatus(
            ok=False,
            region=resolved_region,
            status="keepalive_invalid",
            token_path=str(token_path),
            message=str(keepalive_diag.get("message") or "COROS keepalive 配置不可用，请回配置页重新检查授权状态。"),
            login_command=command,
            mcp_authorized=mcp_authorized,
            node_available=True,
            skill_available=True,
            node_path=node_path,
            openclaw_node_binary=openclaw_node_binary,
            openclaw_mjs=openclaw_mjs,
            keepalive_region=keepalive_region,
            keepalive_mcp_url=keepalive_mcp_url,
            keepalive_token_path=keepalive_token_path,
            diagnostics=diagnostics,
        )
    if not mcp_authorized:
        return CorosAuthStatus(
            ok=False,
            region=resolved_region,
            status="missing_token",
            token_path=str(token_path),
            message=f"请先登录 COROS（{resolved_region}），未检测到 MCP 授权 token。",
            login_command=command,
            mcp_authorized=False,
            node_available=True,
            skill_available=True,
            node_path=node_path,
            openclaw_node_binary=openclaw_node_binary,
            openclaw_mjs=openclaw_mjs,
            keepalive_region=keepalive_region,
            keepalive_mcp_url=keepalive_mcp_url,
            keepalive_token_path=keepalive_token_path,
            diagnostics=diagnostics,
        )

    return CorosAuthStatus(
        ok=True,
        region=resolved_region,
        status="authorized",
        token_path=str(token_path),
        message=f"已检测到 COROS MCP 授权（{resolved_region}）。",
        login_command=command,
        mcp_authorized=True,
        node_available=True,
        skill_available=True,
        node_path=node_path,
        openclaw_node_binary=openclaw_node_binary,
        openclaw_mjs=openclaw_mjs,
        keepalive_region=keepalive_region,
        keepalive_mcp_url=keepalive_mcp_url,
        keepalive_token_path=keepalive_token_path,
        diagnostics=diagnostics,
    )


def ensure_auth_available(
    *,
    region: str | None = None,
    base_dir: Path | str | None = None,
    token_root: Path | str | None = None,
) -> CorosAuthStatus:
    status = check_auth_status(region=region, base_dir=base_dir, token_root=token_root)
    if status.ok:
        return status
    code_map = {
        "missing_token": "coros_auth_required",
        "node_missing": "coros_node_missing",
        "skill_missing": "coros_skill_not_found",
        "keepalive_invalid": "coros_keepalive_invalid",
        "invalid_region": "invalid_coros_region",
    }
    code = code_map.get(status.status, "coros_auth_required")
    if code == "coros_auth_required":
        raise CorosAuthRequiredError(status.message)
    if code == "coros_skill_not_found":
        raise CorosSkillNotFoundError(status.message)
    raise CorosSyncError(status.message, code=code)


def _error_snippet(value: str) -> str:
    text = _sanitize_coros_text(value).strip()
    if len(text) <= ERROR_SNIPPET_CHARS:
        return text
    head = ERROR_SNIPPET_CHARS // 2
    tail = ERROR_SNIPPET_CHARS - head
    return text[:head] + "\n...\n" + text[-tail:]


def _looks_like_auth_required(text: str) -> bool:
    clean = str(text or "").lower()
    if not clean:
        return False
    auth_markers = (
        "coros 授权",
        "coros 未登录",
        "请先登录 coros",
        "未检测到 mcp 授权 token",
        "missing_token",
        "auth_required",
        "unauthorized",
        "authentication failed",
        "authorization",
        "access token",
        "token expired",
    )
    return any(marker in clean for marker in auth_markers)


def _classify_coros_error(exc: Exception, context: dict[str, Any] | None = None) -> str:
    context_text = str((context or {}).get("operation") or "").lower()
    current = str(getattr(exc, "code", "") or "").strip()
    if current and current != "coros_sync_error":
        if current == "coros_script_failed" and "profile" in context_text:
            return "coros_profile_sync_failed"
        return current
    if isinstance(exc, CorosAuthRequiredError):
        return "coros_auth_required"
    if isinstance(exc, CorosSkillNotFoundError):
        return "coros_skill_not_found"
    if isinstance(exc, CorosJsonParseError) or isinstance(exc, json.JSONDecodeError):
        return "coros_json_parse_error"
    if isinstance(exc, CorosFitDownloadError):
        return str(getattr(exc, "code", "") or "coros_fit_download_failed")
    if isinstance(exc, (FileNotFoundError, OSError)):
        return "coros_node_missing"
    text = str(exc or "").lower()
    if _looks_like_auth_required(text):
        return "coros_auth_required"
    if "session not found" in text or "context pollution" in text or "mcp" in text and "unavailable" in text:
        return "coros_mcp_unavailable"
    if "json" in text or "decode" in text:
        return "coros_json_parse_error"
    if "keepalive" in text:
        return "coros_keepalive_invalid"
    if "profile" in context_text or "画像" in text:
        return "coros_profile_sync_failed"
    if "fit" in context_text or "download" in context_text:
        return "coros_fit_download_failed"
    return "unknown"


def normalize_coros_error(exc: Exception, context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = dict(context or {})
    code = _classify_coros_error(exc, context)
    raw_detail = _error_snippet(str(exc or ""))
    message = COROS_USER_MESSAGES.get(code, COROS_USER_MESSAGES["unknown"])
    if raw_detail and code in {"invalid_coros_region"}:
        message = raw_detail
    diagnostics: dict[str, Any] = {
        "provider": "coros",
    }
    for key in (
        "region",
        "node_available",
        "node_path",
        "skill_available",
        "keepalive_path",
        "keepalive_region",
        "keepalive_mcp_url",
        "keepalive_token_path",
        "token_path",
        "exit_code",
        "failed_tool_name",
        "operation",
    ):
        if key in context and context[key] not in (None, ""):
            diagnostics[key] = context[key]
    if raw_detail:
        diagnostics["error_summary"] = raw_detail
    if isinstance(exc, CorosSyncError):
        diagnostics["source_code"] = str(getattr(exc, "code", "") or "")
    payload = {
        "provider": "coros",
        "provider_error_code": code,
        "message": message,
        "action_hint": COROS_ACTION_HINTS.get(code, COROS_ACTION_HINTS["unknown"]),
        "diagnostics": diagnostics,
    }
    return sanitize_coros_value(payload, max_text_chars=ERROR_SNIPPET_CHARS)


def run_coros_script(
    script_path: Path | str,
    args: list[str] | tuple[str, ...] | None = None,
    *,
    timeout: int = DEFAULT_TIMEOUT_SEC,
    env: dict[str, str] | None = None,
) -> CorosScriptResult:
    script = Path(script_path).expanduser().resolve()
    if not script.is_file():
        raise CorosSkillNotFoundError(f"未找到 COROS skill 脚本: {script}")

    command = [sys.executable, str(script), *[str(arg) for arg in (args or [])]]
    try:
        completed = run_hidden(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=str(script.parent),
        )
    except subprocess.TimeoutExpired as exc:
        raise CorosScriptFailed(f"COROS 脚本超时未返回 ({timeout}s): {script.name}") from exc
    except OSError as exc:
        raise CorosScriptFailed(f"COROS 脚本启动失败: {exc}") from exc

    result = CorosScriptResult(
        command=command,
        stdout=str(completed.stdout or ""),
        stderr=str(completed.stderr or ""),
        returncode=int(completed.returncode),
    )
    if result.returncode != 0:
        detail = _error_snippet(result.stderr or result.stdout)
        suffix = f": {detail}" if detail else ""
        if _looks_like_auth_required(detail):
            raise CorosAuthRequiredError(f"COROS 授权不可用或已失效，请到配置页完成授权{suffix}")
        raise CorosScriptFailed(f"COROS 脚本执行失败 (exit {result.returncode}){suffix}")
    return result


def _parse_json_stdout(stdout: str) -> Any:
    text = str(stdout or "").strip()
    if not text:
        raise CorosJsonParseError("COROS 脚本未输出 JSON")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise CorosJsonParseError(f"COROS JSON 解析失败: {exc}") from exc


@contextmanager
def _temporary_sys_path(path: Path) -> Iterator[None]:
    text = str(path)
    inserted = False
    if text not in sys.path:
        sys.path.insert(0, text)
        inserted = True
    try:
        yield
    finally:
        if inserted:
            try:
                sys.path.remove(text)
            except ValueError:
                pass


@contextmanager
def _temporary_environ(values: dict[str, str]) -> Iterator[None]:
    old: dict[str, str | None] = {key: os.environ.get(key) for key in values}
    try:
        os.environ.update({str(key): str(value) for key, value in values.items()})
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _load_skill_module(script: Path, prefix: str) -> Any:
    if not script.is_file():
        raise CorosSkillNotFoundError(f"未找到 COROS skill 脚本: {script}")
    module_name = f"_fitvault_{prefix}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, script)
    if spec is None or spec.loader is None:
        raise CorosScriptFailed(f"COROS skill 模块加载失败: {script}")
    module = importlib.util.module_from_spec(spec)
    with _temporary_sys_path(script.parent):
        try:
            spec.loader.exec_module(module)
        except CorosSyncError:
            raise
        except Exception as exc:
            detail = _error_snippet(str(exc))
            if _looks_like_auth_required(detail):
                raise CorosAuthRequiredError(f"COROS 授权不可用或已失效，请到配置页完成授权: {detail}") from exc
            raise CorosScriptFailed(f"COROS skill 模块执行失败: {detail}") from exc
    return module


def _sync_profile_in_process(paths: CorosSkillPaths, *, region: str) -> list[dict[str, Any]]:
    env = build_coros_runtime_env()
    env["COROS_REGION"] = region
    module = _load_skill_module(paths.profile_runner, "coros_profile")
    build_profile = getattr(module, "build_profile", None)
    if not callable(build_profile):
        raise CorosScriptFailed("COROS skill 缺少 build_profile 可调用入口")
    try:
        with _temporary_environ(env):
            parsed = build_profile()
    except CorosSyncError:
        raise
    except Exception as exc:
        detail = _error_snippet(str(exc))
        if _looks_like_auth_required(detail):
            raise CorosAuthRequiredError(f"COROS 授权不可用或已失效，请到配置页完成授权: {detail}") from exc
        raise CorosScriptFailed(f"COROS 画像同步执行失败: {detail}") from exc
    if not isinstance(parsed, list):
        raise CorosJsonParseError("COROS 画像同步返回的不是 JSON 数组")
    if not all(isinstance(item, dict) for item in parsed):
        raise CorosJsonParseError("COROS 画像同步 JSON 数组元素必须是对象")
    return parsed


def sync_profile_json(
    *,
    region: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SEC,
    base_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    resolved_region = resolve_coros_region(region)
    ensure_auth_available(region=resolved_region, base_dir=base_dir)
    paths = get_coros_skill_paths(base_dir)
    return _sync_profile_in_process(paths, region=resolved_region)


def start_login(
    *,
    region: str | None = None,
    base_dir: Path | str | None = None,
    timeout: int | None = None,
) -> CorosLoginResult:
    try:
        resolved_region = resolve_coros_region(region)
    except CorosSyncError as exc:
        return CorosLoginResult(
            ok=False,
            region=str(region or os.environ.get("COROS_REGION") or "").strip().lower(),
            status="invalid_region",
            command=[],
            stdout="",
            stderr="",
            message=str(exc),
        )

    try:
        command = login_command(region=resolved_region, base_dir=base_dir)
    except CorosSkillNotFoundError as exc:
        return CorosLoginResult(
            ok=False,
            region=resolved_region,
            status="skill_missing",
            command=[],
            stdout="",
            stderr="",
            message=str(exc),
        )

    if sys.platform == "darwin":
        cwd = str(Path(command[1]).resolve().parent) if len(command) > 1 else str(Path.cwd())
        runtime_env = build_coros_runtime_env()
        env_prefix_parts = []
        for key in ("PATH", "QCLAW_CLI_NODE_BINARY", "QCLAW_CLI_OPENCLAW_MJS", "MAITU_BUNDLED_NODE_DIR"):
            value = str(runtime_env.get(key) or "").strip()
            if value:
                env_prefix_parts.append(f"export {key}={shlex.quote(value)}")
        env_prefix = "; ".join(env_prefix_parts)
        if env_prefix:
            env_prefix += "; "
        shell_command = (
            f"cd {shlex.quote(cwd)} && "
            f"{env_prefix}"
            f"{' '.join(shlex.quote(part) for part in command)}; "
            "echo; echo 'COROS 授权流程结束后，请回到脉图点击检查状态。'; "
            "printf '按回车关闭窗口...'; read _"
        )
        escaped = shell_command.replace("\\", "\\\\").replace('"', '\\"')
        osa = [
            "osascript",
            "-e",
            'tell application "Terminal"',
            "-e",
            "activate",
            "-e",
            f'do script "{escaped}"',
            "-e",
            "end tell",
        ]
        try:
            popen_hidden(osa, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            return CorosLoginResult(
                ok=False,
                region=resolved_region,
                status="launch_failed",
                command=command,
                stdout="",
                stderr="",
                message=f"COROS 授权终端启动失败: {exc}",
            )
        return CorosLoginResult(
            ok=True,
            region=resolved_region,
            status="launched",
            command=command,
            stdout="",
            stderr="",
            message=f"已打开终端窗口，请在终端完成 COROS 授权（{resolved_region}）。",
        )

    if sys.platform.startswith("win"):
        return CorosLoginResult(
            ok=False,
            region=resolved_region,
            status="unsupported_legacy_login",
            command=command,
            stdout="",
            stderr="",
            message="Windows 版 COROS 授权请使用账号连接中心；旧登录入口已停用以避免打开命令行窗口。",
        )

    try:
        completed = run_hidden(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=build_coros_runtime_env(),
            cwd=str(Path(command[1]).resolve().parent) if len(command) > 1 else None,
        )
    except subprocess.TimeoutExpired as exc:
        return CorosLoginResult(
            ok=False,
            region=resolved_region,
            status="timeout",
            command=command,
            stdout=str(exc.stdout or ""),
            stderr=str(exc.stderr or ""),
            message=f"COROS 授权超时 ({timeout}s)",
        )
    except OSError as exc:
        return CorosLoginResult(
            ok=False,
            region=resolved_region,
            status="launch_failed",
            command=command,
            stdout="",
            stderr="",
            message=f"COROS 授权脚本启动失败: {exc}",
        )

    stdout = str(completed.stdout or "")
    stderr = str(completed.stderr or "")
    if int(completed.returncode) != 0:
        detail = _error_snippet(stderr or stdout)
        suffix = f": {detail}" if detail else ""
        return CorosLoginResult(
            ok=False,
            region=resolved_region,
            status="failed",
            command=command,
            stdout=stdout,
            stderr=stderr,
            message=f"COROS 授权失败 (exit {int(completed.returncode)}){suffix}",
        )

    return CorosLoginResult(
        ok=True,
        region=resolved_region,
        status="completed",
        command=command,
        stdout=stdout,
        stderr=stderr,
        message=f"COROS 授权已完成（{resolved_region}）。",
    )


def _issuer_for_region(region: str) -> str:
    return {
        "cn": "https://mcpcn.coros.com",
        "us": "https://mcpus.coros.com",
        "eu": "https://mcpeu.coros.com",
    }[resolve_coros_region(region)]


def _format_mcp_day(value: str | date) -> str:
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    text = str(value or "").strip()
    if not text:
        return ""
    if re_match := re.match(r"^\d{8}$", text):
        return re_match.group(0)
    try:
        return date.fromisoformat(text).strftime("%Y%m%d")
    except ValueError as exc:
        raise CorosFitDownloadError(f"无效的 COROS FIT 日期: {text}", code="coros_fit_download_failed") from exc


def _coros_mcp_command(region: str, tool_name: str, arguments: dict[str, Any]) -> list[str]:
    paths = get_coros_skill_paths()
    node_path = discover_node_binary()
    if not node_path:
        raise CorosFitDownloadError(
            "未检测到 Node.js，无法调用 COROS MCP keepalive；请使用包含 bundled Node 的安装包。",
            code="coros_node_missing",
        )
    keepalive = paths.skill_dir / "scripts" / "coros-mcp-keepalive.js"
    if not keepalive.is_file():
        raise CorosFitDownloadError(f"未找到 COROS keepalive 脚本: {keepalive}", code="coros_skill_not_found")
    return [
        node_path,
        str(keepalive),
        "--region",
        resolve_coros_region(region),
        "call",
        tool_name,
        json.dumps(arguments, ensure_ascii=False, separators=(",", ":")),
    ]


def run_coros_mcp_tool(
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    region: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SEC,
) -> Any:
    resolved_region = resolve_coros_region(region)
    command = _coros_mcp_command(resolved_region, tool_name, arguments or {})
    node_path = command[0]
    keepalive_path = command[1]
    try:
        completed = run_hidden(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=build_coros_runtime_env(),
            cwd=str(Path(keepalive_path).resolve().parent),
        )
    except subprocess.TimeoutExpired as exc:
        raise CorosFitDownloadError(f"COROS MCP 工具调用超时 ({timeout}s): {tool_name}") from exc
    except OSError as exc:
        raise CorosFitDownloadError(
            f"COROS MCP keepalive 启动失败: {_error_snippet(str(exc))}; node={node_path}; keepalive={keepalive_path}",
            code="coros_node_missing",
        ) from exc

    stdout = str(completed.stdout or "")
    stderr = str(completed.stderr or "")
    if int(completed.returncode) != 0:
        detail = _error_snippet(stderr or stdout)
        suffix = f": {detail}" if detail else ""
        if _looks_like_auth_required(detail):
            raise CorosAuthRequiredError(f"COROS 授权不可用或已失效，请到配置页完成授权{suffix}")
        lower_detail = detail.lower()
        if "session not found" in lower_detail or "context pollution" in lower_detail:
            raise CorosFitDownloadError(
                f"COROS MCP 服务暂不可用 (exit {int(completed.returncode)}): {tool_name}{suffix}",
                code="coros_mcp_unavailable",
            )
        raise CorosFitDownloadError(
            f"COROS MCP 工具调用失败 (exit {int(completed.returncode)}): {tool_name}; "
            f"region={resolved_region}; node={node_path}; keepalive={keepalive_path}{suffix}"
        )
    try:
        return _parse_json_stdout(stdout)
    except CorosJsonParseError:
        text = stdout.strip()
        if not text:
            raise
        return {"content": [{"type": "text", "text": text}]}


def _iter_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_dicts(child)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_dicts(item)


def _safe_fit_name(base: str, index: int) -> str:
    clean = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in str(base or "").strip())
    clean = clean.strip("._") or f"coros_activity_{index}"
    if not clean.lower().endswith(".fit"):
        clean += ".fit"
    return clean


def _decode_blob(item: dict[str, Any]) -> bytes | None:
    for key in ("blob", "data", "base64", "bytes"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            try:
                return base64.b64decode(value, validate=False)
            except (ValueError, TypeError):
                continue
    return None


def _extract_fit_blobs(payload: Any) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for item in _iter_dicts(payload):
        mime = str(item.get("mimeType") or item.get("mime_type") or item.get("mediaType") or "").lower()
        uri = str(item.get("uri") or item.get("name") or item.get("filename") or item.get("fileName") or "")
        if "fit" not in mime and not uri.lower().endswith(".fit"):
            continue
        data = _decode_blob(item)
        if not data:
            continue
        files.append({
            "filename": _safe_fit_name(item.get("filename") or item.get("fileName") or item.get("name") or uri, len(files) + 1),
            "data": data,
            "source": "downloadActivityFitFiles",
        })
    return files


def _extract_urls(payload: Any) -> list[str]:
    urls: list[str] = []

    def add(text: str) -> None:
        value = str(text or "").strip()
        if value.startswith("http://") or value.startswith("https://"):
            urls.append(value)

    for item in _iter_dicts(payload):
        for key in ("url", "downloadUrl", "download_url", "fitUrl", "fit_url", "href"):
            if isinstance(item.get(key), str):
                add(item[key])
            elif isinstance(item.get(key), list):
                for value in item[key]:
                    if isinstance(value, str):
                        add(value)
        for key in ("urls", "downloadUrls", "download_urls"):
            if isinstance(item.get(key), list):
                for value in item[key]:
                    if isinstance(value, str):
                        add(value)
        text = item.get("text")
        if isinstance(text, str):
            try:
                nested = json.loads(text)
            except json.JSONDecodeError:
                for part in text.replace("\n", " ").split():
                    add(part)
            else:
                urls.extend(_extract_urls(nested))
    return list(dict.fromkeys(urls))


def _extract_text_payload(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()

    chunks: list[str] = []
    for item in _iter_dicts(payload):
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            value = text.strip()
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                chunks.append(value)
            else:
                chunks.append(decoded if isinstance(decoded, str) else value)
    return "\n".join(chunks)


def _extract_sport_records(payload: Any, limit: int = MAX_COROS_FIT_DOWNLOAD_LIMIT) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for item in _iter_dicts(payload):
        label_id = item.get("labelId") or item.get("label_id") or item.get("activityLabelId")
        sport_type = item.get("sportType") or item.get("sport_type") or item.get("sportTypeCode")
        if label_id is None or sport_type is None:
            continue
        try:
            sport_type_int = int(sport_type)
        except (TypeError, ValueError):
            continue
        record = {"labelId": str(label_id), "sportType": sport_type_int}
        for key in ("title", "name", "date", "startTimestamp", "endTimestamp"):
            if item.get(key) is not None:
                record[key] = item.get(key)
        if record not in records:
            records.append(record)

    text = _extract_text_payload(payload)
    if text:
        pattern = re.compile(
            r"(?:^|\n)\s*(\d+)\.\s*(.*?)\s+[—-]\s+(\d{4}-\d{2}-\d{2}).*?"
            r"LabelId:\s*([A-Za-z0-9_-]+).*?SportType:\s*(\d+)",
            re.S,
        )
        for match in pattern.finditer(text):
            record = {
                "index": int(match.group(1)),
                "title": match.group(2).strip(),
                "date": match.group(3),
                "labelId": match.group(4),
                "sportType": int(match.group(5)),
            }
            if not any(item["labelId"] == record["labelId"] and item["sportType"] == record["sportType"] for item in records):
                records.append(record)

    return records[: max(1, min(int(limit or MAX_COROS_FIT_DOWNLOAD_LIMIT), MAX_COROS_FIT_DOWNLOAD_LIMIT))]


def _query_sport_records_for_fit(
    *,
    start_day: str,
    end_day: str,
    region: str,
    limit: int,
    timeout: int,
) -> list[dict[str, Any]]:
    payload = run_coros_mcp_tool(
        "querySportRecords",
        {
            "startDate": start_day,
            "endDate": end_day,
            "sportTypeCodes": [65535],
            "minDistanceKm": None,
            "maxDistanceKm": None,
            "minDurationMinutes": None,
            "maxDurationMinutes": None,
            "maxAveragePace": "",
            "locationKeyword": "",
            "limit": limit,
            "timezone": "Asia/Shanghai",
        },
        region=region,
        timeout=timeout,
    )
    return _extract_sport_records(payload, limit=limit)


def _write_fit_file(output_dir: Path, filename: str, data: bytes, index: int) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / _safe_fit_name(filename, index)
    if path.exists():
        return {"file": str(path), "status": "skipped", "reason": "exists"}
    path.write_bytes(data)
    return {"file": str(path), "status": "downloaded", "bytes": len(data)}


def _download_url_to_fit(output_dir: Path, url: str, index: int, timeout: int) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_fit_name(Path(urllib.parse.urlparse(url).path).name or f"coros_activity_{index}.fit", index)
    path = output_dir / filename
    if path.exists():
        return {"file": str(path), "status": "skipped", "reason": "exists", "url": url}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "fit-vault-coros-sync/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"file": str(path), "status": "failed", "error": str(exc), "url": url}
    path.write_bytes(data)
    return {"file": str(path), "status": "downloaded", "bytes": len(data), "url": url}


def _summarize_fit_records(
    *,
    provider: str,
    region: str,
    mode: str,
    strategy: str,
    start_date: str,
    end_date: str,
    output_dir: Path,
    records: list[dict[str, Any]],
    errors: list[dict[str, Any]] | None = None,
    limit: int = MAX_COROS_FIT_DOWNLOAD_LIMIT,
    searched: int | None = None,
) -> dict[str, Any]:
    error_items = errors or [item for item in records if item.get("status") == "failed"]
    return {
        "ok": not any(item.get("status") == "failed" for item in records) and not any(item.get("status") == "failed" for item in error_items),
        "provider": provider,
        "region": region,
        "mode": mode,
        "strategy": strategy,
        "start_date": start_date,
        "end_date": end_date,
        "limit": limit,
        "searched": len(records) if searched is None else searched,
        "downloaded": sum(1 for item in records if item.get("status") == "downloaded"),
        "skipped": sum(1 for item in records if item.get("status") == "skipped"),
        "failed": sum(1 for item in records if item.get("status") == "failed") + sum(1 for item in error_items if item.get("status") == "failed"),
        "output_dir": str(output_dir),
        "files": records,
        "errors": error_items,
    }


def download_fit_json(
    *,
    start_date: str,
    end_date: str,
    output_dir: Path | str,
    region: str | None = None,
    limit: int = MAX_COROS_FIT_DOWNLOAD_LIMIT,
    timeout: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    resolved_region = resolve_coros_region(region)
    ensure_auth_available(region=resolved_region)
    start_day = _format_mcp_day(start_date)
    end_day = _format_mcp_day(end_date)
    safe_limit = max(1, min(int(limit or MAX_COROS_FIT_DOWNLOAD_LIMIT), MAX_COROS_FIT_DOWNLOAD_LIMIT))
    output_path = Path(output_dir).expanduser()
    args = {"startDate": start_day, "endDate": end_day, "limit": safe_limit}
    errors: list[dict[str, Any]] = []

    try:
        binary_payload = run_coros_mcp_tool(
            "downloadActivityFitFiles",
            args,
            region=resolved_region,
            timeout=timeout,
        )
        blobs = _extract_fit_blobs(binary_payload)
    except CorosAuthRequiredError:
        raise
    except CorosFitDownloadError as exc:
        blobs = []
        errors.append({"status": "failed", "stage": "date_range_binary", "error": str(exc)})
    records: list[dict[str, Any]] = []
    for index, item in enumerate(blobs[:safe_limit], start=1):
        records.append(_write_fit_file(output_path, item["filename"], item["data"], index))
    if records:
        return _summarize_fit_records(
            provider="coros",
            region=resolved_region,
            mode="date_range",
            strategy="date_range_binary",
            start_date=date.fromisoformat(str(start_date)).isoformat() if "-" in str(start_date) else start_day,
            end_date=date.fromisoformat(str(end_date)).isoformat() if "-" in str(end_date) else end_day,
            output_dir=output_path,
            records=records,
            limit=safe_limit,
        )

    try:
        url_payload = run_coros_mcp_tool(
            "queryActivityFitFileDownloadUrls",
            args,
            region=resolved_region,
            timeout=timeout,
        )
        urls = _extract_urls(url_payload)[:safe_limit]
    except CorosAuthRequiredError:
        raise
    except CorosFitDownloadError as exc:
        urls = []
        errors.append({"status": "failed", "stage": "date_range_url", "error": str(exc)})
    if urls:
        for index, url in enumerate(urls, start=1):
            records.append(_download_url_to_fit(output_path, url, index, timeout))
        return _summarize_fit_records(
            provider="coros",
            region=resolved_region,
            mode="date_range",
            strategy="date_range_url",
            start_date=str(start_date),
            end_date=str(end_date),
            output_dir=output_path,
            records=records,
            limit=safe_limit,
        )

    try:
        sport_records = _query_sport_records_for_fit(
            start_day=start_day,
            end_day=end_day,
            region=resolved_region,
            limit=safe_limit,
            timeout=timeout,
        )
    except CorosAuthRequiredError:
        raise
    except CorosFitDownloadError as exc:
        sport_records = []
        errors.append({"status": "failed", "stage": "query_sport_records", "error": str(exc)})
    if not sport_records:
        return _summarize_fit_records(
            provider="coros",
            region=resolved_region,
            mode="date_range",
            strategy="sport_records_empty",
            start_date=str(start_date),
            end_date=str(end_date),
            output_dir=output_path,
            records=[],
            errors=errors or [{"status": "failed", "stage": "query_sport_records", "error": "COROS MCP 未返回活动记录或可下载 FIT 文件"}],
            limit=safe_limit,
            searched=0,
        )

    for item in sport_records[:safe_limit]:
        label_id = item["labelId"]
        sport_type = int(item["sportType"])
        per_args = {"labelId": label_id, "sportType": sport_type}
        try:
            binary_payload = run_coros_mcp_tool(
                "downloadActivityFitFiles",
                per_args,
                region=resolved_region,
                timeout=timeout,
            )
            blobs = _extract_fit_blobs(binary_payload)
        except CorosAuthRequiredError:
            raise
        except CorosFitDownloadError as exc:
            blobs = []
            errors.append({"status": "failed", "stage": "sport_records_binary", "labelId": label_id, "sportType": sport_type, "error": str(exc)})
        for blob in blobs:
            record = _write_fit_file(output_path, blob["filename"], blob["data"], len(records) + 1)
            record["source"] = "downloadActivityFitFiles"
            record["labelId"] = label_id
            record["sportType"] = sport_type
            records.append(record)
        if blobs:
            continue
        try:
            url_payload = run_coros_mcp_tool(
                "queryActivityFitFileDownloadUrls",
                per_args,
                region=resolved_region,
                timeout=timeout,
            )
            urls = _extract_urls(url_payload)
        except CorosAuthRequiredError:
            raise
        except CorosFitDownloadError as exc:
            urls = []
            errors.append({"status": "failed", "stage": "sport_records_url", "labelId": label_id, "sportType": sport_type, "error": str(exc)})
        if not urls:
            errors.append({"status": "failed", "stage": "sport_records_download", "labelId": label_id, "sportType": sport_type, "error": "未返回 FIT blob 或下载 URL"})
            continue
        for url in urls[: max(1, safe_limit - len(records))]:
            record = _download_url_to_fit(output_path, url, len(records) + 1, timeout)
            record["source"] = "queryActivityFitFileDownloadUrls"
            record["labelId"] = label_id
            record["sportType"] = sport_type
            records.append(record)
        if len(records) >= safe_limit:
            break

    strategy = "sport_records_binary" if any(item.get("source") == "downloadActivityFitFiles" for item in records) else "sport_records_url"
    return _summarize_fit_records(
        provider="coros",
        region=resolved_region,
        mode="date_range",
        strategy=strategy,
        start_date=str(start_date),
        end_date=str(end_date),
        output_dir=output_path,
        records=records,
        errors=errors,
        limit=safe_limit,
        searched=len(sport_records),
    )
