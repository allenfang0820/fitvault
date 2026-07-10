# ACS Phase0-01 Architecture Baseline Completion Report

更新时间：2026-07-07

## 任务目标

建立 ACS 后端工程基线与模块边界，避免后续运动生涯系统逻辑继续堆叠到 `main.py`，并为后续 schema migration 提供幂等入口。

## 已完成

- 新增 `career_backend.py`。
- 在模块 docstring 中声明 ACS 硬边界：
  - Activity 是唯一事实源。
  - Resolver 负责语义识别，ACS 负责长期组织。
  - ACS 不读取原始 FIT、原始 points 或完整活动记录。
  - AI 只能消费 Career Snapshot，不暴露本地路径、SQLite schema 或原始记录。
- 新增 `CAREER_SCHEMA_VERSION`。
- 新增 `ensure_career_schema(conn=None)`。
- 新增轻量元信息表 `career_schema_meta`。
- 新增 `tests/test_career_backend_schema.py`，覆盖导入、幂等 migration 和临时 DB 路径。

## 刻意不做

- 未新增一级导航。
- 未新增 pywebview Career API。
- 未登记未实现 API。
- 未创建 Race/PB/Achievement/Memory/Snapshot 业务表。
- 未修改 FIT 解析、AI prompt、活动导入或前端 UI。

## 兼容性说明

- 默认数据库路径通过 `profile_backend.DB_PATH` 获取。
- 路径处理使用 `pathlib.Path`。
- 测试覆盖临时 SQLite 文件路径，不依赖 macOS 专有目录。

## 后续建议

下一步进入 `ACS-Phase0-02`：修复 `_build_ai_snapshot()` 中错误的 `profile_backend._DB_PATH` 引用，保证后续 Career Snapshot / AI Career Insight 的边界基础可靠。
