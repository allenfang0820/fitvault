"""Garmin skill script provider.

This module is intentionally limited to locating and running the bundled
garmin-stats scripts. It does not call LLM backends or mutate application
state; higher-level sync flows wire these primitives into profile/activity
storage.
"""

from __future__ import annotations

import json
import importlib.util
import os
import shlex
import subprocess
import sys
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from argparse import Namespace
from pathlib import Path
from typing import Any, Iterator


VALID_GARMIN_REGIONS = {"cn", "global"}
DEFAULT_TIMEOUT_SEC = 300
ERROR_SNIPPET_CHARS = 800


class GarminSyncError(RuntimeError):
    """Base error for Garmin provider failures."""

    def __init__(self, message: str, *, code: str = "garmin_sync_error") -> None:
        super().__init__(message)
        self.code = code


class GarminSkillNotFoundError(GarminSyncError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="garmin_skill_not_found")


class GarminScriptFailed(GarminSyncError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="garmin_script_failed")


class GarminAuthRequiredError(GarminSyncError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="garmin_auth_required")


class GarminJsonParseError(GarminSyncError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="garmin_json_parse_error")


@dataclass(frozen=True)
class GarminSkillPaths:
    skill_dir: Path
    get_stats: Path
    download_fit: Path
    login: Path


@dataclass(frozen=True)
class GarminScriptResult:
    command: list[str]
    stdout: str
    stderr: str
    returncode: int


@dataclass(frozen=True)
class GarminAuthStatus:
    ok: bool
    region: str
    status: str
    token_path: str
    message: str
    login_command: list[str]


@dataclass(frozen=True)
class GarminLoginResult:
    ok: bool
    region: str
    status: str
    command: list[str]
    stdout: str
    stderr: str
    message: str


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
            if (candidate / "skills" / "garmin-stats" / "scripts" / "get_garmin_stats.py").is_file():
                return candidate
        return meipass if (meipass / "skills").exists() else candidates[0]
    return Path(__file__).resolve().parent


def resolve_garmin_region(region: str | None = None) -> str:
    value = str(region or os.environ.get("GARMIN_REGION") or "cn").strip().lower()
    if value not in VALID_GARMIN_REGIONS:
        allowed = ", ".join(sorted(VALID_GARMIN_REGIONS))
        raise GarminSyncError(f"不支持的 Garmin 区域: {value or '(empty)'}，仅支持 {allowed}", code="invalid_garmin_region")
    return value


def get_garmin_skill_paths(base_dir: Path | str | None = None) -> GarminSkillPaths:
    root = Path(base_dir).expanduser().resolve() if base_dir is not None else app_base_dir()
    skill_dir = root / "skills" / "garmin-stats"
    scripts_dir = skill_dir / "scripts"
    paths = GarminSkillPaths(
        skill_dir=skill_dir,
        get_stats=scripts_dir / "get_garmin_stats.py",
        download_fit=scripts_dir / "download_fit.py",
        login=scripts_dir / "login.py",
    )
    missing = [
        str(path)
        for path in (paths.get_stats, paths.download_fit, paths.login)
        if not path.is_file()
    ]
    if missing:
        raise GarminSkillNotFoundError("未找到 Garmin skill 脚本: " + "; ".join(missing))
    return paths


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
        "garmin 认证失败",
        "未找到 garmin token",
        "请先运行 login.py",
        "please run login.py",
        "auth_required",
        "authentication failed",
    )
    return any(marker in clean for marker in auth_markers)


def run_garmin_script(
    script_path: Path | str,
    args: list[str] | tuple[str, ...] | None = None,
    *,
    timeout: int = DEFAULT_TIMEOUT_SEC,
    env: dict[str, str] | None = None,
) -> GarminScriptResult:
    script = Path(script_path).expanduser().resolve()
    if not script.is_file():
        raise GarminSkillNotFoundError(f"未找到 Garmin skill 脚本: {script}")

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
        raise GarminScriptFailed(f"Garmin 脚本超时未返回 ({timeout}s): {script.name}") from exc
    except OSError as exc:
        raise GarminScriptFailed(f"Garmin 脚本启动失败: {exc}") from exc

    result = GarminScriptResult(
        command=command,
        stdout=str(completed.stdout or ""),
        stderr=str(completed.stderr or ""),
        returncode=int(completed.returncode),
    )
    if result.returncode != 0:
        detail = _error_snippet(result.stderr or result.stdout)
        suffix = f": {detail}" if detail else ""
        if _looks_like_auth_required(detail):
            raise GarminAuthRequiredError(f"Garmin 授权不可用或已失效{suffix}")
        raise GarminScriptFailed(f"Garmin 脚本执行失败 (exit {result.returncode}){suffix}")
    return result


