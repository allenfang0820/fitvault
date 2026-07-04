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
import tempfile
import uuid
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterator


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
    root = (
        Path(token_root).expanduser()
        if token_root is not None
        else Path(os.environ.get("COROS_MCP_TOKEN_ROOT", str(Path.home() / ".coros-mcp-skill-gateway-ts"))).expanduser()
    )
    return root / resolved_region / "token.json"


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
    candidates.extend([
        base / "node" / "bin" / "node",
        base / "node" / "node.exe",
        base / "Resources" / "node" / "bin" / "node",
        base / "Resources" / "node" / "node.exe",
        Path(sys.executable).resolve().parent / "node" / "bin" / "node",
        Path(sys.executable).resolve().parent / "node" / "node.exe",
        Path(sys.executable).resolve().parent.parent / "Resources" / "node" / "bin" / "node",
        Path(sys.executable).resolve().parent.parent / "Resources" / "node" / "node.exe",
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


def build_coros_runtime_env(env: dict[str, str] | None = None) -> dict[str, str]:
    runtime_env = dict(env or os.environ)
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
        runtime_env["PATH"] = node_dir + os.pathsep + runtime_env.get("PATH", "")
        runtime_env.setdefault("QCLAW_CLI_NODE_BINARY", node_path)
        runtime_env.setdefault("MAITU_BUNDLED_NODE_DIR", node_root)
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
    return ""


def prepare_coros_connection_runtime(
    *,
    region: str | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> CorosConnectionStepResult:
    resolved_region = resolve_coros_region(region)
    diagnostics = [_diag("region", "ok", f"COROS 区域有效: {resolved_region}")]
    node_path = discover_node_binary()
    if not node_path:
        diagnostics.append(_diag("node", "failed", "未检测到 Node.js"))
        return CorosConnectionStepResult(
            ok=False,
            status="failed",
            message="未检测到 Node.js，无法启动 COROS OAuth 连接向导。",
            node_path="",
            token_path=str(default_mcp_token_path(resolved_region)),
            diagnostics=diagnostics,
        )
    diagnostics.append(_diag("node", "ok", f"Node.js 可用: {node_path}"))
    runtime_env = build_coros_runtime_env(env)
    runtime_env.setdefault("NPM_CONFIG_PREFIX", str(Path.home() / ".maitu" / "node-global"))
    try:
        Path(runtime_env["NPM_CONFIG_PREFIX"]).expanduser().mkdir(parents=True, exist_ok=True)
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
            token_path=str(default_mcp_token_path(resolved_region)),
            diagnostics=diagnostics,
        )
    diagnostics.append(_diag("npm", "ok", f"npm 可用: {npm_path}"))

    coros_mcp_path = discover_coros_mcp_binary(runtime_env)
    if not coros_mcp_path:
        diagnostics.append(_diag("coros_mcp", "checking", "正在安装 coros-mcp"))
        try:
            completed = subprocess.run(
                [npm_path, "install", "-g", "coros-mcp"],
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
                env=runtime_env,
            )
        except subprocess.TimeoutExpired:
            diagnostics.append(_diag("coros_mcp", "failed", "coros-mcp 安装超时"))
            return CorosConnectionStepResult(False, "failed", "coros-mcp 安装超时。", node_path, npm_path, "", str(default_mcp_token_path(resolved_region)), diagnostics)
        except OSError as exc:
            diagnostics.append(_diag("coros_mcp", "failed", f"coros-mcp 安装启动失败: {exc}"))
            return CorosConnectionStepResult(False, "failed", f"coros-mcp 安装启动失败: {exc}", node_path, npm_path, "", str(default_mcp_token_path(resolved_region)), diagnostics)
        if int(completed.returncode) != 0:
            detail = _error_snippet(str(completed.stderr or completed.stdout or ""))
            diagnostics.append(_diag("coros_mcp", "failed", f"coros-mcp 安装失败: {detail}"))
            return CorosConnectionStepResult(False, "failed", "coros-mcp 安装失败。", node_path, npm_path, "", str(default_mcp_token_path(resolved_region)), diagnostics)
        coros_mcp_path = discover_coros_mcp_binary(runtime_env)
    if not coros_mcp_path:
        diagnostics.append(_diag("coros_mcp", "failed", "未找到 coros-mcp 命令"))
        return CorosConnectionStepResult(False, "failed", "coros-mcp 安装后仍不可用。", node_path, npm_path, "", str(default_mcp_token_path(resolved_region)), diagnostics)
    diagnostics.append(_diag("coros_mcp", "ok", f"coros-mcp 可用: {coros_mcp_path}"))
    return CorosConnectionStepResult(
        ok=True,
        status="checking",
        message="COROS MCP 运行环境已就绪。",
        node_path=node_path,
        npm_path=npm_path,
        coros_mcp_path=coros_mcp_path,
        token_path=str(default_mcp_token_path(resolved_region)),
        diagnostics=diagnostics,
    )


def start_coros_oauth_login(
    *,
    region: str | None = None,
    coros_mcp_path: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.Popen:
    resolved_region = resolve_coros_region(region)
    runtime_env = build_coros_runtime_env(env)
    binary = str(coros_mcp_path or discover_coros_mcp_binary(runtime_env) or "coros-mcp")
    return subprocess.Popen(
        [binary, "--issuer", coros_issuer_for_region(resolved_region), "login"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        shell=False,
        env=runtime_env,
    )


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
        completed = subprocess.run(
            [binary, "--issuer", coros_issuer_for_region(resolved_region), "apply-openclaw"],
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
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


def _windows_command_line(command: list[str]) -> str:
    return subprocess.list2cmdline([str(part) for part in command])


def _windows_command_cwd(command: list[str], fallback: Path) -> str:
    if command:
        first = Path(command[0])
        if first.name.lower() in {"python.exe", "pythonw.exe", "py.exe", "bash.exe"} and len(command) > 1:
            return str(Path(command[1]).resolve().parent)
        if first.is_file() or first.suffix.lower() in {".exe", ".cmd", ".bat"}:
            return str(first.resolve().parent)
    return str(fallback)


def _windows_console_launcher(command: list[str], cwd: str, title: str, done_message: str) -> list[str]:
    command_line = _windows_command_line(command)
    if command and Path(str(command[0])).suffix.lower() in {".cmd", ".bat"}:
        command_line = "call " + command_line
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        suffix=".cmd",
        prefix="fitvault-coros-login-",
        delete=False,
    )
    with handle:
        handle.write("@echo off\n")
        handle.write("chcp 65001 >nul\n")
        handle.write(f"cd /d {subprocess.list2cmdline([cwd])}\n")
        handle.write(f"{command_line}\n")
        handle.write("echo.\n")
        handle.write(f"echo {done_message}\n")
        handle.write("pause\n")
    return [
        "cmd.exe",
        "/d",
        "/c",
        "start",
        title,
        "cmd.exe",
        "/d",
        "/k",
        handle.name,
    ]


def _diag(name: str, status: str, message: str) -> dict[str, str]:
    return {"name": name, "status": status, "message": message}


def _run_keepalive_print_config(
    paths: CorosSkillPaths,
    region: str,
    timeout: int = 5,
    *,
    node_binary: str = "node",
) -> tuple[str, str, str, dict[str, str]]:
    command = [node_binary or "node", str(paths.skill_dir / "scripts" / "coros-mcp-keepalive.js"), "--region", region, "--print-config"]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            env=build_coros_runtime_env(),
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
    if keepalive_region != region:
        return keepalive_region, keepalive_mcp_url, keepalive_token_path, _diag(
            "keepalive_config",
            "failed",
            f"COROS keepalive 区域不一致: 配置 {region}，脚本 {keepalive_region}",
        )
    return keepalive_region, keepalive_mcp_url, keepalive_token_path, _diag(
        "keepalive_config",
        "ok",
        f"COROS keepalive 已按 {region} 区域解析",
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
    )
    diagnostics.append(keepalive_diag)
    mcp_authorized = token_path.is_file()
    diagnostics.append(_diag(
        "mcp_token",
        "ok" if mcp_authorized else "failed",
        f"{'已检测到' if mcp_authorized else '未检测到'} COROS MCP token: {token_path}",
    ))
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


def _error_snippet(value: str) -> str:
    text = str(value or "").strip()
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
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
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
            detail = str(exc)
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
        detail = str(exc)
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
            subprocess.Popen(osa, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        paths = get_coros_skill_paths(base_dir)
        cwd = _windows_command_cwd(command, paths.install_mcp_cmd.resolve().parent)
        launcher = _windows_console_launcher(
            command,
            cwd,
            "FitVault COROS Login",
            "COROS 授权流程结束后，请回到脉图点击检查状态。",
        )
        try:
            subprocess.Popen(
                launcher,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=build_coros_runtime_env(),
                cwd=cwd,
            )
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
            message=f"已打开命令行窗口，请在窗口中完成 COROS 授权（{resolved_region}）。",
        )

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
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
    return [
        node_path or "node",
        str(paths.skill_dir / "scripts" / "coros-mcp-keepalive.js"),
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
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            env=build_coros_runtime_env(),
        )
    except subprocess.TimeoutExpired as exc:
        raise CorosFitDownloadError(f"COROS MCP 工具调用超时 ({timeout}s): {tool_name}") from exc
    except OSError as exc:
        raise CorosFitDownloadError(f"COROS MCP keepalive 启动失败: {exc}", code="coros_node_missing") from exc

    stdout = str(completed.stdout or "")
    stderr = str(completed.stderr or "")
    if int(completed.returncode) != 0:
        detail = _error_snippet(stderr or stdout)
        suffix = f": {detail}" if detail else ""
        if _looks_like_auth_required(detail):
            raise CorosAuthRequiredError(f"COROS 授权不可用或已失效，请到配置页完成授权{suffix}")
        raise CorosFitDownloadError(f"COROS MCP 工具调用失败 (exit {int(completed.returncode)}): {tool_name}{suffix}")
    return _parse_json_stdout(stdout)


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
    start_day = _format_mcp_day(start_date)
    end_day = _format_mcp_day(end_date)
    safe_limit = max(1, min(int(limit or MAX_COROS_FIT_DOWNLOAD_LIMIT), MAX_COROS_FIT_DOWNLOAD_LIMIT))
    output_path = Path(output_dir).expanduser()
    args = {"startDate": start_day, "endDate": end_day, "limit": safe_limit}

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
    except CorosFitDownloadError:
        blobs = []
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

    errors: list[dict[str, Any]] = []
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
