# ACS 年度 AI 总结最终完成报告

## 结论

除最终 DMG 打包外，年度 AI 总结任务清单已完成。

## 完成等级

| 门禁 | 状态 | 证据 |
| --- | --- | --- |
| 代码级实现 | Done | `career_backend.py`、`llm_backend.py`、`main.py`、`track.html`、`docs/js_api_contract.json` 已接入年度 Snapshot、状态机、缓存、生成 API、LLM、前端只读页面 |
| 自动化测试 | Done | 年度测试 115 passed、10 subtests；ACS 宽回归 588 passed、38 subtests |
| 真实 AI | Done | 保留 v1 既有验收；真实 DB 2025 使用运行时 OpenClaw 从 v1 原子升级为 v2，canonical 表计数不变 |
| 产品验收 | Done | 真实数据抽样与视觉逐项验收记录完成 |
| macOS `.app` 构建 | Done | `dist/acs_year_ai_08c/脉图.app` 构建成功，315M，`codesign --verify --deep --strict` 通过 |
| macOS DMG | Not Run | 按用户要求不执行最终 DMG 打包 |
| Windows 代码级 | Done | Python 编译、JSON 解析、跨平台路径/CLI/SQLite 代码路径由测试和静态检查覆盖 |
| Windows 真机 / Windows 打包 | Not Run | 当前环境为 macOS，不标记真机或 Windows 产物通过 |

## 核心契约摘要

- Activity 是唯一事实源；Race / PB / Achievement 语义由 Resolver 负责。
- 年度 AI 使用独立 Year Snapshot：`snapshot_version=acs.year.v1`、`scope=year`。
- 年度刷新由 `source_fingerprint` 驱动，不由年份是否当前年或自然日期驱动。
- 年度报告缓存使用 `career_ai_insights`，按 `scope + scope_key + snapshot_fingerprint + prompt_version + model_id` 唯一。
- AI 只写叙事草稿；后端校验 schema/evidence 后回填标题、日期、成绩、`activity_id` 和 `detail_link`。
- 年度生成 API 只接受 `year`；拒绝 prompt、Snapshot、model、force 和事实字段。
- OpenClaw CLI 默认模型跟随脉图全局大模型配置链路；年度功能不写死具体模型。
- 用户可见 v2 是一篇连续年度故事；结构化 JSON 仅作为校验、事实回填、页面编排和未来分享图片的母稿。
- AI 采用温暖、克制、真诚的语气；AI 自行复述的精确数字句由后端删除，数字只通过后端 `fact_lead` 和 evidence 节点展示。
- 同指纹 v1 报告继续可读，并可通过“升级年度故事”一次性生成 v2；失败保留 v1。
- 报告缓存时间继续以 UTC 持久化和排序；API 与页面按运行设备当地时区展示，当前真实环境验证为 `+08:00`。
- 旧 `representative_memories`、`memory_count` 和通用 MemoryItem AI 语义不进入年度 Snapshot 或年度报告。

## 关键实现范围

- `career_backend.py`
  - Year Snapshot 构建、校验、fingerprint、状态机、持久化。
  - `career_ai_insights` schema、repository、ready 原子切换。
  - `get_career_year_insight` 只读服务。
  - `validate_career_year_ai_report` AI 输出校验与事实回填。
  - `generate_career_year_insight` 生成服务、缓存幂等、single-flight、失败分类与安全日志。
- `llm_backend.py`
  - 年度 Prompt assembler。
  - 年度 LLM 调用、严格 JSON、一次格式修复。
  - OpenClaw 默认模型运行时标识。
- `main.py`
  - `get_career_year_insight(payload)`。
  - `generate_career_year_insight(payload)`。
  - pywebview envelope 与 payload 白名单。
- `track.html`
  - 年度卡片“查看年度总结”导航。
  - 年度/生涯 insight 模式。
  - v2 单列文章、v1 兼容、facts/local fallback 渲染。
  - 年份 chip、状态提示、请求隔离。
  - 生成步骤轮换、skeleton、reduced-motion 和计时器释放。
