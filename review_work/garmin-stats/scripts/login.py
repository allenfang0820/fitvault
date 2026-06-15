#!/usr/bin/env python3
"""佳明账号首次授权脚本。

用法：
  python3 login.py
  python3 login.py --region global
"""
import argparse
import getpass
import json
import os
import subprocess
from pathlib import Path

AUTH_FILE = Path.home() / ".qclaw" / "workspace" / "garmin_auth.json"


def patch_garth_ssl_consumer() -> None:
    import garth

    try:
        result = subprocess.run(
            [
                "curl",
                "-s",
                "--max-time",
                "10",
                "https://thegarth.s3.amazonaws.com/oauth_consumer.json",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip().startswith("{"):
            garth.sso.OAUTH_CONSUMER = json.loads(result.stdout.strip())
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="登录佳明账号并保存 OAuth token")
    parser.add_argument(
        "--region",
        choices=["cn", "global"],
        default=os.environ.get("GARMIN_REGION", "cn"),
        help="佳明账号区域，默认 cn；国际区用 global",
    )
    parser.add_argument(
        "--auth-file",
        default=str(AUTH_FILE),
        help="认证文件保存路径",
    )
    args = parser.parse_args()

    try:
        import garth
    except ModuleNotFoundError:
        raise SystemExit("缺少依赖 garth。请先运行: pip3 install -r ~/.qclaw/skills/garmin-stats/requirements.txt")

    patch_garth_ssl_consumer()

    email = input("佳明账号邮箱/用户名: ").strip()
    password = getpass.getpass("佳明账号密码（不会显示）: ")
    if not email or not password:
        raise SystemExit("账号或密码不能为空。")

    auth_path = Path(args.auth_file).expanduser()
    auth_path.parent.mkdir(parents=True, exist_ok=True)

    client = garth.Client(domain="garmin.cn" if args.region == "cn" else "garmin.com")
    client.login(email, password)
    client.save(str(auth_path))

    print(f"登录成功，认证文件已保存: {auth_path}")


if __name__ == "__main__":
    main()