def _parse_json_stdout(stdout: str) -> Any:
    text = str(stdout or "").strip()
    if not text:
        raise GarminJsonParseError("Garmin 脚本未输出 JSON")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise GarminJsonParseError(f"Garmin JSON 解析失败: {exc}") from exc


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


def _load_skill_module(script: Path, prefix: str) -> Any:
    if not script.is_file():
        raise GarminSkillNotFoundError(f"未找到 Garmin skill 脚本: {script}")
    module_name = f"_fitvault_{prefix}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, script)
    if spec is None or spec.loader is None:
        raise GarminScriptFailed(f"Garmin skill 模块加载失败: {script}")
    module = importlib.util.module_from_spec(spec)
    with _temporary_sys_path(script.parent):
        try:
            spec.loader.exec_module(module)
        except GarminSyncError:
            raise
        except Exception as exc:
            detail = str(exc)
            if _looks_like_auth_required(detail):
                raise GarminAuthRequiredError(f"Garmin 授权不可用或已失效: {detail}") from exc
            raise GarminScriptFailed(f"Garmin skill 模块执行失败: {detail}") from exc
    return module


def _sync_profile_in_process(paths: GarminSkillPaths, *, region: str, refresh: bool) -> list[dict[str, Any]]:
    module = _load_skill_module(paths.get_stats, "garmin_profile")
    build_profile = getattr(module, "build_profile", None)
    if not callable(build_profile):
        raise GarminScriptFailed("Garmin skill 缺少 build_profile 可调用入口")
    args = Namespace(
        mode="sync",
        refresh=bool(refresh),
        no_cache_refresh=False,
        cache_ttl_days=getattr(module, "DEFAULT_CACHE_TTL_DAYS", 7),
        region=region,
        tokenstore=None,
        auth_file=None,
        debug=False,
    )
    try:
        parsed = build_profile(args)
    except GarminSyncError:
        raise
    except Exception as exc:
        detail = str(exc)
        if _looks_like_auth_required(detail):
            raise GarminAuthRequiredError(f"Garmin 授权不可用或已失效: {detail}") from exc
        raise GarminScriptFailed(f"Garmin 画像同步执行失败: {detail}") from exc
    if not isinstance(parsed, list):
        raise GarminJsonParseError("Garmin 画像同步返回的不是 JSON 数组")
    if not all(isinstance(item, dict) for item in parsed):
        raise GarminJsonParseError("Garmin 画像同步 JSON 数组元素必须是对象")
    return parsed


def sync_profile_json(
    *,
    region: str | None = None,
    refresh: bool = False,
    timeout: int = DEFAULT_TIMEOUT_SEC,
    base_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    resolved_region = resolve_garmin_region(region)
    paths = get_garmin_skill_paths(base_dir)
    return _sync_profile_in_process(paths, region=resolved_region, refresh=refresh)


def download_fit_json(
    *,
    start_date: str,
    end_date: str,
    output_dir: Path | str,
    region: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SEC,
    base_dir: Path | str | None = None,
) -> dict[str, Any]:
    resolved_region = resolve_garmin_region(region)
    paths = get_garmin_skill_paths(base_dir)
    args = [
        "--from",
        str(start_date),
        "--to",
        str(end_date),
        "--region",
        resolved_region,
        "--output-dir",
        str(Path(output_dir).expanduser()),
        "--json",
    ]
    result = run_garmin_script(paths.download_fit, args, timeout=timeout)
    parsed = _parse_json_stdout(result.stdout)
    if not isinstance(parsed, dict):
        raise GarminJsonParseError("Garmin FIT 下载返回的不是 JSON 对象")
    return parsed


def login_command(*, region: str | None = None, base_dir: Path | str | None = None) -> list[str]:
    resolved_region = resolve_garmin_region(region)
    paths = get_garmin_skill_paths(base_dir)
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable)
        if sys.platform.startswith("win"):
            candidates = [executable.with_name("FitVaultCLI.exe")]
            meipass = Path(str(getattr(sys, "_MEIPASS", "")))
            if str(meipass):
                candidates.extend([
                    meipass / "FitVaultCLI.exe",
                    meipass.parent / "FitVaultCLI.exe",
                ])
            for cli_exe in candidates:
                if cli_exe.is_file():
                    return [str(cli_exe), "--garmin-login", "--region", resolved_region]
            raise GarminSkillNotFoundError(
                "未找到 Windows Garmin 授权辅助程序: "
                + "; ".join(str(path) for path in candidates)
            )
        return [sys.executable, "--garmin-login", "--region", resolved_region]
    return [sys.executable, str(paths.login), "--region", resolved_region]


