from __future__ import annotations

import importlib
import importlib.metadata
import inspect
import json
import os
import platform
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Callable


GARMINCONNECT_EXPECTED_VERSION = "0.3.6"
GARMIN_FIT_SDK_EXPECTED_VERSION = "21.205.0"
CURL_CFFI_MIN_VERSION = "0.6"
MANIFEST_FILENAME = "build_dependency_manifest.json"
SENSITIVE_PATTERN = re.compile(
    r"(token|password|passwd|authorization|cookie|secret|mfa|otp|api[_-]?key)",
    re.I,
)


class PackagingCheckError(RuntimeError):
    pass


def _version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in str(version or "").split("."):
        match = re.match(r"(\d+)", part)
        if not match:
            break
        parts.append(int(match.group(1)))
    return tuple(parts)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): ("[redacted]" if SENSITIVE_PATTERN.search(str(k)) else _redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = str(value) if value is not None else ""
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[redacted]", text)
    text = re.sub(
        r"(?i)\b(token|password|passwd|authorization|cookie|secret|mfa|otp|api[_-]?key)\s*[:=]\s*[^,\s;]+",
        r"\1=[redacted]",
        text,
    )
    return text


def package_version(package_name: str) -> str | None:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None
    except Exception:
        return None


def require_distribution(
    package_name: str,
    *,
    expected_version: str | None = None,
    min_version: str | None = None,
    version_lookup: Callable[[str], str | None] = package_version,
) -> str:
    version = version_lookup(package_name)
    if not version:
        raise PackagingCheckError(
            f"Missing required packaging distribution: {package_name}. "
            "Run python -m pip install -r requirements.txt -c constraints.txt in the packaging venv."
        )
    if expected_version and version != expected_version:
        if package_name == "garminconnect":
            detail = (
                f"当前源码仅兼容 garminconnect {GARMINCONNECT_EXPECTED_VERSION}，"
                "请同步 requirements/constraints 后重新安装依赖。"
            )
        else:
            detail = (
                f"当前源码需要 {package_name} {expected_version}，"
                "请同步 requirements/constraints 后重新安装依赖。"
            )
        raise PackagingCheckError(
            f"Incompatible {package_name} version: detected {version}, expected {expected_version}. "
            + detail
        )
    if min_version and _version_tuple(version) < _version_tuple(min_version):
        raise PackagingCheckError(
            f"Incompatible {package_name} version: detected {version}, expected >= {min_version}. "
            "请同步 requirements/constraints 后重新安装依赖。"
        )
    return version


def check_garmin_dependencies(
    *,
    version_lookup: Callable[[str], str | None] = package_version,
    import_module: Callable[[str], Any] = importlib.import_module,
) -> dict[str, str]:
    garmin_version = require_distribution(
        "garminconnect",
        expected_version=GARMINCONNECT_EXPECTED_VERSION,
        version_lookup=version_lookup,
    )
    curl_version = require_distribution(
        "curl_cffi",
        min_version=CURL_CFFI_MIN_VERSION,
        version_lookup=version_lookup,
    )
    sdk_version = require_distribution(
        "garmin-fit-sdk",
        expected_version=GARMIN_FIT_SDK_EXPECTED_VERSION,
        version_lookup=version_lookup,
    )
    try:
        garmin_module = import_module("garminconnect")
    except Exception as exc:
        raise PackagingCheckError(f"Cannot import garminconnect: {type(exc).__name__}: {exc}") from exc
    try:
        import_module("garmin_fit_sdk")
    except Exception as exc:
        raise PackagingCheckError(
            "Cannot import garmin_fit_sdk: "
            f"{type(exc).__name__}: {exc}. "
            "Run python -m pip install -r requirements.txt -c constraints.txt in the packaging venv."
        ) from exc
    garmin_cls = getattr(garmin_module, "Garmin", None)
    if garmin_cls is None:
        raise PackagingCheckError("garminconnect.Garmin is missing; reinstall pinned dependencies.")
    try:
        params = inspect.signature(garmin_cls).parameters
    except (TypeError, ValueError) as exc:
        raise PackagingCheckError(f"Cannot inspect garminconnect.Garmin API: {exc}") from exc
    missing = [name for name in ("prompt_mfa", "return_on_mfa") if name not in params]
    if missing:
        raise PackagingCheckError(
            "Incompatible garminconnect.Garmin API: missing "
            + ", ".join(missing)
            + f". 当前源码仅兼容 garminconnect {GARMINCONNECT_EXPECTED_VERSION}，"
              "请同步 requirements/constraints 后重新安装依赖。"
        )
    return {"garminconnect": garmin_version, "curl_cffi": curl_version, "garmin-fit-sdk": sdk_version}


def check_skill_zip(zip_path: Path, *, root_name: str, required_members: list[str]) -> dict[str, Any]:
    path = Path(zip_path)
    if not path.exists():
        raise PackagingCheckError(f"Missing skill zip: {path}")
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    except zipfile.BadZipFile as exc:
        raise PackagingCheckError(f"Invalid skill zip: {path}") from exc
    nested_prefix = f"skills/{root_name}/"
    if any(name.startswith(nested_prefix) for name in names):
        raise PackagingCheckError(f"Invalid skill zip root for {path.name}: found nested {nested_prefix}")
    root_prefix = f"{root_name}/"
    if not any(name.startswith(root_prefix) for name in names):
        raise PackagingCheckError(f"Invalid skill zip root for {path.name}: missing {root_prefix}")
    bad_cache = [name for name in names if "__pycache__/" in name or name.endswith(".pyc")]
    if bad_cache:
        raise PackagingCheckError(f"Invalid skill zip {path.name}: contains Python cache files")
    missing = [member for member in required_members if member not in names]
    if missing:
        raise PackagingCheckError(f"Invalid skill zip {path.name}: missing {', '.join(missing)}")
    return {"zip_present": True, "root": root_name, "member_count": len(names)}


def _runtime_name_for_platform(system: str | None = None, machine: str | None = None) -> str:
    resolved_system = (system or platform.system()).lower()
    resolved_machine = (machine or platform.machine()).lower()
    arch = "arm64" if resolved_machine in {"arm64", "aarch64"} else "x64"
    if resolved_system == "windows":
        return "node-win-x64"
    return f"node-darwin-{arch}"


def resolve_node_runtime_dir(project_root: Path, *, system: str | None = None, machine: str | None = None) -> Path:
    configured = os.environ.get("MAITU_NODE_RUNTIME_DIR", "").strip()
    if configured:
        return Path(configured)
    return Path(project_root) / "runtimes" / _runtime_name_for_platform(system, machine)


def check_windows_runtime(project_root: Path, *, system: str | None = None, machine: str | None = None) -> dict[str, bool]:
    if (system or platform.system()).lower() != "windows":
        return {"required": False}
    runtime_dir = resolve_node_runtime_dir(project_root, system=system, machine=machine)
    node = runtime_dir / "node.exe"
    npm = runtime_dir / "npm.cmd"
    missing = [str(path) for path in (node, npm) if not path.exists()]
    if missing:
        raise PackagingCheckError("Windows packaging requires bundled Node runtime: missing " + ", ".join(missing))
    return {"required": True, "node": True, "npm": True}


def check_python_environment() -> dict[str, Any]:
    version_info = {
        "major": sys.version_info.major,
        "minor": sys.version_info.minor,
        "micro": sys.version_info.micro,
    }
    warnings: list[str] = []
    if (sys.version_info.major, sys.version_info.minor) < (3, 12):
        warnings.append("Packaging runtime is expected to use Python >= 3.12; reinstall dependencies in the packaging venv.")
    return {
        "executable": sys.executable,
        "version": sys.version.split()[0],
        "version_info": version_info,
        "warnings": warnings,
    }


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = (text or "").strip()
    if not stripped:
        raise ValueError("empty output")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end < start:
            raise
        payload = json.loads(stripped[start:end + 1])
    if not isinstance(payload, dict):
        raise ValueError("runtime check output is not a JSON object")
    return payload


def check_python312_runtime_script(
    project_root: str | Path = ".",
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    root = Path(project_root)
    script = root / "scripts" / "check_python312_runtime.py"
    if not script.exists():
        raise PackagingCheckError(f"Missing Python 3.12 runtime check script: {script}")
    try:
        completed = runner(
            [sys.executable, str(script)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:
        raise PackagingCheckError(f"Cannot run Python 3.12 runtime check: {type(exc).__name__}: {exc}") from exc
    try:
        report = _extract_json_object(completed.stdout)
    except Exception as exc:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        detail = stderr or stdout[:500] or type(exc).__name__
        raise PackagingCheckError(f"Python 3.12 runtime check returned invalid JSON: {detail}") from exc
    if completed.returncode != 0 or report.get("ok") is not True:
        raw_errors = report.get("errors")
        errors = [str(item) for item in raw_errors] if isinstance(raw_errors, list) else []
        detail = "; ".join(errors[:5]) or (completed.stderr or "").strip() or "unknown runtime check failure"
        raise PackagingCheckError(f"Python 3.12 runtime check failed: {detail}")
    return report


def check_packaging_prerequisites(
    project_root: str | Path = ".",
    *,
    system: str | None = None,
    machine: str | None = None,
) -> dict[str, Any]:
    root = Path(project_root)
    python_runtime = check_python312_runtime_script(root)
    versions = check_garmin_dependencies()
    check_skill_zip(
        root / "skills" / "garmin-stats.zip",
        root_name="garmin-stats",
        required_members=["garmin-stats/scripts/garmin_auth.py"],
    )
    check_skill_zip(
        root / "skills" / "coros-stats.zip",
        root_name="coros-stats",
        required_members=["coros-stats/scripts/coros-mcp-keepalive.js"],
    )
    for script in (
        root / "skills" / "garmin-stats" / "scripts" / "garmin_auth.py",
        root / "skills" / "coros-stats" / "scripts" / "coros-mcp-keepalive.js",
    ):
        if not script.exists():
            raise PackagingCheckError(f"Missing required skill script: {script}")
    runtime = check_windows_runtime(root, system=system, machine=machine)
    return {
        "packages": versions,
        "python_runtime": python_runtime,
        "runtime": runtime,
        "skills": {"garmin-stats": True, "coros-stats": True},
    }



def _command_version(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
    except Exception:
        return None
    text = (completed.stdout or completed.stderr or "").strip()
    return text.splitlines()[0].strip() if text else None


def build_dependency_manifest(project_root: str | Path = ".") -> dict[str, Any]:
    root = Path(project_root)
    python_env = check_python_environment()
    runtime_dir = resolve_node_runtime_dir(root)
    node_name = "node.exe" if platform.system().lower() == "windows" else "bin/node"
    npm_name = "npm.cmd" if platform.system().lower() == "windows" else "bin/npm"
    node_path = runtime_dir / node_name
    npm_path = runtime_dir / npm_name
    manifest = {
        "python_executable": python_env["executable"],
        "python_version": sys.version.split()[0],
        "python_version_info": python_env["version_info"],
        "python_warnings": python_env["warnings"],
        "platform": platform.platform(),
        "packages": {
            name: package_version(name)
            for name in ("garminconnect", "garmin-fit-sdk", "garth", "curl_cffi", "requests", "urllib3", "certifi")
        },
        "runtime": {
            "node": {"path": str(node_path), "version": _command_version([str(node_path), "--version"]) if node_path.exists() else None},
            "npm": {"path": str(npm_path), "version": _command_version([str(npm_path), "--version"]) if npm_path.exists() else None},
        },
        "skills": {
            "garmin-stats": {
                "zip_present": (root / "skills" / "garmin-stats.zip").exists(),
                "script_present": (root / "skills" / "garmin-stats" / "scripts" / "garmin_auth.py").exists(),
            },
            "coros-stats": {
                "zip_present": (root / "skills" / "coros-stats.zip").exists(),
                "keepalive_present": (root / "skills" / "coros-stats" / "scripts" / "coros-mcp-keepalive.js").exists(),
            },
        },
        "compatibility": {
            "garminconnect_expected": GARMINCONNECT_EXPECTED_VERSION,
            "garmin_fit_sdk_expected": GARMIN_FIT_SDK_EXPECTED_VERSION,
            "garmin_api": "0.3.x-tokenstore-client",
            "codex_cli_windows_shim_supported": True,
            "coros_mcp_envelope_supported": True,
        },
    }
    return _redact(manifest)


def write_dependency_manifest(project_root: str | Path = ".", output_path: str | Path | None = None) -> Path:
    root = Path(project_root)
    target = Path(output_path) if output_path else root / MANIFEST_FILENAME
    manifest = build_dependency_manifest(root)
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


if __name__ == "__main__":
    try:
        check_packaging_prerequisites(Path.cwd())
        path = write_dependency_manifest(Path.cwd())
    except PackagingCheckError as exc:
        print(f"PackagingCheckError: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(path)
