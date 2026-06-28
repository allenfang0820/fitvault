---
name: garmin-stats
description: 佳明/Garmin 用户画像、运动健康数据、活动缓存和 FIT 文件下载 Skill。用于通过 OpenClaw/QClaw/Codex 获取佳明用户画像 JSON 数组，给脉图同步用户画像，查询 HRV、睡眠、静息心率、VO2max、PB、累计里程、最长距离，或下载佳明 FIT 文件。触发词包括「同步用户画像」「更新脉图用户画像」「查一下佳明数据」「我的HRV是多少」「跑步PB成绩」「刷新佳明缓存」「更新活动」「下载FIT文件」。
metadata:
  version: "1.0.3"
---

# garmin-stats

版本：`1.0.3`

这个 Skill 用来获取佳明/Garmin 用户画像 JSON 数组，主要供脉图用户画像同步使用；也支持刷新活动缓存和下载 FIT 文件。

## 安装

在 OpenClaw/QClaw 中使用 Skill 安装/导入功能选择 `garmin-stats.zip`。不建议让普通用户手动寻找隐藏目录；不同系统和工具的 Skill 目录可能不同。

运行环境要求：Python 3.8 或更高版本，建议 Windows 用户使用 64 位 Python 3.10/3.11。

安装依赖时，先进入 OpenClaw/QClaw 已安装的 `garmin-stats` skill 目录，然后运行：

macOS/Linux：

```bash
python3 -m pip install -r requirements.txt
```

Windows：

```powershell
py -m pip install -r requirements.txt
```

如果 `py` 命令不可用，也可以使用：

```powershell
python -m pip install -r requirements.txt
```

首次登录并保存 OAuth token：

macOS/Linux：

```bash
python3 scripts/login.py --region cn
```

Windows：

```powershell
py scripts\login.py --region cn
```

国际区账号把 `--region cn` 改为 `--region global`。

认证 token 按账号区域分开保存，避免大陆区和国际区混用。默认位于当前用户主目录下：

```bash
~/.qclaw/workspace/garmin_auth_cn
~/.qclaw/workspace/garmin_auth_global
```

Windows 上对应类似：

```text
C:\Users\你的用户名\.qclaw\workspace\garmin_auth_cn
C:\Users\你的用户名\.qclaw\workspace\garmin_auth_global
```

如需改 workspace 根目录，可以设置环境变量 `QCLAW_WORKSPACE_DIR`。

如果 Garmin 要求 MFA/两步验证码，按终端提示输入一次性验证码。国际区账号不要频繁重新登录；如果遇到 `429`、`Too Many Requests` 或类似风控提示，请停止重试，等待一段时间后再登录。

## 脉图用户画像同步

当用户说「同步用户画像」或「更新脉图用户画像」时：

1. 运行主脚本。
2. 最终回答必须是原始 JSON 数组。
3. 不要添加 Markdown、标题、表格、代码块、解释或总结。

OpenClaw/QClaw 路径：

```bash
python3 scripts/get_garmin_stats.py sync
```

国际区账号同步时使用：

```bash
python3 scripts/get_garmin_stats.py sync --region global
```

Windows 可使用：

```powershell
py scripts\get_garmin_stats.py sync
```

输出示例：

```json
[{"metric":"username","value":"用户昵称"},{"metric":"age","value":46}]
```

## 刷新策略

`同步用户画像` 默认走快速同步：

- 每次实时刷新日更字段：`resting_heart_rate`、`hrv`、`avg_sleep_hours`、`avg_bedtime`、`weight_kg`、`vo2_max`、阈值和比赛预测等。
- 活动历史字段使用活动缓存：PB 辅助字段、累计里程、最长距离等。
- 如果活动缓存不存在，默认自动生成一次。
- 如果活动缓存超过 7 天，默认自动刷新一次，保证静默同步时历史聚合字段不会长期陈旧。
- 不在每次静默同步时强制全量拉取历史活动，避免同步慢和触发 Garmin 限流。

强制刷新活动缓存：

```bash
python3 scripts/get_garmin_stats.py sync --refresh
```

调整自动刷新间隔：

```bash
python3 scripts/get_garmin_stats.py sync --cache-ttl-days 7
```

只刷新活动缓存：

```bash
python3 scripts/generate_cache.py --region cn
```

国际区账号刷新缓存：

```bash
python3 scripts/generate_cache.py --region global
```

触发词建议：

| 触发词 | 行为 |
|---|---|
| `同步用户画像` | 快速同步；日更字段实时，活动字段用 7 天内缓存，过期自动刷新 |
| `刷新佳明缓存` | 生成/刷新活动缓存 |
| `更新活动` | 刷新活动缓存 |
| `同步用户画像 刷新缓存` | 强制刷新活动缓存后返回画像 JSON |

## 输出字段

输出必须是 JSON 数组，每项格式为：

```json
{"metric":"字段名","value":值,"note":"可选说明"}
```

