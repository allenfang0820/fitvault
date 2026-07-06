#!/usr/bin/env python3
"""佳明账号首次授权脚本。

用法：
  python3 login.py --region cn
  python3 login.py --region global

说明：
- 大陆区和国际区 token 分开保存，避免区域混用。
- 如 Garmin 要求 MFA，按终端提示输入验证码。
- 国际区账号遇到 429/Too Many Requests 时，不要连续重试。
"""
import argparse
import getpass
import os
from pathlib import Path

from garmin_auth import (
    GarminStatsAuthError,
    GarminStatsMFARequired,
    DEFAULT_AUTH_DIRS,
    login_and_save_app,
    normalize_region,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="登录佳明账号并保存 OAuth token")
    parser.add_argument(
        "--region",
        choices=["cn", "global"],
        default=os.environ.get("GARMIN_REGION", "cn"),
        help="佳明账号区域，默认 cn；国际区用 global",
    )
    parser.add_argument(
        "--tokenstore",
        default=None,
        help="token 保存目录；默认按区域保存到用户主目录下的 .qclaw/workspace/garmin_auth_cn 或 garmin_auth_global",
    )
    # 兼容旧参数名；如果传入文件名，实际仍按目录处理。
    parser.add_argument("--auth-file", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    region = normalize_region(args.region)
    tokenstore = args.tokenstore or args.auth_file or str(DEFAULT_AUTH_DIRS[region])

    email = input("佳明账号邮箱/用户名: ").strip()
    password = getpass.getpass("佳明账号密码（不会显示）: ")
    if not email or not password:
        raise SystemExit("账号或密码不能为空。")

    try:
        token_path = login_and_save_app(email, password, region, Path(tokenstore).expanduser())
    except GarminStatsMFARequired as exc:
        mfa_code = input("Garmin MFA/两步验证码: ").strip()
        if not mfa_code:
            raise SystemExit("MFA 验证码不能为空。")
        try:
            token_path = login_and_save_app(
                email,
                password,
                region,
                Path(tokenstore).expanduser(),
                mfa_code=mfa_code,
                mfa_state=getattr(exc, "client_state", None),
            )
        except GarminStatsAuthError as retry_exc:
            raise SystemExit(str(retry_exc))
    except GarminStatsAuthError as exc:
        raise SystemExit(str(exc))

    print(f"登录成功，region={region}")
    print(f"认证 token 已保存: {token_path}")
    print("后续同步、刷新缓存、下载 FIT 请使用同一个 --region。")


if __name__ == "__main__":
    main()
