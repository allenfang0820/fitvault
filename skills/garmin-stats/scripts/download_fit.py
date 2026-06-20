#!/usr/bin/env python3
"""
下载佳明活动 FIT 文件，以活动标题+ID命名。

用法:
  python3 download_fit.py <activity_id>               # 下载单个活动
  python3 download_fit.py <id1> <id2> ...             # 下载多个活动
  python3 download_fit.py --from YYYY-MM-DD --to YYYY-MM-DD    # 时间范围
  python3 download_fit.py --update                     # 更新活动（上次下载至今）
  python3 download_fit.py --update-1m                  # 更新近一个月（30天）
  python3 download_fit.py --update-3m                  # 更新近三个月（90天）
  python3 download_fit.py --update-1y                  # 更新近一年（365天）
  python3 download_fit.py --update-2y                  # 更新近两年
  python3 download_fit.py --update-3y                  # 更新近三年
"""
import sys, os, json, subprocess, re, io, zipfile
from datetime import date, timedelta

# 通用移除 hermes libs
hermes_libs = os.path.expanduser("~/Library/Application Support/QClaw/hermes/libs")
if hermes_libs in sys.path:
    sys.path.remove(hermes_libs)

def _extract_option(name, default=None):
    if name in sys.argv:
        idx = sys.argv.index(name)
        try:
            value = sys.argv[idx + 1]
        except IndexError:
            value = default
        del sys.argv[idx:idx + 2]
        return value
    prefix = name + "="
    for arg in list(sys.argv):
        if arg.startswith(prefix):
            sys.argv.remove(arg)
            return arg.split("=", 1)[1]
    return default

