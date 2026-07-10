# ACS-Phase9-01：ACS SQLite migration 与路径兼容性审计完成报告

## 任务范围

本任务完成 ACS 在 macOS / Windows 双系统兼容方向的第一轮代码层审计，聚焦 SQLite migration、默认 DB 路径、媒体引用路径安全，以及 Career API / Snapshot 禁止字段边界。

本任务只做：

- 审计 ACS SQLite migration 幂等性。
- 审计 ACS 默认 DB 路径是否使用 `Path` 并支持中文与空格目录。
- 加固 ACS 公共 metadata 与 Career Snapshot 禁止字段过滤。
- 补充路径兼容与禁止字段回归测试。
- 更新 ACS 开发任务清单。

未做：

- 不做 Windows 真机验证。
- 不做 Windows 打包验证。
- 不改 Race / PB / Achievement / Memory 的事实识别规则。
- 不新增 pywebview API。
- 不接真实 AI。
- 不调用 `call_llm` 或 `llm_backend`。
- 不改变 ACS API envelope。

## 审计结论

### SQLite migration

`career_backend.ensure_career_schema()` 当前保持幂等：

- `career_schema_meta` 使用 `CREATE TABLE IF NOT EXISTS`。
- ACS 派生表使用 `CREATE TABLE IF NOT EXISTS`。
- ACS 索引使用 `CREATE INDEX IF NOT EXISTS`。
- 增量列使用 `_add_column_if_missing()` 检查后再 `ALTER TABLE`。
- schema version 使用 `INSERT ... ON CONFLICT(key) DO UPDATE`。

本轮新增中文与空格路径测试，确认默认 DB 路径的父目录可自动创建，重复 migration 不会重复创建表或报错。

### 路径兼容

`career_backend._connect_default()` 使用：

- `Path(profile_backend.DB_PATH).expanduser()`
- `db_path.parent.mkdir(parents=True, exist_ok=True)`
- `sqlite3.connect(str(db_path))`

该路径边界符合 macOS / Windows 兼容原则：内部使用 `Path`，仅在 SQLite 连接边界转为字符串。

### 本地路径泄漏防护

本轮加固：

- `_sanitize_public_metadata()` 的禁止字段过滤改为大小写不敏感。
- `_snapshot_has_forbidden_key()` 的禁止字段检查改为大小写不敏感。

因此以下大小写变体不会穿过 ACS 公共 metadata 或 Snapshot 写入守卫：

- `File_Path`
- `Storage_Ref`
- `SQLite_Schema`

媒体记忆引用继续只允许：

- `memory/...`
- `asset:memory:...`

并拒绝：

- `/Users/...`
- `/tmp/...`
- `C:/Users/...`
- `C:\Users\...`
- `\\server\share\...`
- `file:///Users/...`
- `file://C:/Users/...`
- `memory/.../../...`

## 修改文件

- `career_backend.py`
  - ACS public metadata 禁止字段过滤改为大小写不敏感。
  - Career Snapshot 禁止字段守卫改为大小写不敏感。
- `tests/test_career_backend_schema.py`
  - 新增中文与空格 SQLite DB 路径 migration 幂等测试。
- `tests/test_career_races_api.py`
  - 禁止字段断言改为大小写不敏感。
  - 扩展 public metadata 清洗测试，覆盖大小写变体禁止字段。
- `tests/test_career_memory_media_api.py`
  - 扩展 Windows 风格本地路径与 file URL 拦截测试。
- `tests/test_career_snapshot_persistence.py`
  - 禁止字段断言改为大小写不敏感。
  - 扩展历史脏 Snapshot 清洗测试。
  - 新增 Snapshot 禁止字段守卫大小写不敏感测试。
- `docs/脉图运动生涯系统（ACS）开发任务清单.md`
  - 新增并勾选 `ACS-Phase9-01`，说明仅完成代码层审计。

## 安全边界确认

- 未读取或暴露 raw FIT。
- 未读取或暴露 points / points_json / track_json。
- 未返回 `file_path`、`storage_ref`、本地绝对路径或 SQLite schema。
- 未向 AI 输入加入本地路径、SQLite schema 或原始 Activity 事实。
- 未新增真实 AI 调用。
- 未新增 pywebview API。
- API 返回结构继续由 `main.Api` 包装为 `{ok, code, msg, data, traceId}`。

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_backend_schema.py tests/test_career_races_api.py tests/test_career_memory_media_api.py tests/test_career_snapshot_persistence.py
python3 -m pytest tests/test_career_snapshot_builder.py
```

结果：

- `34 passed`
- `5 passed`

仅出现环境级 urllib3 / LibreSSL warning，与本任务无关。

## 未完成项

以下仍保留在 Phase9 后续任务中：

- Windows 打包后验证。
- Windows 真机 SQLite 可读写验证。
- FIT 导入后 ACS 真机刷新验证。
- 中文文件名、中文标题编辑真机验证。
- 时间轴滚动性能真机验证。
- macOS 完整应用受控目录读写验证。

## 下一个建议任务

建议进入：

`ACS-Phase9-02：pywebview API envelope 与 ACS 跨平台错误态审计`

