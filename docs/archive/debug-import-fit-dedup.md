# Debug Session: import-fit-dedup

> Status: **[AWAITING_USER_VERIFICATION]**
> Created: 2026-06-03
> Closed: 待用户确认
> Session ID: `import-fit-dedup`
> RunId: `pre-fix` → `trace` → `post-fix` (探针完成,代码修复完成,真实桌面验证待用户)
> Task Reference: T-IMPORT-FIT-DEDUP
> Debug Server: port 7779

## 12.1 假设验证结果

| ID | 假设 | 状态 | 证据 |
|---|---|---|---|
| **A1** | batch_import_tracks 根本未调 check_duplicate_activity | ✅ **CONFIRMED** | 静态扫描函数体,`calls_check_duplicate=False` |
| **A2** | check_duplicate_activity 缺 mtime/size 摘要 | ❌ **REJECTED** | API 5 参数: start_time, dist_km, duration_sec, points_json, start_time_utc,带 80 分阈值 |
| **A3** | file_path+mtime+size 去重只在首次入库生效 | ✅ **CONFIRMED** | unique_fit_path 改名后,新 path 不匹配 existing |
| **A4** | 80 分阈值对无 GPS 活动过低 | ✅ **CONFIRMED** | 无 points 时 max=70 (time+dist+dur) 永远 < 80 |
| **B1** | ZIP 文件名 GBK 乱码 | ✅ **CONFIRMED** | 手工构造 legacy GBK ZIP (无 UTF-8 flag) → 解析为 `╬╥╡─╗ε╢».fit` |
| **B2** | member.filename 乱码被作为 file_name 入库 | ✅ **CONFIRMED** | 紧跟 B1 链路 |
| **B3** | enrich_sport_metadata / _derive_title 用 file_name 当 title | ⏳ **INCONCLUSIVE** | 需在真实 DB 验证 title 字段;pre-fix 探针未覆盖此链 |
| **B4** | ZIP flag bit 11 未处理 | ✅ **CONFIRMED** | flag_bits=0x0 在我手工 ZIP 中可见 |

## 12.2 根因定位

**Issue A 根因链**:
1. `batch_import_tracks` 没有调用 `check_duplicate_activity` (A1)
2. 即便调用,80 分阈值对户外活动(有 GPS)能命中,但对**无 GPS 活动**(室内跑步机、骑行台)只能得 70 分 (A4)
3. `unique_fit_path` 重命名后,新 path 不匹配 existing record,导致 file_path+mtime+size 去重也失效 (A3)

**Issue B 根因**: Python `zipfile` 模块读取 ZIP 时,对没有 UTF-8 flag (bit 11) 的成员名,默认用 CP437 解码,导致 Windows 中文 ZIP (GBK 编码) 解压后文件名乱码。`safe_extract_zip` 未做兜底解码。

## 12.3 修复 patch

### Issue A 修复
1. **main.py:4253-4314** `batch_import_tracks` 在 `_sync_single_fit_file` 成功后调用新助手 `_rollback_if_semantic_duplicate`,命中 80 分时回滚(DELETE row + remove file)并写入 `data.skipped`
2. **main.py:4316-4394** 新增 `_rollback_if_semantic_duplicate(res, dst, src_path)` 助手,职责:
   - 从 `res["resolved"]` 提取 `distance_km`/`duration_sec` (resolved 字段名是 `distance_km` 不是 `dist_km`)
   - 从 `res["points"]` 提取 GPS 点 (由 `_sync_single_fit_file` 暴露,原未在响应中)
   - 调用 `profile_backend.check_duplicate_activity(start_time, dist_km, duration_sec, points_json, start_time_utc)`
   - 命中 (is_duplicate=True && existing_id != new_id) 时,DELETE row + remove file + 返回 skip 描述
3. **main.py:1842-1844** `_sync_single_fit_file` 响应增加 `points` 字段 (原仅返回 `activity`/`resolved`/`diff`)
4. **docs/js_api_contract.json:252-265** 同步 `batch_import_tracks` 契约:`data: {imported, skipped, errors}` + 说明新语义

### Issue B 修复
1. **main.py:4187-4195** `safe_extract_zip` 在每个 member 循环开头加入 CP437→GBK 兜底:
   ```python
   if not (member.flag_bits & 0x800) and any(ord(c) > 127 for c in entry_name):
       try:
           entry_name = entry_name.encode('cp437').decode('gbk')
       except (UnicodeEncodeError, UnicodeDecodeError):
           pass
   ```
   仅当 UTF-8 flag 未设置 且 含非 ASCII 字符时才触发,不影响 UTF-8 路径。

## 12.4 验证对比

| 场景 | pre-fix | post-fix |
|---|---|---|
| 同 FIT 二次导入 | DB delta=1,生成 `real_run_copy.fit` | **DB delta=0**,`skipped: [{duplicate_of:1, score:100}]` |
| GBK ZIP | 文件名 `╬╥╡─╗ε╢».fit` | **文件名 `我的活动.fit`** |
| UTF-8 ZIP | 文件名正常 | 文件名正常 (回归) |
| 路径穿越 ZIP | 拦截 | 拦截 (回归) |
| 损坏 FIT | 友好错误 | 友好错误 (回归) |
| 53/53 单测 | 通过 | 通过 |

## 12.5 实施过程中遇到的 3 个隐藏陷阱