def _windows_command_line(command: list[str]) -> str:
    return subprocess.list2cmdline([str(part) for part in command])


def _windows_command_cwd(command: list[str], fallback: Path) -> str:
    if command:
        first = Path(command[0])
        if first.name.lower() in {"python.exe", "pythonw.exe", "py.exe"} and len(command) > 1:
            return str(Path(command[1]).resolve().parent)
        if first.is_file() or first.suffix.lower() in {".exe", ".cmd", ".bat"}:
            return str(first.resolve().parent)
    return str(fallback)


def _windows_console_launcher(command: list[str], cwd: str, title: str, done_message: str) -> list[str]:
    command_line = _windows_command_line(command)
    if command and Path(str(command[0])).suffix.lower() in {".cmd", ".bat"}:
        command_line = "call " + command_line
    shell_command = (
        f"cd /d {subprocess.list2cmdline([cwd])} && "
        f"{command_line} & "
        f"echo. & echo {done_message} & pause"
    )
    return [
        "cmd.exe",
        "/d",
        "/c",
        "start",
        title,
        "cmd.exe",
        "/d",
        "/k",
        shell_command,
    ]


def default_tokenstore(
    region: str | None = None,
    workspace_dir: Path | str | None = None,
) -> Path:
    resolved_region = resolve_garmin_region(region)
    root = (
        Path(workspace_dir).expanduser()
        if workspace_dir is not None
        else Path(os.environ.get("QCLAW_WORKSPACE_DIR", str(Path.home() / ".qclaw" / "workspace"))).expanduser()
    )
    return root / f"garmin_auth_{resolved_region}"


def check_auth_status(
    *,
    region: str | None = None,
    base_dir: Path | str | None = None,
    workspace_dir: Path | str | None = None,
) -> GarminAuthStatus:
    try:
        resolved_region = resolve_garmin_region(region)
    except GarminSyncError as exc:
        return GarminAuthStatus(
            ok=False,
            region=str(region or os.environ.get("GARMIN_REGION") or "").strip().lower(),
            status="invalid_region",
            token_path="",
            message=str(exc),
            login_command=[],
        )

    token_path = default_tokenstore(resolved_region, workspace_dir)
    try:
        command = login_command(region=resolved_region, base_dir=base_dir)
    except GarminSkillNotFoundError as exc:
        return GarminAuthStatus(
            ok=False,
            region=resolved_region,
            status="skill_missing",
            token_path=str(token_path),
            message=str(exc),
            login_command=[],
        )

    if not token_path.exists():
        return GarminAuthStatus(
            ok=False,
            region=resolved_region,
            status="missing_token",
            token_path=str(token_path),
            message=f"请先登录 Garmin（{resolved_region}），未检测到授权 token。",
            login_command=command,
        )

    if token_path.is_dir() and not (
        (token_path / "oauth1_token.json").is_file()
        and (token_path / "oauth2_token.json").is_file()
    ):
        return GarminAuthStatus(
            ok=False,
            region=resolved_region,
            status="missing_token",
            token_path=str(token_path),
            message=f"请先登录 Garmin（{resolved_region}），授权 token 不完整。",
            login_command=command,
        )

    if not (token_path.is_file() or token_path.is_dir()):
        return GarminAuthStatus(
            ok=False,
            region=resolved_region,
            status="unknown",
            token_path=str(token_path),
            message=f"Garmin 授权路径不可用: {token_path}",
            login_command=command,
        )

    return GarminAuthStatus(
        ok=True,
        region=resolved_region,
        status="authorized",
        token_path=str(token_path),
        message=f"已检测到 Garmin 授权（{resolved_region}）。",
        login_command=command,
    )


