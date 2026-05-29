# 脉图项目审查整改任务清单

> 来源：2026-05-29 项目深度审查报告  
> 根目录：`/Users/fanglei/应用开发/AI track`  
> 任务目录：`tasks/review-remediation-20260529/`

## 统一执行约束

首要约束：所有代码修改、功能开发操作必须严格在项目已定义的架构契约约束范围内执行，不得违反项目的技术架构规范、目录结构约定及编码标准；必须遵守以下核心架构契约：FIT 字段不得直接透传 UI；Resolver 是唯一语义翻译层；DB 只存系统标准字段；UI 只能消费 DB/API 契约字段且禁止 fallback 推断；所有字段必须兜底，禁止 None/null/undefined/“/” 污染展示；高风险接口必须具备鉴权、确认或等价安全门禁；所有接口响应必须向 `{code,msg,data,traceId}` 统一响应结构演进；不得新增未文档化接口、未登记字段或本地孤立 schema。

## 待处理任务总览

| 任务编号 | 严重度 | 任务名称 | 关联问题描述 | 涉及文件与行号范围 | 专属提示词 |
|---|---|---|---|---|---|
| T001 | P0 | 修复 Resolver 平铺记录适配 | `metrics_resolver.py` 仍按 `raw/geo` 嵌套读取 FIT record，与 `fit_engine` 平铺输出不匹配，导致高级指标曲线和语义指标失效 | `metrics_resolver.py:L220-L260` | [T001_resolver_flat_record_adapter.md](./T001_resolver_flat_record_adapter.md) |
| T002 | P0 | 实现 shadow_diff 持久化闭环 | 全项目无 `shadow_diff` 字段引用，Resolver 与 Legacy 差异无法落库、查询和追踪 | `profile_backend.py:L448-L520`、`main.py:L1094-L1216`、`main.py:L3444-L3530` | [T002_shadow_diff_persistence.md](./T002_shadow_diff_persistence.md) |
| T003 | P0 | LLM 配置敏感字段脱敏 | `get_llm_config()` 将配置字典展开返回，存在 `api_key` 暴露给前端的风险 | `main.py:L2415-L2420`、`main.py:L2463-L2503`、`llm_backend.py` | [T003_llm_config_secret_redaction.md](./T003_llm_config_secret_redaction.md) |
| T004 | P0 | 高风险删除接口安全加固 | `delete_activities()` 会删除本地 FIT 文件和数据库记录，缺少二次确认、路径归属校验和操作审计 | `main.py:L3179-L3224` | [T004_delete_activities_guard.md](./T004_delete_activities_guard.md) |
| T005 | P1 | 统一 API 响应与错误码 | 多数 pywebview API 返回 `ok/error` 或散落字段，不符合统一 `{code,msg,data,traceId}` 响应契约 | `main.py:L2415-L2503`、`main.py:L3444-L3530`、`main.py:L3179-L3303` | [T005_response_envelope_error_codes.md](./T005_response_envelope_error_codes.md) |
| T006 | P1 | ZIP/FIT 批量导入资源限制 | ZIP 安全解压已有路径穿越防护，但缺少文件数量、单文件大小、总解压大小和压缩炸弹防护 | `main.py:L3228-L3303` | [T006_zip_import_resource_limits.md](./T006_zip_import_resource_limits.md) |
| T007 | P1 | 数据库 Schema 迁移一致性校验 | 审查发现实际数据库列数可能落后于代码定义，`activities` 扩展列需要幂等迁移与版本校验 | `profile_backend.py:L390-L553`、`main.py:L388-L541` | [T007_schema_migration_consistency.md](./T007_schema_migration_consistency.md) |
| T008 | P2 | 建立 pywebview js_api 契约文档 | 项目不是 HTTP 服务，未发现 OpenAPI 或等价本地 API 契约，前后端调用无法自动核验 | `main.py:L2228-L2250`、`track.html:L2775-L2997`、`docs/` | [T008_js_api_contract.md](./T008_js_api_contract.md) |
| T009 | P1 | Nominatim 地区查询完全解耦 | 地区查询已有缓存/后台逻辑，但仍需确保 FIT 入库链路不发生同步网络阻塞 | `profile_backend.py:L21`、`profile_backend.py:L1154-L1288`、`test_fit_sync.py:L216-L360` | [T009_nominatim_async_decoupling.md](./T009_nominatim_async_decoupling.md) |
| T010 | P2 | main.py 职责拆分方案落地 | B-8 未执行，`main.py` 同时承载 API、同步、解析、配置、AI Snapshot 等职责，影响契约治理 | `main.py:L2228-L3308`、`main.py:L3444-L3590`、`docs/DIR_SPEC.md` | [T010_main_py_modularization.md](./T010_main_py_modularization.md) |

## 验收要求

- 每个任务文件必须以统一首要约束开头。
- 每个任务文件必须包含任务编号、目标文件、定位行号、执行目标、禁止事项、必读文件、允许修改范围、推荐测试命令、完成后报告格式、验收标准。
- 所有目标路径均必须使用项目根目录下的完整相对路径。
- 所有代码变更必须保留现有 pywebview 本地桌面应用架构，不得擅自引入 HTTP 服务化改造。
