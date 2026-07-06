#!/usr/bin/env python3
"""
下载佳明活动 FIT 文件，以活动标题+ID命名。

用法:
  python download_fit.py <activity_id>               # 下载单个活动
  python download_fit.py <id1> <id2> ...             # 下载多个活动
  python download_fit.py --from YYYY-MM-DD --to YYYY-MM-DD    # 时间范围
  python download_fit.py --update                     # 更新活动（上次下载至今）
  python download_fit.py --update-1m                  # 更新近一个月（30天）
  python download_fit.py --update-3m                  # 更新近三个月（90天）
  python download_fit.py --update-1y                  # 更新近一年（365天）
  python download_fit.py --update-2y                  # 更新近两年
  python download_fit.py --update-3y                  # 更新近三年

机器模式:
  追加 --json 时，stdout 只输出一个 JSON 对象，普通日志改写 stderr。
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import sys
import zipfile
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

# 通用移除 hermes libs
hermes_libs = os.path.expanduser("~/Library/Application Support/QClaw/hermes/libs")
if hermes_libs in sys.path:
    sys.path.remove(hermes_libs)


DEFAULT_OUTPUT_DIR = os.path.abspath(os.path.expanduser(
    os.environ.get("FITVAULT_TRACKS_DIR", "~/.fitvault/workspace/tracks")
))
DEFAULT_REGION = os.environ.get("GARMIN_REGION", "cn")


@dataclass
class RuntimeContext:
    client: Any
    garminconnect: Any
    output_dir: str
    region: str


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="下载佳明活动 FIT 文件")
    parser.add_argument("activity_ids", nargs="*", help="一个或多个 Garmin activity id")
    parser.add_argument("--from", dest="start_date", default="", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--to", dest="end_date", default="", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--type", dest="activity_type", default=None, help="Garmin 活动类型过滤")
    parser.add_argument("--update", action="store_true", help="从最近已下载活动日期更新至今天")
    parser.add_argument("--update-1m", action="store_true", help="更新近一个月")
    parser.add_argument("--update-3m", action="store_true", help="更新近三个月")
    parser.add_argument("--update-1y", action="store_true", help="更新近一年")
    parser.add_argument("--update-2y", action="store_true", help="更新近两年")
    parser.add_argument("--update-3y", action="store_true", help="更新近三年")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="FIT 保存目录")
    parser.add_argument("--region", choices=["cn", "global"], default=DEFAULT_REGION, help="Garmin 账号区域")
    parser.add_argument("--tokenstore", default=None, help="Garmin token 目录；默认按区域读取")
    parser.add_argument("--auth-file", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--json", action="store_true", help="只向 stdout 输出机器可读 JSON")
    return parser.parse_args(argv)


def log(message: str, *, json_mode: bool = False, end: str = "\n", flush: bool = False) -> None:
    print(message, end=end, flush=flush, file=sys.stderr if json_mode else sys.stdout)


def _summary(
    *,
    mode: str,
    region: str,
    output_dir: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    return {
        "ok": True,
        "region": region,
        "output_dir": output_dir,
        "mode": mode,
        "start_date": start_date,
        "end_date": end_date,
        "searched": 0,
        "downloaded": 0,
        "skipped": 0,
        "failed": 0,
        "files": [],
        "errors": [],
    }


def _merge_result(summary: dict[str, Any], result: dict[str, Any]) -> None:
    status = result.get("status")
    if status == "downloaded":
        summary["downloaded"] += 1
        if result.get("file"):
            summary["files"].append(result["file"])
    elif status == "skipped":
        summary["skipped"] += 1
    else:
        summary["failed"] += 1
        summary["errors"].append({
            "activity_id": result.get("activity_id"),
            "message": result.get("message") or "下载失败",
        })
    summary["ok"] = summary["failed"] == 0


def create_runtime_context(args: argparse.Namespace) -> RuntimeContext:
    try:
        import garminconnect
    except ModuleNotFoundError as exc:
        raise SystemExit(
            f"缺少依赖 {exc.name}。请先在 skill 目录运行: python -m pip install -r requirements.txt"
        ) from exc

    from garmin_auth import GarminStatsAuthError, build_client, default_tokenstore

    try:
        tokenstore = args.tokenstore or args.auth_file or str(default_tokenstore(args.region))
        client, _token_path = build_client(args.region, tokenstore)
    except GarminStatsAuthError as exc:
        raise SystemExit(str(exc)) from exc

    return RuntimeContext(
        client=client,
        garminconnect=garminconnect,
        output_dir=os.path.abspath(os.path.expanduser(args.output_dir)),
        region=args.region,
    )


def sanitize_filename(name: str) -> str:
    """将活动标题转为安全的文件名"""
    safe = re.sub(r'[<>:"/\\|?*]', "_", str(name or ""))
    safe = re.sub(r"\s+", " ", safe).strip()
    if len(safe) > 80:
        safe = safe[:80].rstrip()
    return safe or "Garmin Activity"


def list_existing_ids(output_dir: str) -> set[int]:
    """扫描目录中已有的 FIT 文件，返回已下载的活动ID集合"""
    ids: set[int] = set()
    if not os.path.isdir(output_dir):
        return ids
    pattern = re.compile(r"_(\d+)\.fit$")
    for fname in os.listdir(output_dir):
        if fname.endswith(".fit"):
            m = pattern.search(fname)
            if m:
                ids.add(int(m.group(1)))
    return ids


def get_activity_detail(ctx: RuntimeContext, activity_id: int, *, json_mode: bool = False) -> dict[str, Any] | None:
    """获取活动详情（含标题、日期）"""
    try:
        return ctx.client.connectapi(f"/activity-service/activity/{activity_id}")
    except Exception as e:
        log(f"  获取活动详情({activity_id})失败: {e}", json_mode=True)
        return None


def download_and_save(
    ctx: RuntimeContext,
    activity_id: int,
    activity_title: str | None = None,
    *,
    json_mode: bool = False,
) -> dict[str, Any]:
    """下载并保存 FIT 文件，返回结构化结果。"""
    os.makedirs(ctx.output_dir, exist_ok=True)

    existing = list_existing_ids(ctx.output_dir)
    if activity_id in existing:
        message = f"已存在，跳过 {activity_id}"
        log(f"  ⏭️  {message}", json_mode=json_mode)
        return {"status": "skipped", "activity_id": activity_id, "file": None, "message": message}

    log(f"\n📥 正在下载活动 {activity_id}...", json_mode=json_mode)

    if not activity_title:
        detail = get_activity_detail(ctx, activity_id, json_mode=json_mode)
        if detail:
            activity_title = detail.get("activityName") or str(activity_id)
        else:
            activity_title = str(activity_id)

    try:
        raw_data = ctx.client.download_activity(
            activity_id,
            dl_fmt=ctx.garminconnect.Garmin.ActivityDownloadFormat.ORIGINAL,
        )
    except Exception as e:
        message = f"下载失败: {e}"
        log(f"  ❌ {message}", json_mode=True)
        return {"status": "failed", "activity_id": activity_id, "file": None, "message": message}

    if not raw_data:
        message = "下载返回空数据"
        log(f"  ❌ {message}", json_mode=True)
        return {"status": "failed", "activity_id": activity_id, "file": None, "message": message}

    try:
        with zipfile.ZipFile(io.BytesIO(raw_data)) as zf:
            fit_files = [n for n in zf.namelist() if n.lower().endswith(".fit")]
            if not fit_files:
                message = "ZIP 内无 FIT 文件"
                log(f"  ❌ {message}", json_mode=True)
                return {"status": "failed", "activity_id": activity_id, "file": None, "message": message}
            fit_data = zf.read(fit_files[0])
    except Exception as e:
        message = f"解压失败: {e}"
        log(f"  ❌ {message}", json_mode=True)
        return {"status": "failed", "activity_id": activity_id, "file": None, "message": message}

    safe_title = sanitize_filename(activity_title)
    filename = f"{safe_title}_{activity_id}.fit"
    filepath = os.path.join(ctx.output_dir, filename)

    with open(filepath, "wb") as f:
        f.write(fit_data)

    log(f"  ✅ 已保存: {filename}", json_mode=json_mode)
    return {"status": "downloaded", "activity_id": activity_id, "file": filepath, "message": "已保存"}


def get_latest_downloaded_date(ctx: RuntimeContext, *, json_mode: bool = False) -> str | None:
    """从已有 FIT 文件中找到最近下载的活动日期"""
    ids = list_existing_ids(ctx.output_dir)
    if not ids:
        return None

    top_ids = sorted(ids, reverse=True)[:5]
    latest_date = None

    for aid in top_ids:
        detail = get_activity_detail(ctx, aid, json_mode=json_mode)
        if detail:
            sd = detail.get("summaryDTO") or {}
            st = sd.get("startTimeLocal")
            if st:
                try:
                    d = st[:10]
                    if latest_date is None or d > latest_date:
                        latest_date = d
                except Exception:
                    pass

    return latest_date


def download_by_date_range(
    ctx: RuntimeContext,
    start_date: str,
    end_date: str,
    activity_type: str | None = None,
    *,
    json_mode: bool = False,
    mode: str = "date_range",
) -> dict[str, Any]:
    """下载时间范围内所有活动"""
    summary = _summary(
        mode=mode,
        region=ctx.region,
        output_dir=ctx.output_dir,
        start_date=start_date,
        end_date=end_date,
    )
    log(f"🔍 正在搜索 {start_date} 至 {end_date} 的活动...", end="", flush=True, json_mode=json_mode)

    try:
        activities = ctx.client.get_activities_by_date(start_date, end_date, activity_type)
    except Exception as e:
        message = f"获取活动列表失败: {e}"
        log(f"\n  {message}", json_mode=True)
        summary["ok"] = False
        summary["errors"].append({"activity_id": None, "message": message})
        summary["failed"] = 1
        return summary

    if not activities:
        log(" 未找到任何活动", json_mode=json_mode)
        return summary

    summary["searched"] = len(activities)
    log(f" 找到 {len(activities)} 个活动", json_mode=json_mode)

    for act in activities:
        aid = act.get("activityId")
        if not aid:
            continue
        title = act.get("activityName") or str(aid)
        _merge_result(summary, download_and_save(ctx, int(aid), activity_title=title, json_mode=json_mode))

    log(f"\n📊 结果: {summary['downloaded']} 个成功, {summary['failed']} 个失败", json_mode=json_mode)
    log(f"📁 保存位置: {ctx.output_dir}", json_mode=json_mode)
    return summary


def do_update(
    ctx: RuntimeContext,
    last_days: int | None = None,
    *,
    json_mode: bool = False,
    mode: str = "update",
) -> dict[str, Any]:
    """执行更新下载"""
    today_str = date.today().isoformat()

    if last_days == 0:
        log("🔍 正在查找最近已下载的活动日期...", flush=True, json_mode=json_mode)
        latest = get_latest_downloaded_date(ctx, json_mode=json_mode)
        if not latest:
            log("  ⚠️  目录中没有已有 FIT 文件，改为下载近一个月", json_mode=json_mode)
            start = (date.today() - timedelta(days=30)).isoformat()
        else:
            start = latest
            log(f"  最近已下载: {latest}", json_mode=json_mode)
    else:
        start = (date.today() - timedelta(days=last_days or 30)).isoformat()

    return download_by_date_range(ctx, start, today_str, json_mode=json_mode, mode=mode)


def download_activity_ids(ctx: RuntimeContext, activity_ids: list[str], *, json_mode: bool = False) -> dict[str, Any]:
    summary = _summary(mode="activity_ids", region=ctx.region, output_dir=ctx.output_dir)
    valid_ids: list[int] = []
    for arg in activity_ids:
        if str(arg).startswith("--"):
            continue
        try:
            valid_ids.append(int(arg))
        except ValueError:
            message = f"参数错误: '{arg}' 不是有效活动ID"
            log(f"❌ {message}", json_mode=True)
            summary["failed"] += 1
            summary["errors"].append({"activity_id": arg, "message": message})
            summary["ok"] = False
    summary["searched"] = len(valid_ids)
    for aid in valid_ids:
        _merge_result(summary, download_and_save(ctx, aid, json_mode=json_mode))

    if not json_mode:
        if summary["failed"] == 0:
            print(f"\n🎉 全部下载完成，保存在: {ctx.output_dir}")
        else:
            print(f"\n⚠️  部分下载失败，保存在: {ctx.output_dir}")
    return summary


def list_recent_activities(ctx: RuntimeContext, limit: int = 20) -> list[dict[str, Any]]:
    """列出最近活动供选择"""
    try:
        activities = ctx.client.connectapi(
            f"/activitylist-service/activities/search/activities?start=0&limit={limit}"
        )
        if not activities:
            print("没有找到活动")
            return []

        print(f"\n📋 最近 {len(activities)} 个活动:\n")
        print(f"{'#':>3} | {'活动ID':>10} | {'日期':<12} | {'类型':<10} | {'标题'}")
        print("-" * 80)
        for i, act in enumerate(activities, 1):
            aid = act.get("activityId", "?")
            date_str = act.get("startTimeLocal", "")[:10] if act.get("startTimeLocal") else ""
            act_type = act.get("activityType", {}).get("typeKey", "?")
            title = act.get("activityName", "?")
            print(f"{i:>3} | {aid:>10} | {date_str:<12} | {act_type:<10} | {title}")
        return activities
    except Exception as e:
        print(f"获取活动列表失败: {e}", file=sys.stderr)
        return []


def _update_mode(args: argparse.Namespace) -> tuple[str, int] | None:
    modes = [
        ("update", args.update, 0),
        ("update_1m", args.update_1m, 30),
        ("update_3m", args.update_3m, 90),
        ("update_1y", args.update_1y, 365),
        ("update_2y", args.update_2y, 730),
        ("update_3y", args.update_3y, 1095),
    ]
    for mode, enabled, days in modes:
        if enabled:
            return mode, days
    return None


def print_help_and_recent(ctx: RuntimeContext) -> None:
    print("=== 佳明 FIT 文件下载工具 ===\n")
    print("用法:")
    print("  python download_fit.py <activity_id>                      # 单个活动")
    print("  python download_fit.py <id1> <id2> ...                   # 多个活动")
    print("  python download_fit.py --from YYYY-MM-DD --to YYYY-MM-DD  # 时间范围")
    print("  python download_fit.py --update                          # 更新活动（增量）")
    print("  python download_fit.py --update-1m                       # 近一个月")
    print("  python download_fit.py --update-3m                       # 近三个月")
    print("  python download_fit.py --update-1y                       # 近一年")
    print("  python download_fit.py --update-2y                       # 近两年")
    print("  python download_fit.py --update-3y                       # 近三年")
    print("  python download_fit.py --output-dir \"D:\\fitvault\\tracks\" # 指定保存目录")
    print("  python download_fit.py --from 2026-01-01 --to 2026-01-31 --json # 机器输出\n")
    list_recent_activities(ctx)


def run(args: argparse.Namespace, ctx: RuntimeContext) -> dict[str, Any] | None:
    update = _update_mode(args)
    if update:
        mode, days = update
        return do_update(ctx, last_days=days, json_mode=args.json, mode=mode)

    if args.start_date:
        start_date = args.start_date
        end_date = args.end_date or start_date
        return download_by_date_range(
            ctx,
            start_date,
            end_date,
            args.activity_type,
            json_mode=args.json,
            mode="date_range",
        )

    if args.activity_ids:
        return download_activity_ids(ctx, args.activity_ids, json_mode=args.json)

    if args.json:
        return _summary(mode="help", region=ctx.region, output_dir=ctx.output_dir)
    print_help_and_recent(ctx)
    return None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.json:
        with contextlib.redirect_stdout(sys.stderr):
            ctx = create_runtime_context(args)
            summary = run(args, ctx)
        print(json.dumps(summary or {}, ensure_ascii=False))
    else:
        ctx = create_runtime_context(args)
        run(args, ctx)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