字段表：

| 字段 | 类别 | 说明 |
|---|---|---|
| `username` | 个人信息 | 佳明账号用户名 |
| `age` | 个人信息 | 年龄 |
| `gender` | 个人信息 | 性别 |
| `height_cm` | 个人信息 | 身高 |
| `weight_kg` | 个人信息 | 体重 |
| `bmi` | 身体成分 | BMI |
| `body_fat_percent` | 身体成分 | 体脂率 |
| `body_water_percent` | 身体成分 | 身体水分率 |
| `bone_mass_kg` | 身体成分 | 骨量 |
| `muscle_mass_kg` | 身体成分 | 肌肉量 |
| `metabolic_age` | 身体成分 | 代谢年龄 |
| `visceral_fat` | 身体成分 | 内脏脂肪等级 |
| `resting_heart_rate` | 生理指标 | 近 7 天平均静息心率 |
| `hrv` | 生理指标 | 近 7 天平均 HRV |
| `avg_sleep_hours` | 生理指标 | 近 7 天平均睡眠时长 |
| `avg_bedtime` | 生理指标 | 近 7 天平均入睡时间 |
| `vo2_max` | 生理指标 | 最大摄氧量 |
| `lactate_threshold_hr` | 生理指标 | 乳酸阈值心率 |
| `lactate_threshold_pace` | 生理指标 | 乳酸阈值配速 |
| `ftp_watts` | 生理指标 | 骑行 FTP |
| `1km_pb` | 跑步 | 1 公里 PB |
| `1mile_pb` | 跑步 | 1 英里 PB |
| `5km_pb` | 跑步 | 5 公里 PB |
| `10km_pb` | 跑步 | 10 公里 PB |
| `half_marathon_pb` | 跑步 | 半马 PB |
| `full_marathon_pb` | 跑步 | 全马 PB |
| `longest_run_km` | 跑步 | 最长跑步距离 |
| `total_run_km` | 跑步 | 累计跑步距离 |
| `race_predict_5k` | 跑步 | 5 公里比赛预测 |
| `race_predict_10k` | 跑步 | 10 公里比赛预测 |
| `race_predict_half` | 跑步 | 半马比赛预测 |
| `race_predict_full` | 跑步 | 全马比赛预测 |
| `longest_hike_km` | 徒步 | 最长徒步距离 |
| `total_hike_km` | 徒步 | 累计徒步/登山距离 |
| `longest_ride_time` | 骑行 | 最长骑行时间 |
| `cycling_40km_time` | 骑行 | 40 公里 PB |
| `cycling_80km_time` | 骑行 | 80 公里 PB |
| `longest_cycle_km` | 骑行 | 最长骑行距离 |
| `total_cycle_km` | 骑行 | 累计骑行距离 |
| `longest_swim_distance_m` | 游泳 | 最长游泳距离 |
| `total_swim_km` | 游泳 | 累计游泳距离 |
| `swimming_100m_pb` | 游泳 | 100 米 PB |

## FIT 文件下载

用户说「下载FIT文件」触发 FIT 下载流程。

```bash
python3 scripts/download_fit.py
python3 scripts/download_fit.py <activity_id>
python3 scripts/download_fit.py --from 2023-01-01 --to 2023-12-31
python3 scripts/download_fit.py --update
python3 scripts/download_fit.py --update-1m
python3 scripts/download_fit.py --update-3m
python3 scripts/download_fit.py --update-1y
```

国际区账号下载 FIT 时同样使用 `--region global`，确保读取国际区 token：

```bash
python3 scripts/download_fit.py --from 2026-01-01 --to 2026-01-31 --region global
```

Windows 可使用：

```powershell
py scripts\download_fit.py --update
```

下载文件默认保存到脉图工作区，脉图会扫描这个目录并导入 FIT：

```bash
~/.fitvault/workspace/tracks/
```

Windows 上对应类似：

```text
C:\Users\你的用户名\.fitvault\workspace\tracks
```

如果 Windows 版脉图使用了不同的 FIT 目录，可以通过参数或环境变量指定：

```powershell
py scripts\download_fit.py --update --output-dir "D:\fitvault\tracks"
```

或设置环境变量 `FITVAULT_TRACKS_DIR`。

文件名格式：

```text
{活动标题}_{活动ID}.fit
```

## 常见问题

- 认证失败：重新运行 `scripts/login.py`。
- 国际区账号认证失败：确认登录、同步、刷新缓存、下载 FIT 都使用同一个 `--region global`；遇到 `429` 不要连续重试。
- 缺依赖：在 skill 目录运行 `python -m pip install -r requirements.txt`；Windows 可运行 `py -m pip install -r requirements.txt`。
- 活动字段不是最新：运行 `刷新佳明缓存` 或 `get_garmin_stats.py sync --refresh`。
- 某些字段为 `null`：佳明账号可能没有对应数据，属于正常情况。