# SSL 修复
try:
    import garth
    result = subprocess.run(
        ["curl", "-s", "--max-time", "10",
         "https://thegarth.s3.amazonaws.com/oauth_consumer.json"],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode == 0 and result.stdout.strip().startswith("{"):
        garth.sso.OAUTH_CONSUMER = json.loads(result.stdout.strip())
except Exception:
    pass

AUTH_FILE = os.path.expanduser("~/.qclaw/workspace/garmin_auth.json")
OUTPUT_DIR = os.path.expanduser("~/.fitvault/workspace/tracks")
REGION = _extract_option("--region", os.environ.get("GARMIN_REGION", "cn"))

try:
    import garminconnect, garth
except ModuleNotFoundError as exc:
    raise SystemExit(
        f"缺少依赖 {exc.name}。请先运行: pip3 install -r ~/.qclaw/skills/garmin-stats/requirements.txt"
    )

garth_client = garth.Client()
garth_client.load(AUTH_FILE)
client = garminconnect.Garmin(is_cn=(REGION == "cn"))
client.garth = garth_client
display_name = garth_client.profile["displayName"]


def sanitize_filename(name):
    """将活动标题转为安全的文件名"""
    safe = re.sub(r'[<>:"/\\|?*]', '_', name)
    safe = re.sub(r'\s+', ' ', safe).strip()
    if len(safe) > 80:
        safe = safe[:80].rstrip()
    return safe


def get_activity_detail(activity_id):
    """获取活动详情（含标题、日期）"""
    try:
        return client.garth.connectapi(
            f"/activity-service/activity/{activity_id}"
        )
    except Exception as e:
        print(f"  获取活动详情({activity_id})失败: {e}", file=sys.stderr)
        return None


def download_and_save(activity_id, activity_title=None):
    """下载并保存 FIT 文件"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 如果文件已存在，跳过
    existing = list_existing_ids()
    if activity_id in existing:
        print(f"  ⏭️  已存在，跳过 {activity_id}")
        return True

    print(f"\n📥 正在下载活动 {activity_id}...")

    if not activity_title:
        detail = get_activity_detail(activity_id)
        if detail:
            activity_title = detail.get("activityName") or str(activity_id)
        else:
            activity_title = str(activity_id)

    try:
        raw_data = client.download_activity(
            activity_id,
            dl_fmt=garminconnect.Garmin.ActivityDownloadFormat.ORIGINAL
        )
    except Exception as e:
        print(f"  ❌ 下载失败: {e}", file=sys.stderr)
        return False

    if not raw_data:
        print(f"  ❌ 下载返回空数据", file=sys.stderr)
        return False

    # 解压 ZIP（Garmin 的 ORIGINAL 下载始终是 ZIP）
    try:
        with zipfile.ZipFile(io.BytesIO(raw_data)) as zf:
            fit_files = [n for n in zf.namelist() if n.lower().endswith('.fit')]
            if not fit_files:
                print(f"  ❌ ZIP 内无 FIT 文件", file=sys.stderr)
                return False
            fit_data = zf.read(fit_files[0])
    except Exception as e:
        print(f"  ❌ 解压失败: {e}", file=sys.stderr)
        return False

    # 构造文件名：{活动标题}_{activityId}.fit
    safe_title = sanitize_filename(activity_title)
    filename = f"{safe_title}_{activity_id}.fit"
    filepath = os.path.join(OUTPUT_DIR, filename)

    with open(filepath, 'wb') as f:
        f.write(fit_data)

    print(f"  ✅ 已保存: {filename}")
    return True


def list_existing_ids():
    """扫描目录中已有的 FIT 文件，返回已下载的活动ID集合"""
    ids = set()
    if not os.path.isdir(OUTPUT_DIR):
        return ids
    pattern = re.compile(r'_(\d+)\.fit$')
    for fname in os.listdir(OUTPUT_DIR):
        if fname.endswith('.fit'):
            m = pattern.search(fname)
            if m:
                ids.add(int(m.group(1)))
    return ids


def get_latest_downloaded_date():
    """从已有 FIT 文件中找到最近下载的活动日期"""
    ids = list_existing_ids()
    if not ids:
        return None

    # 取最大的几个 ID（Garmin ID 大致递增）
    top_ids = sorted(ids, reverse=True)[:5]
    latest_date = None

    for aid in top_ids:
        detail = get_activity_detail(aid)
        if detail:
            sd = detail.get("summaryDTO") or {}
            st = sd.get("startTimeLocal")
            if st:
                try:
                    d = st[:10]
                    if latest_date is None or d > latest_date:
                        latest_date = d
                except:
                    pass

    return latest_date


def download_by_date_range(start_date, end_date, activity_type=None):
    """下载时间范围内所有活动"""
    print(f"🔍 正在搜索 {start_date} 至 {end_date} 的活动...", end="", flush=True)

    try:
        activities = client.get_activities_by_date(start_date, end_date, activity_type)
    except Exception as e:
        print(f"\n  获取活动列表失败: {e}", file=sys.stderr)
        return

    if not activities:
        print(" 未找到任何活动")
        return

    print(f" 找到 {len(activities)} 个活动")

    success, fail = 0, 0
    for act in activities:
        aid = act.get("activityId")
        if not aid:
            continue
        title = act.get("activityName") or str(aid)
        if download_and_save(aid, activity_title=title):
            success += 1
        else:
            fail += 1

    print(f"\n📊 结果: {success} 个成功, {fail} 个失败")
    print(f"📁 保存位置: {OUTPUT_DIR}")


def do_update(last_days=None):
    """执行更新下载"""
    today_str = date.today().isoformat()

    if last_days == 0:
        # 「更新活动」— 从最近已下载活动的日期到今日
        print("🔍 正在查找最近已下载的活动日期...", flush=True)
        latest = get_latest_downloaded_date()
        if not latest:
            print("  ⚠️  目录中没有已有 FIT 文件，改为下载近一个月")
            start = (date.today() - timedelta(days=30)).isoformat()
        else:
            start = latest
            print(f"  最近已下载: {latest}")
    else:
        start = (date.today() - timedelta(days=last_days)).isoformat()

    download_by_date_range(start, today_str)


def list_recent_activities(limit=20):
    """列出最近活动供选择"""
    try:
        activities = client.garth.connectapi(
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


if __name__ == "__main__":
    # 批量更新模式
    update_modes = {
        "--update": 0,       # 0 = 特殊值，表示从最近已下载至今
        "--update-1m": 30,
        "--update-3m": 90,
        "--update-1y": 365,
        "--update-2y": 730,
        "--update-3y": 1095,
    }

    for flag, days in update_modes.items():
        if flag in sys.argv:
            do_update(last_days=days)
            sys.exit(0)

    # --from/--to 时间范围
    if "--from" in sys.argv:
        try:
            from_idx = sys.argv.index("--from")
            start_date = sys.argv[from_idx + 1]
        except (ValueError, IndexError):
            print("❌ 请指定 --from YYYY-MM-DD", file=sys.stderr)
            sys.exit(1)

        try:
            to_idx = sys.argv.index("--to")
            end_date = sys.argv[to_idx + 1]
        except (ValueError, IndexError):
            end_date = start_date

        act_type = None
        if "--type" in sys.argv:
            try:
                type_idx = sys.argv.index("--type")
                act_type = sys.argv[type_idx + 1]
            except IndexError:
                pass

        download_by_date_range(start_date, end_date, act_type)

    elif len(sys.argv) > 1:
        # 指定了活动ID
        success = True
        for arg in sys.argv[1:]:
            if arg.startswith("--"):
                continue
            try:
                aid = int(arg)
                if not download_and_save(aid):
                    success = False
            except ValueError:
                print(f"❌ 参数错误: '{arg}' 不是有效活动ID", file=sys.stderr)
                success = False
        if success:
            print(f"\n🎉 全部下载完成，保存在: {OUTPUT_DIR}")
        else:
            print(f"\n⚠️  部分下载失败，保存在: {OUTPUT_DIR}")

    else:
        # 无参数，列出最近活动+帮助
        print("=== 佳明 FIT 文件下载工具 ===\n")
        print("用法:")
        print("  python3 download_fit.py <activity_id>                      # 单个活动")
        print("  python3 download_fit.py <id1> <id2> ...                   # 多个活动")
        print("  python3 download_fit.py --from YYYY-MM-DD --to YYYY-MM-DD  # 时间范围")
        print("  python3 download_fit.py --update                          # 更新活动（增量）")
        print("  python3 download_fit.py --update-1m                       # 近一个月")
        print("  python3 download_fit.py --update-3m                       # 近三个月")
        print("  python3 download_fit.py --update-1y                       # 近一年")
        print("  python3 download_fit.py --update-2y                       # 近两年")
        print("  python3 download_fit.py --update-3y                       # 近三年\n")
        list_recent_activities()