def start_login(
    *,
    region: str | None = None,
    base_dir: Path | str | None = None,
    timeout: int | None = None,
) -> GarminLoginResult:
    try:
        resolved_region = resolve_garmin_region(region)
    except GarminSyncError as exc:
        return GarminLoginResult(
            ok=False,
            region=str(region or os.environ.get("GARMIN_REGION") or "").strip().lower(),
            status="invalid_region",
            command=[],
            stdout="",
            stderr="",
            message=str(exc),
        )

    try:
        command = login_command(region=resolved_region, base_dir=base_dir)
    except GarminSkillNotFoundError as exc:
        return GarminLoginResult(
            ok=False,
            region=resolved_region,
            status="skill_missing",
            command=[],
            stdout="",
            stderr="",
            message=str(exc),
        )

    if sys.platform == "darwin":
        paths = get_garmin_skill_paths(base_dir)
        cwd = str(paths.login.resolve().parent)
        shell_command = (
            f"cd {shlex.quote(cwd)} && "
            f"{' '.join(shlex.quote(part) for part in command)}; "
            "echo; echo 'Garmin 授权流程结束后，请回到脉图重新点击同步活动。'; "
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
            return GarminLoginResult(
                ok=False,
                region=resolved_region,
                status="launch_failed",
                command=command,
                stdout="",
                stderr="",
                message=f"Garmin 登录终端启动失败: {exc}",
            )
        return GarminLoginResult(
            ok=True,
            region=resolved_region,
            status="launched",
            command=command,
            stdout="",
            stderr="",
            message=f"已打开终端窗口，请在终端完成 Garmin 登录授权（{resolved_region}）。",
        )

    paths = get_garmin_skill_paths(base_dir)

    if sys.platform.startswith("win"):
        cwd = _windows_command_cwd(command, paths.login.resolve().parent)
        launcher = _windows_console_launcher(
            command,
            cwd,
            "FitVault Garmin Login",
            "Garmin 授权流程结束后，请回到脉图重新点击同步活动。",
        )
        try:
            subprocess.Popen(
                launcher,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=cwd,
            )
        except OSError as exc:
            return GarminLoginResult(
                ok=False,
                region=resolved_region,
                status="launch_failed",
                command=command,
                stdout="",
                stderr="",
                message=f"Garmin 登录终端启动失败: {exc}",
            )
        return GarminLoginResult(
            ok=True,
            region=resolved_region,
            status="launched",
            command=command,
            stdout="",
            stderr="",
            message=f"已打开命令行窗口，请在窗口中完成 Garmin 登录授权（{resolved_region}）。",
        )

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            cwd=str(paths.login.resolve().parent),
        )
    except subprocess.TimeoutExpired as exc:
        stdout = str(exc.stdout or "")
        stderr = str(exc.stderr or "")
        return GarminLoginResult(
            ok=False,
            region=resolved_region,
            status="timeout",
            command=command,
            stdout=stdout,
            stderr=stderr,
            message=f"Garmin 登录授权超时 ({timeout}s)",
        )
    except OSError as exc:
        return GarminLoginResult(
            ok=False,
            region=resolved_region,
            status="launch_failed",
            command=command,
            stdout="",
            stderr="",
            message=f"Garmin 登录脚本启动失败: {exc}",
        )

    stdout = str(completed.stdout or "")
    stderr = str(completed.stderr or "")
    if int(completed.returncode) != 0:
        detail = _error_snippet(stderr or stdout)
        suffix = f": {detail}" if detail else ""
        return GarminLoginResult(
            ok=False,
            region=resolved_region,
            status="failed",
            command=command,
            stdout=stdout,
            stderr=stderr,
            message=f"Garmin 登录授权失败 (exit {int(completed.returncode)}){suffix}",
        )

    return GarminLoginResult(
        ok=True,
        region=resolved_region,
        status="completed",
        command=command,
        stdout=stdout,
        stderr=stderr,
        message=f"Garmin 登录授权已完成（{resolved_region}）。",
    )