- `docs/js_api_contract.json`
  - 注册年度只读 API 与年度生成 API。

## 真实 AI 验收

### 真实 DB v2 格式升级

```text
year = 2025
report_state = ready
generation_status = generated
schema_version = acs.year.report.v2
prompt_version = acs.year.summary.zh-CN.v2
model_id = openclaw-default
section_types = annual_story / progress / rhythm / comparison
fact_lead / closing / letter_to_next_year = present
format_upgrade_available = false
canonical Activity/Race/PB/Achievement counts = unchanged
```

### 真实 DB 首次生成

```text
year = 2024
report_state = ready
generation_status = generated
prompt_version = acs.year.summary.zh-CN.v1
model_id = openclaw-default
headline = 夏日集中发力，首个10公里完赛
key_moment_count = 1
```

### 真实 DB 临时拷贝更新验证

```text
year = 2023
first_generation_state = ready
activity_count_before = 4
after_fact_change_read_state = stale
activity_count_after = 5
second_generation_state = ready
model_id = openclaw-default
```

说明：事实变化更新验证使用真实 DB 的临时拷贝，避免污染真实 Activity 表。

## 验证命令与结果

```text
.venv312/bin/python -m pytest tests/test_career_year_*.py tests/test_career_ai_insights_repository.py -q
115 passed, 10 subtests passed in 0.83s

.venv312/bin/python -m pytest tests/test_career*.py -q
588 passed, 38 subtests passed in 2.97s

.venv312/bin/python -m py_compile career_backend.py main.py llm_backend.py profile_backend.py
passed

.venv312/bin/python -m json.tool docs/js_api_contract.json >/dev/null
passed
```

macOS `.app` 构建验证：

```text
PYTHONPATH=. .venv312/bin/pyinstaller HikingTrackAnalyzer.spec --noconfirm --distpath dist/acs_year_ai_08c --workpath build/acs_year_ai_08c
Build complete

dist/acs_year_ai_08c/脉图.app
315M
codesign --verify --deep --strict --verbose=2
valid on disk; satisfies its Designated Requirement
```

未生成 DMG。

## 已知边界与风险

- 未执行 DMG 创建、DMG verify、notarization 或 Gatekeeper 分发验收。
- 未执行 Windows 真机或 Windows 打包产物验收。
- 未做真实桌面截图；08B 采用逐项人工验收记录和前端静态测试。
- 真实 DB 中保留既有 v1 缓存，并新增 2025 年度 v2 ready 报告缓存；未修改真实 Activity/Race/PB/Achievement 事实表。
- `dist/acs_year_ai_08c/脉图.app` 是 08C 构建验证产物，不是 DMG 发布物。

## 回滚方式

- 若需要撤销真实 v2 验收缓存，可在备份后删除或标记 `career_ai_insights` 中 `scope='career_year' AND scope_key='2025' AND prompt_version='acs.year.summary.zh-CN.v2'` 的相关 ready 记录；v1 superseded 行仍保留。
- 若需要撤销构建产物，可删除 `dist/acs_year_ai_08c/` 与 `build/acs_year_ai_08c/`。
- 若需要回滚代码，按 Git diff 针对年度 AI 相关文件回退，不要影响当前工作树中的其他用户改动。

## 下一步建议

1. 如需发布安装包，再执行 DMG 打包、DMG verify、临时 HOME 启动 smoke test、Gatekeeper/notarization 检查。
2. 如需补强视觉验收，启动桌面 app 后补桌面 / 窄屏截图。
3. 如需 Windows 发布，使用 Windows 真机或 CI 执行 PyInstaller 与启动 smoke test。
4. 社交媒体分享图片可在后续任务中消费 v2 母稿和后端事实，不应重新让 AI 计算成绩。
