# ACS-Phase9-03：应用受控目录与中文文件名兼容性审计完成报告

## 任务范围

本任务完成 ACS 应用受控目录、中文文件名、中文标题与路径泄漏边界的代码层审计。

本任务只做：

- 审计 ACS 记忆故事和媒体引用的中文输入处理。
- 审计 ACS media_ref 的受控目录与逻辑引用边界。
- 加固 media_ref 路径穿越识别。
- 补充中文标题、中文正文、中文媒体逻辑引用、前端安全转义测试。
- 更新 ACS 开发任务清单。

未做：

- 不做 Windows 真机验证。
- 不做 Windows 打包验证。
- 不新增真实文件复制、删除、上传或选择器流程。
- 不新增 pywebview API。
- 不改 Race / PB / Achievement 事实识别规则。
- 不接真实 AI，不调用 `call_llm` 或 `llm_backend`。

## 后端加固

`career_backend._normalize_memory_media_ref()` 增加 URL 解码后的路径穿越检查：

- 对 media_ref 最多进行两轮 `urllib.parse.unquote()`。
- 原始值和解码值都执行安全检查。
- 继续拒绝：
  - POSIX 绝对路径
  - Windows 盘符路径
  - UNC 路径
  - `file:` URL
  - `~`
  - 反斜杠
  - 空字节
  - `/Users/`
  - `/tmp/`
  - `..`
  - `%2e%2e` 编码路径穿越

仍允许逻辑引用：

- `memory/...`
- `asset:memory:...`

并新增验证中文逻辑引用：

- `memory/photo/苏州 10K 终点.jpg`

API 返回仍只暴露 `has_media` 与空 `thumbnail_url`，不返回 `storage_ref` 或本地路径。

## 中文标题与正文

已验证：

- Story title 支持中文、空格和数字混排。
- Story text 支持中文正文。
- 中文 title / story 保存后可通过 `get_career_memory()` 返回。
- 返回 view model 不包含 `path`、`file_path`、`storage_ref`、raw FIT、points、track_json 或 SQLite schema。

## 前端安全边界

`track.html` 中 Career Memory 相关渲染继续使用白名单字段：

- `id`
- `activity_id`
- `race_id`
- `type`
- `title`
- `story`
- `date`
- `thumbnail_url`
- `has_media`
- `detail_link`

本轮确认并补充测试：

- `careerMemoryItemHtml()` 对 title、story、meta 使用 `safeHtml()`。
- `renderCareerMemoryEditForm()` 对编辑表单中的 title/story 使用 `safeHtml()`。
- 前端 Memory 区块不读取、不拼接本地路径。
- 前端 Memory 区块不调用 `save_career_memory_media`，不提供上传/选文件入口。

## Envelope 兼容修复

本轮发现并修复一个代码层运行时风险：

- `track.html` 中部分 Career 逻辑已调用 `requireCareerApiData()`，但 helper 缺失。
- 已补齐 `careerApiErrorMessage()` 与 `requireCareerApiData()`。
- `loadCareerOverview()`、`loadCareerMemory()`、`saveCareerMemoryStory()` 已接入统一 envelope 解析。

这保证非对象返回、`ok=false`、`code != 0`、缺失 `data` 时进入局部错误态，而不是当作成功数据继续渲染。

## 修改文件

- `career_backend.py`
  - 引入 `urllib.parse.unquote`。
  - 加固 `_normalize_memory_media_ref()`，覆盖编码路径穿越。
- `track.html`
  - 补齐 Career API envelope helper。
  - `loadCareerOverview()`、`loadCareerMemory()`、`saveCareerMemoryStory()` 使用统一 envelope 解析。
- `tests/test_career_memory_story_api.py`
  - 新增中文 story title / story_text 保存与返回测试。
- `tests/test_career_memory_media_api.py`
  - 新增中文 media_ref 逻辑引用测试。
  - 新增 `%2e%2e` 编码路径穿越拒绝测试。
- `tests/test_career_memory_frontend_render.py`
  - 新增用户文本安全转义测试。
  - 更新 Memory API envelope helper 断言。
- `tests/test_career_memory_story_frontend.py`
  - 更新保存故事使用统一 envelope helper 的断言。
- `tests/test_career_phase9_pywebview_envelope.py`
  - 新增 Phase9 envelope 回归测试，覆盖中文路径临时库、ACS envelope 与前端 helper。
- `docs/脉图运动生涯系统（ACS）开发任务清单.md`
  - 新增并勾选 `ACS-Phase9-03`。

## 安全边界确认

- 未读取或暴露 raw FIT。
- 未读取或暴露 points / points_json / track_json。
- 未返回本地绝对路径、`file_path`、`storage_ref` 或 SQLite schema。
- 未向 AI 输入加入本地路径、SQLite schema 或原始 Activity 事实。
- 未新增真实 AI 调用。
- 未新增 pywebview API。
- 未新增真实文件复制、删除、上传或选择器流程。
- 未将 Windows 真机或打包验证标记为完成。

## 验证结果

已通过：

```bash
python3 -m pytest tests/test_career_memory_story_api.py tests/test_career_memory_media_api.py tests/test_career_memory_api.py
python3 -m pytest tests/test_career_snapshot_persistence.py tests/test_career_insight_api_skeleton.py
python3 -m pytest tests/test_career_memory_frontend_render.py tests/test_career_memory_story_frontend.py tests/test_career_memory_story_edit_frontend.py tests/test_career_memory_media_frontend.py
python3 -m pytest tests/test_career_phase9_pywebview_envelope.py tests/test_track_html_sync_logic.py
```

结果：

- `23 passed`
- `21 passed`
- `29 passed`
- `27 passed`

仅出现环境级 urllib3 / LibreSSL warning，与本任务无关。

## Windows 后置说明

用户已明确要求：需要 Windows 操作的任务往后排，先完成开发后再进入打包验证。

因此以下仍未完成：

- Windows 打包后 SQLite 可读写验证。
- Windows 真机 FIT 导入后 ACS 刷新验证。
- Windows 真机中文文件名验证。
- Windows 真机中文标题编辑验证。
- Windows 真机 pywebview 慢初始化验证。
- Windows 真机时间轴滚动性能验证。

## 下一个建议任务

建议进入：

`ACS-Phase9-04：开发完成前的 ACS 数据边界与前端零推断总审计`