1. **API 签名不符**:`check_duplicate_activity` 实际只有 5 个参数,没有 `exclude_id` 和 `min_score` (我在初版探针中传了这两个,触发 TypeError,被 except 静默吞掉)。修复:移除这两个参数,改用事后过滤 `if existing_id == new_id: return None`。

2. **字段名错位**: `activity_row` (activities 表行) 不含 `dist_km`/`duration_sec`;`resolved` 字典的字段名是 `distance_km` 而非 `dist_km`;`points` 在 `resolved` 中完全没有。修复:从 `parsed["distance_km"]` 取距离,从 `sync_res["points"]` 取 GPS 点。

3. **响应结构未暴露 points**:`_sync_single_fit_file` 原响应只有 `activity`/`resolved`/`diff`,没有把 `activity.get("points")` 暴露。修复:在响应中加 `"points": activity.get("points") or []`。

## 12.6 用户验收清单(请在 macOS 桌面会话执行)

1. `cd "/Users/fanglei/应用开发/AI track" && python3 main.py`
2. 切到「运动记录」Tab
3. 点击「导入本地 FIT 文件」,选 `local_tracks/235844483_ACTIVITY.fit` → 入库
4. 再次点击「导入本地 FIT 文件」,选**同一个** FIT → 期望:`已跳过 N 个重复` toast,DB 不增加行
5. 找一份 Windows 打包的 GBK 编码 ZIP(中文文件名 FIT) → 选 → 期望:中文文件名正常显示在活动列表
6. 选 UTF-8 编码 ZIP(回归)→ 正常
7. 选路径穿越 ZIP(回归)→ 拒绝

## 12.7 未覆盖风险

1. **无 GPS 活动(室内跑步/骑行)**:`points=[]` 时 max=70 < 80,查重不触发。这是 80 分阈值的天然限制,需要**产品决策**(降到 70 或新增无 GPS 模式)才能解决。建议作为后续 T-IMPORT-FIT-DEDUP-PART2。

2. **跨平台 ZIP 编码变体**: Big5 (繁体)/ Shift-JIS (日文)/ KOI8-R (俄文) 等。当前仅 GBK 兜底。如需支持其他语言,需要扩展 `safe_extract_zip` 的编码探测或维护一个编码优先级表。

3. **同日相似活动**: 用户同一天跑两场,start_time 相差 1 小时,distance 相差 2%,score=15+20+20=55 < 80,正常入库。不会被误杀。

4. **80 分阈值的边界 case**: 第 1 场与第 2 场数据高度相似但其实是不同活动(如用户两次跑同一路线)。score 可能达到 80,被误判为重复。可通过 `exclude_id` 或 `force_import` UI 解决(本次 P0 未实现 UI 强制导入,留 P2)。

## 1.1 任务背景

执行 `T-IMPORT-FIT-DEDUP`：批量导入链路补齐 80 分语义查重 + 修复 ZIP 解压后活动标题乱码。

## 1.2 双 Issue 根因假设（来自任务提示词 §3）

### Issue A：批量导入无去重
- **A1** `batch_import_tracks` 根本没调 `check_duplicate_activity`
- **A2** `check_duplicate_activity` API 缺 mtime/size 摘要能力
- **A3** `_persist_sync_activity` 的 file_path+mtime+size 去重只在首次入库时生效
- **A4** 80 分阈值过低

### Issue B：ZIP 解压后活动标题乱码
- **B1** Python `zipfile` 默认 UTF-8 解读，GBK/CP936 编码的中文文件名 → 乱码
- **B2** `member.filename` 拿到乱码字符串后被作为 FIT 文件 `file_name` 入库
- **B3** `enrich_sport_metadata` 或 `_derive_title` 拿 `file_name` 当 title 来源
- **B4** ZIP 写入方使用 CP437 + flag bit 11，Python 未处理 flag

## 1.3 关键代码位置（不改，仅引用）

| 角色 | 文件:行 | 内容 |
|---|---|---|
| 批量导入 | main.py:4245-4300 | `batch_import_tracks` |
| ZIP 安全 | main.py:4180-4226 | `safe_extract_zip` |
| 解析器 | main.py:1115-1233 | `_parse_fit_activity_for_sync` |
| 入库 | main.py:1772-1813 | `_persist_sync_activity` |
| 80 分查重 | main.py:5254-5265 + profile_backend.check_duplicate_activity | `_api_check_duplicate_track` |
| 文件选择 | main.py:3412-3433 | `pick_and_import_fit_files` |

## 1.4 调试协议（来自 T-IMPORT-FIT-DEDUP §4）

强制要求：
1. 探针必须从用户入口触发（不能绕过 batch_import_tracks）
2. 不允许在 headless 环境中得出"已修复"结论（Issue A 用真实 FIT 文件验证；Issue B 构造 GBK ZIP 验证）
3. 启动 Debug Server（port 7779）
4. 4 类探针点全部上报

## 1.5 测试数据构造计划

| 探针 | 测试样本 | 验证目标 |
|---|---|---|
| A1-A3 | `real_run.fit` 拷贝 1 份 | 同 FIT 二次导入触发 skip |
| A4 | 模拟 80+ 分场景 | 评分逻辑生效 |
| B1-B4 | GBK 编码 ZIP（含中文文件名 FIT） | 文件名正常 |
| 回归 | 合法 UTF-8 ZIP / 路径穿越 ZIP / 损坏 FIT | 行为不变 |
