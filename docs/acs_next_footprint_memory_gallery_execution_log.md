---
title: ACS 足迹与 Memory Gallery 执行日志
version: v0.1.0
status: In Progress
type: Execution Log
source:
  - docs/acs_next_footprint_memory_gallery_delivery_manual.md
  - docs/acs_next_footprint_memory_gallery_task_list.md
updated: 2026-07-13
---

# ACS 足迹与 Memory Gallery 执行日志

## 全局摘要

### 交付手册摘要

足迹页目标形态包含两个模块：

1. 生涯足迹：暗黑风格地图，按省份 / 州 / 行政区域点亮；只有中国足迹时显示中国地区地图并包含台湾，存在海外足迹时显示世界地图。
2. Memory Gallery：按赛事组织相册墙，4:3 卡片，封面复用赛事照片排序第一张图并与 Overview Banner 一致；点击相册展开全部照片，点击单张照片打开大图。

### 项目契约摘要

- Activity 是唯一事实源。
- 后端输出安全 ViewModel，前端只负责渲染。
- 前端不得根据标题、城市、日期或 DOM 文本推断地理区域。
- API 和前端不得暴露 raw FIT、`points_json`、`track_json`、本地路径、`storage_ref`、`file://` 或 SQLite schema。
- 生涯足迹覆盖所有有可靠地理信息的 Activity，不只限赛事。
- Memory Gallery 必须复用 Activity Detail 已有赛事照片、排序与安全预览，不另建脱离 Activity Detail 的相册事实源。
- 任务出现偏差、边界冲突或需求变化时，必须重新完整阅读交付手册和任务清单。

## FM-00：现状审计与基线冻结

### 工程级提示词

目标：

对当前 ACS 足迹页、Race Map、Memory Gallery、Activity Detail 赛事照片、Overview Banner 的实现做只读审计，冻结后续改造基线。首个任务必须总结交付手册和任务契约摘要，后续任务只刷新摘要；只有出现偏差时才完整重读手册。

范围：

- 读取 `docs/acs_next_footprint_memory_gallery_delivery_manual.md`。
- 读取 `docs/acs_next_footprint_memory_gallery_task_list.md`。
- 审计 `career_backend.py` 中 `get_career_race_map`、`get_career_memory`、Activity Detail 赛事照片、Banner 图选择逻辑。
- 审计 `main.py` 中相关 pywebview API。
- 审计 `track.html` 中足迹页、Memory Gallery、Activity Detail 照片管理、Overview Banner 前端入口。
- 审计 `docs/js_api_contract.json` 中相关 API 契约。
- 用真实 SQLite 库只读确认 `activities`、`career_race_events`、`career_memory_items` 的可用字段与数量。

约束：

- 本任务不修改业务逻辑。
- 不重写旧 Race Map，不引入新 API。
- 不触碰非 ACS 足迹 / Memory Gallery 的已有用户改动。
- 审计结论必须区分“可复用基础”和“历史过渡实现”。

验收：

- 写入执行日志，包含当前 API、前端入口、真实数据字段、照片排序 / Banner 逻辑位置、旧 Race Map 替换边界。
- 运行 `tests/test_career_race_map_api.py` 和 `tests/test_career_race_map_frontend.py`。
- 更新任务清单 FM-00 状态。

### 审计结论

当前可复用基础：

- `career_backend.get_career_race_map()` 已实现只读赛事点位 API，但它只覆盖 active Race Event，并按 Activity 起点经纬度返回点位。
- `main.Api.get_career_race_map()` 已暴露 pywebview envelope。
- `track.html` 足迹页当前包含“生涯足迹”入口，但 UI 仍是 `career-race-map-*` 赛事点位视图。
- `career_backend.get_career_memory()` 已实现轻量 MemoryItem 列表，但不是按赛事聚合的相册墙。
- Activity Detail 赛事照片能力已存在：`get_activity_race_photos`、`add_activity_race_photos`、`reorder_activity_race_photos`、`deactivate_activity_race_photo`。
- 赛事照片排序由 `_fetch_activity_race_photo_rows()`、`_update_activity_race_photo_order()` 和 `_activity_race_hero_banner_media()` 维护；排序第一张成为 `overview_banner`，可作为 Gallery 封面逻辑来源。
- `docs/js_api_contract.json` 已记录旧 Race Map、轻量 Memory、Activity Detail 赛事照片、Banner 照片相关 API。

历史过渡实现：

- `Race Map / 赛事足迹` 是经纬度点位图，不是本轮目标的行政区域点亮地图。
- 当前 Memory Gallery 是零散 `career_memory_items` 列表，不是按赛事组织的 4:3 相册墙。
- 当前足迹页文本仍以“赛事足迹 / 赛事起点 / 待补坐标”为主，需要后续任务替换为“生涯足迹 / 区域点亮 / 缺少地区信息”。

真实库基线：

- 默认库：`/Users/fanglei/.fitvault/user_profile.db`。
- `activities` 存在，当前 253 条，包含 `start_lat`、`start_lon`、`region`、`region_city`、`region_country`、`region_display`、`deleted_at` 等足迹可用字段。
- `career_race_events` 存在，当前 8 条。
- `career_memory_items` 存在，当前 6 条，其中 active photo 3 条，inactive photo 3 条。

风险：

- 当前系统 Python 导入 `profile_backend` 时可能缺少 `requests`；仓库 `.venv312/bin/python` 可正常读取真实库，后续验证优先使用 `.venv312/bin/python -m pytest`。
- 工作区已有多处非本轮改动，后续任务必须只做足迹 / Memory Gallery 范围内的增量修改。

### 完成记录

- 验证命令：`.venv312/bin/python -m pytest tests/test_career_race_map_api.py tests/test_career_race_map_frontend.py -q`
- 验证结果：`11 passed`
- 状态：Done
- 下一个任务：FM-01 生涯足迹数据契约冻结

## FM-01：生涯足迹数据契约冻结

### 摘要刷新

本轮继续沿用 FM-00 冻结的全局摘要。任务边界聚焦 `get_career_footprint(filters?)` 的 ViewModel 契约，不实现 UI，不替换旧 Race Map，不读取 raw FIT / points / 本地路径。

### 工程级提示词

目标：

冻结生涯足迹 API 的数据契约，使后续 FM-02 / FM-03 可以按同一 ViewModel 实现区域归一和只读 API。

范围：

- 更新或确认 `docs/acs_next_footprint_memory_gallery_delivery_manual.md` 与 `docs/acs_next_footprint_memory_gallery_task_list.md` 中的 `get_career_footprint` 契约。
- 新增契约测试，验证必要字段、地图模式规则、行政区域点亮规则和安全红线已写入文档。
- 本任务不实现前端地图，不读取或改写业务数据。

约束：

- `map_mode` 必须由后端返回，只能表达中国地图或世界地图模式。
- 契约必须包含 `regions`、`without_region`、`summary`、`filters`、`status`。
- 只有中国足迹时显示中国地区地图并包含台湾；存在海外足迹时显示世界地图。
- 普通 Activity 可进入生涯足迹，不依赖赛事身份。
- 缺地理信息 Activity 进入 `without_region`，不得强行点亮。
- API 和前端不得返回 raw FIT、`points_json`、`track_json`、本地路径、`storage_ref`、SQLite schema。

验收：

- 新增或更新 `tests/test_career_footprint_contract.py`。
- 运行 `.venv312/bin/python -m pytest tests/test_career_footprint_contract.py -q`。
- 更新任务清单 FM-01 状态。

### 完成记录

- 新增契约测试：`tests/test_career_footprint_contract.py`
- 验证命令：`.venv312/bin/python -m pytest tests/test_career_footprint_contract.py -q`
- 验证结果：`4 passed`
- 状态：Done
- 下一个任务：FM-02 地理区域归一 Resolver

## FM-02：地理区域归一 Resolver

### 摘要刷新

本轮实现后端内部区域归一 Resolver，为后续 `get_career_footprint` API 提供基础。任务边界仍不暴露 pywebview API、不实现前端地图、不调用在线地理编码。

### 工程级提示词

目标：

在 `career_backend.py` 中实现 Activity 地理字段到稳定地图区域的归一逻辑，支持中国省级区域、台湾区域、海外国家级区域和缺失原因。

范围：

- 新增中国地区 key / alias 映射，至少覆盖常见省级区域并包含台湾。
- 新增海外国家级归一映射。
- 新增内部函数 `_resolve_career_footprint_region(row)` 和 `_career_footprint_missing_reason(row)`。
- 新增后端单测覆盖中国城市到省份、台湾、海外国家、缺失地理信息、不从标题推断。

约束：

- 只读取 Activity 地理字段，如 `region_country`、`region`、`region_display`、`region_city`、`city`。
- 不读取 raw FIT、points、`points_json`、`track_json` 或本地路径。
- 不调用在线地理编码。
- 不从标题推断城市或区域。
- 缺失或无法映射时返回缺失原因，不强行点亮。

验收：

- 运行 `.venv312/bin/python -m pytest tests/test_career_footprint_api.py -q`。
- 运行 `.venv312/bin/python -m pytest tests/test_career_footprint_contract.py -q`。

### 完成记录

- 新增后端内部 Resolver：`_resolve_career_footprint_region(row)`。
- 新增缺失原因函数：`_career_footprint_missing_reason(row)`。
- 新增中国省级 / 台湾 / 港澳 / 海外国家级基础映射。
- 新增测试：`tests/test_career_footprint_api.py`。
- 验证命令：`.venv312/bin/python -m pytest tests/test_career_footprint_api.py tests/test_career_footprint_contract.py -q`
- 验证结果：`11 passed`
- 状态：Done
- 下一个任务：FM-03 `get_career_footprint` 只读 API

## FM-03：`get_career_footprint` 只读 API

### 摘要刷新

本轮将 FM-02 的区域归一 Resolver 接入正式后端 API。任务边界仍保持后端只读：不实现地图 UI，不替换旧前端 Race Map，不读取轨迹 points 或本地路径。

### 工程级提示词

目标：

新增 `get_career_footprint(filters?)` 只读 API，并通过 `main.Api` 暴露给 pywebview，输出生涯足迹地图所需的安全 ViewModel。

范围：

- `career_backend.py`：新增 Activity-backed 区域聚合 API。
- `main.py`：新增 pywebview wrapper。
- `docs/js_api_contract.json`：注册只读 API 契约。
- `tests/test_career_footprint_api.py`：覆盖 API 行为、envelope 和契约注册。

约束：

- 只读取未删除 Activity。
- 普通 Activity 可进入生涯足迹，不依赖赛事身份。
- Race Event 只用于统计 `race_count`，不作为足迹唯一来源。
- 不读取或返回 raw FIT、points、`points_json`、`track_json`、本地路径、`storage_ref`、SQLite schema。
- `map_mode` 只能由后端基于区域事实返回 `china` 或 `world`。
- 缺地理信息 Activity 进入 `without_region`。

验收：

- 无 `activities` 表时稳定空态。
- 中国-only 数据返回 `map_mode = china`。
- 海外数据返回 `map_mode = world`。
- 普通 Activity 参与区域统计。
- 删除 Activity 不参与统计。
- pywebview envelope 通过测试。

### 完成记录

- 新增 `career_backend.get_career_footprint()`。
- 新增 `main.Api.get_career_footprint()`。
- 更新 `docs/js_api_contract.json` 注册 `get_career_footprint`。
- 扩展 `tests/test_career_footprint_api.py` 覆盖中国-only、海外、缺地区、删除排除、envelope 与契约注册。
- 验证命令：`.venv312/bin/python -m pytest tests/test_career_footprint_api.py tests/test_career_phase9_pywebview_envelope.py -q`
- 验证结果：`16 passed`
- 补充验证：`.venv312/bin/python -m pytest tests/test_career_footprint_contract.py -q`，结果 `4 passed`
- 状态：Done
- 下一个任务：FM-04 地图资源与区域 key 对齐

## FM-04：地图资源与区域 key 对齐

### 摘要刷新

本轮不实现地图 UI，只建立本地离线地图区域资源目录，并用测试保证后端 `region_key` 能被前端资源识别。地图资源必须包含台湾，不依赖在线 CDN。

### 工程级提示词

目标：

新增足迹地图区域资源文件，覆盖中国地区地图和世界地图的 key/name/layout 基础信息，并与后端 Resolver 输出 key 对齐。

范围：

- 新增本地资源文件，例如 `assets/career_footprint_map_regions.json`。
- 中国地图资源必须包含全部后端中国区域 key，尤其 `CN-TW`。
- 世界地图资源必须包含后端海外国家 key。
- 新增 `tests/test_career_footprint_map_assets.py` 验证资源完整性和离线约束。

约束：

- 不接入在线地图或 CDN。
- 不实现前端交互。
- 不读取用户数据。
- 不改变 `get_career_footprint` API 输出。

验收：

- 后端中国区域 key 均能在中国地图资源中找到。
- 台湾区域 key 能在中国地图资源中找到。
- 后端海外国家 key 均能在世界地图资源中找到。
- 资源文件不包含 `http://`、`https://`、CDN 字样。

### 完成记录

- 新增本地资源：`assets/career_footprint_map_regions.json`。
- 中国资源覆盖后端所有 `CAREER_FOOTPRINT_CHINA_REGION_SPECS` key，并包含 `CN-TW`。
- 世界资源覆盖后端 `CAREER_FOOTPRINT_COUNTRY_SPECS` 国家 key。
- 新增测试：`tests/test_career_footprint_map_assets.py`。
- 验证命令：`.venv312/bin/python -m pytest tests/test_career_footprint_map_assets.py tests/test_career_footprint_api.py -q`
- 验证结果：`17 passed`
- 状态：Done
- 下一个任务：FM-05 暗黑地图前端骨架

## FM-05：暗黑地图前端骨架

### 摘要刷新

本轮将 FM-03 `get_career_footprint` 与 FM-04 本地区域资源接入足迹页前端。任务边界只做地图骨架、区域点亮、筛选、summary、空态和局部错误态；不实现区域详情面板和代表 Activity 回跳，那部分留给 FM-06。

### 工程级提示词

目标：

在 `track.html` 足迹页实现“生涯足迹”暗黑地图前端骨架，替换旧的赛事起点散点图入口。

范围：

- `track.html`：新增 `career-footprint-*` CSS、DOM、JS normalizer、render、loading/error、filter change 和 `loadCareerFootprint(filters)`。
- `tests/test_career_footprint_frontend.py`：新增前端静态契约测试。
- `tests/test_career_race_map_frontend.py`：迁移旧 Race Map 断言，确认足迹页不再加载旧赛事点位视图。

约束：

- 前端调用 `api.get_career_footprint(nextFilters)`。
- 前端只信后端 `map_mode` 决定中国地图或世界地图。
- 前端只用本地区域资源 `CAREER_FOOTPRINT_MAP_REGIONS` 对齐 `region_key` 并点亮。
- 前端 normalizer 必须白名单字段，不使用 `Object.assign` 或 `...item` 透传。
- 前端不得读取 raw FIT、points、`points_json`、`track_json`、本地路径、`storage_ref`、SQLite schema。
- 不实现 FM-06 的区域详情面板和代表 Activity 回跳。

验收：

- 足迹页包含 `career-footprint-map`、筛选器、summary metrics、缺地区列表和空态。
- `loadCareerData()` 调用 `loadCareerFootprint()`，不再调用旧 `loadCareerRaceMap()`。
- 中国资源包含 `CN-TW`，资源不依赖在线 URL 或 CDN。
- 目标测试通过。

### 完成记录

- 替换足迹页旧 `career-race-map-*` 前端入口为 `career-footprint-*` 暗黑地图骨架。
- 新增 `CAREER_FOOTPRINT_MAP_REGIONS` 本地前端区域资源快照，包含中国 / 世界模式和 `CN-TW`。
- 新增 `normalizeCareerFootprintRegion()`、`normalizeCareerFootprintMissing()`、`normalizeCareerFootprint()` 白名单 normalizer。
- 新增 `loadCareerFootprint()` 调用 `api.get_career_footprint(nextFilters)` 并使用统一 envelope。
- 新增测试：`tests/test_career_footprint_frontend.py`。
- 更新旧 Race Map 前端测试为迁移后兼容断言：`tests/test_career_race_map_frontend.py`。
- 验证命令：`.venv312/bin/python -m pytest tests/test_career_footprint_frontend.py tests/test_career_race_map_frontend.py tests/test_career_footprint_map_assets.py tests/test_career_footprint_api.py -q`
- 验证结果：`24 passed`
- 状态：Done
- 下一个任务：FM-06 地图交互与详情回跳

## FM-06：地图交互与详情回跳

### 摘要刷新

本轮在 FM-05 暗黑地图骨架上补齐区域交互。任务边界聚焦 hover/focus 摘要、click 详情面板和代表 Activity 回跳；不改变后端 `get_career_footprint` 契约，不新增地理推断逻辑。

### 工程级提示词

目标：

完善生涯足迹地图区域交互，使用户能通过鼠标、键盘查看区域摘要，并从已点亮区域回跳代表 Activity Detail。

范围：

- `track.html`：新增 hover 摘要卡片、区域详情面板、区域状态索引、preview/select 交互函数。
- `tests/test_career_footprint_frontend.py`：扩展前端交互契约测试。

约束：

- hover/focus/click 只能通过 `data-region-key` 查后端 ViewModel 和本地区域资源。
- 不从标题、城市、日期或 DOM 文本反查 Activity 或推断地理区域。
- 详情面板展示活动数、赛事数、首次活动、最近活动。
- 有 `representative_activity_id` / `detail_link` 时复用 `openCareerActivityDetailFromElement(this)` 打开 Activity Detail。
- 局部 loading/error 必须清理旧详情面板，不影响其他 Career 模块。

验收：

- 区域按钮具备 hover/focus 摘要和 click 详情入口。
- 详情面板包含 Activity / Race / first / latest 四项摘要。
- 代表 Activity 按钮复用既有 Activity Detail 打开链路。
- 前端测试覆盖不从原始标题或 `region_display` 推断。

### 完成记录

- 新增 `career-footprint-hover-card` 和 `career-footprint-detail-panel`。
- 新增 `getCareerFootprintRegionState()`、`renderCareerFootprintPreview()`、`previewCareerFootprintRegion()`、`clearCareerFootprintPreview()`、`renderCareerFootprintDetail()`、`selectCareerFootprintRegion()`。
- 区域按钮新增 `onmouseenter`、`onfocus`、`onclick` 和 `data-region-key`。
- 已点亮区域可显示活动数、赛事数、首次活动、最近活动；有代表 Activity 时可打开详情。
- 验证命令：`.venv312/bin/python -m pytest tests/test_career_footprint_frontend.py tests/test_career_footprint_api.py tests/test_career_overview_activity_detail_link.py -q`
- 验证结果：`25 passed`
- 状态：Done
- 下一个任务：FM-07 Memory Gallery 相册 ViewModel

## FM-07：Memory Gallery 相册 ViewModel

### 摘要刷新

本轮实现 Memory Gallery 后端赛事相册 ViewModel。任务边界只做后端只读 API、pywebview wrapper、契约注册和测试；不实现前端相册墙、展开或大图预览。

### 工程级提示词

目标：

新增 `get_career_memory_gallery(filters?)`，按 active Race Event / 赛事 Activity 聚合相册，并复用 Activity Detail 赛事照片排序和安全预览。

范围：

- `career_backend.py`：新增 Gallery filters、album / cover / summary 构建函数和只读 API。
- `main.py`：新增 `Api.get_career_memory_gallery()`。
- `docs/js_api_contract.json`：注册只读 API 契约。
- `tests/test_career_memory_gallery_api.py`：新增后端契约测试。

约束：

- 相册以 active Race Event / 赛事 Activity 为单位。
- 每个相册返回 `race_id`、`activity_id`、赛事标题、时间、地点、封面、照片列表。
- `photos` 必须复用 Activity Detail 赛事照片排序。
- `cover` 必须使用第一张 active 照片，保持与 Overview Banner 第一张图逻辑一致。
- 无照片赛事返回空相册，不伪造照片。
- 只返回 data:image 安全预览或空字符串，不返回 `storage_ref`、本地路径、`file://`、raw FIT、points、`track_json` 或 SQLite schema。

验收：

- 有照片赛事返回封面和照片列表。
- 重排照片后 Gallery 封面随第一张照片变化，并与 Activity Detail hero banner 一致。
- 软删除照片不出现在相册中。
- 无照片赛事稳定返回空相册。
- pywebview envelope 和 JS API 契约注册通过测试。

### 完成记录

- 新增 `career_backend.get_career_memory_gallery()`。
- 新增 `_normalize_memory_gallery_filters()`、`_memory_gallery_cover_from_photos()`、`_build_memory_gallery_album()`、`_summarize_memory_gallery_albums()`。
- 新增 `main.Api.get_career_memory_gallery()`。
- 更新 `docs/js_api_contract.json` 注册 `get_career_memory_gallery`。
- 新增测试：`tests/test_career_memory_gallery_api.py`。
- 验证命令：`.venv312/bin/python -m pytest tests/test_career_memory_gallery_api.py tests/test_career_media_safe_preview_api.py tests/test_career_phase9_pywebview_envelope.py -q`
- 验证结果：`13 passed`
- 状态：Done
- 下一个任务：FM-08 Memory Gallery 相册墙前端

## FM-08：Memory Gallery 相册墙前端

### 摘要刷新

本轮实现 Memory Gallery 前端相册墙。任务边界聚焦 4:3 赛事相册卡片、封面 / 空封面、相册 summary、loading/error 和 API 接入；点击后展开照片网格留给 FM-09。

### 工程级提示词

目标：

在足迹页 Memory Gallery 区域渲染按赛事组织的 4:3 相册卡片墙，接入 FM-07 的 `get_career_memory_gallery(filters?)`。

范围：

- `track.html`：新增相册卡片 CSS、album/photo normalizer、album card renderer、Gallery API loader。
- `tests/test_career_memory_gallery_frontend.py`：新增前端相册墙契约测试。
- 迁移旧 Memory 前端测试到赛事相册墙语义。

约束：

- 前端调用 `window.pywebview.api.get_career_memory_gallery`。
- 卡片比例固定 `aspect-ratio: 4 / 3`。
- 卡片显示封面、赛事标题、时间、地点、照片数。
- 无封面时显示稳定空相册状态，不展示假照片。
- 前端只使用后端白名单字段，不读取或拼接 `storage_ref`、本地路径、`file://`、raw FIT、points、`track_json` 或 SQLite schema。
- 不实现照片网格展开和大图预览。

验收：

- Memory 区域仍无上传入口。
- `loadCareerMemory()` 使用 `get_career_memory_gallery` 和统一 envelope。
- normalizer 白名单 `albums/cover/photos`。
- 卡片可点击并记录 album id，供 FM-09 展开使用。

### 完成记录

- Memory Gallery 前端由旧 `career_memory_items` 列表切换为赛事相册墙。
- 新增 `normalizeCareerMemoryAlbum()`、`normalizeCareerMemoryPhoto()` 和 `careerMemoryAlbumCardHtml()`。
- `loadCareerMemory()` 改为调用 `get_career_memory_gallery`。
- 新增测试：`tests/test_career_memory_gallery_frontend.py`。
- 迁移测试：`tests/test_career_memory_frontend_render.py`、`tests/test_career_memory_media_frontend.py`、`tests/test_career_gap_p1_11_frontend_data_linkage.py`。
- 验证命令：`.venv312/bin/python -m pytest tests/test_career_memory_gallery_frontend.py tests/test_career_memory_frontend_render.py tests/test_career_memory_media_frontend.py tests/test_career_gap_p1_11_frontend_data_linkage.py -q`
- 验证结果：`25 passed`
- 状态：Done
- 下一个任务：FM-09 单场赛事相册展开

## FM-09：单场赛事相册展开

### 摘要刷新

本轮在 FM-08 相册墙基础上实现页面内相册展开。任务边界包含点击相册、展示该赛事全部照片、返回相册墙和空相册状态；单张照片大图 modal 留给 FM-10。

### 工程级提示词

目标：

点击 Memory Gallery 相册卡片后，展开该赛事已上传的全部照片，并支持返回相册墙。

范围：

- `track.html`：新增相册详情容器、照片网格 CSS、展开 / 返回状态函数、照片单元格渲染。
- `tests/test_career_memory_gallery_frontend.py`：扩展相册展开契约测试。

约束：

- 展开视图只使用 FM-07 后端返回的 `photos` 排序。
- 不重新请求媒体路径，不拼接本地路径。
- 无照片赛事显示稳定空态。
- 图片加载失败只影响当前图片单元，不影响相册关闭或返回。
- 不实现大图预览。

验收：

- 点击相册记录 `selectedMemoryAlbumId` 并渲染详情。
- 展开页展示赛事标题、时间地点、照片数量。
- 照片网格按后端顺序渲染。
- 返回按钮清空选择并回到相册墙。

### 完成记录

- 新增 `career-memory-album-detail` 容器。
- 新增 `careerMemoryAlbumMeta()`、`findCareerMemoryAlbumById()`、`careerMemoryPhotoCellHtml()`、`renderCareerMemoryAlbumDetail()`、`openCareerMemoryAlbum()`、`closeCareerMemoryAlbum()`。
- 渲染逻辑支持相册墙 / 单相册详情两种状态。
- 验证命令：`.venv312/bin/python -m pytest tests/test_career_memory_gallery_frontend.py tests/test_career_memory_frontend_render.py tests/test_career_memory_media_frontend.py -q`
- 验证结果：`21 passed`
- 状态：Done
- 下一个任务：FM-10 单张照片大图预览

## FM-10：单张照片大图预览

### 摘要刷新

本轮在 FM-09 相册展开基础上实现单张照片大图预览。任务边界包含打开、关闭、上一张 / 下一张、ESC 关闭、左右键切换和图片局部错误态；不新增后端 API，不读取媒体路径。

### 工程级提示词

目标：

点击相册照片后打开大图预览，并支持键盘和按钮操作。

范围：

- `track.html`：新增照片 modal CSS、modal 容器、打开 / 关闭 / 切换 / 键盘处理函数。
- `tests/test_career_memory_gallery_frontend.py`：扩展大图预览契约测试。

约束：

- 大图使用后端返回的 `preview_url`，无 preview 时 fallback 到 `thumbnail_url`。
- 不拼接本地路径，不读取 `storage_ref`。
- 第一张和最后一张边界稳定，不循环跳转。
- ESC 关闭，左右键切换仅在 modal 可见时生效。
- 图片加载失败只影响 modal 当前图。

验收：

- 照片格子点击调用 `openCareerMemoryPhoto(this)`。
- modal 显示序号、关闭、上一张、下一张。
- `stepCareerMemoryPhoto(delta)` 对索引做边界夹取。
- 全局 keydown 只在 modal 可见时处理 ESC / ArrowLeft / ArrowRight。

### 完成记录

- 新增 `career-memory-photo-modal`。
- 新增 `currentCareerMemoryAlbum()`、`currentCareerMemoryPhotos()`、`renderCareerMemoryPhotoModal()`、`openCareerMemoryPhoto()`、`closeCareerMemoryPhoto()`、`stepCareerMemoryPhoto()`、`onCareerMemoryPhotoModalKeydown()`。
- 相册退出和 loading 会清理 modal 状态。
- 验证命令：`.venv312/bin/python -m pytest tests/test_career_memory_gallery_frontend.py tests/test_career_memory_frontend_render.py tests/test_career_memory_media_frontend.py -q`
- 验证结果：`22 passed`
- 状态：Done
- 下一个任务：FM-11 安全边界与前端零推断验收

## FM-11：安全边界与前端零推断验收

### 摘要刷新

本轮对生涯足迹和 Memory Gallery 做统一安全边界验收。任务边界只补测试和必要的契约迁移，不新增产品行为。

### 工程级提示词

目标：

验证本轮新增足迹地图和 Memory Gallery 前后端均遵守安全 ViewModel、前端零推断、无路径泄露、无原始对象透传的契约。

范围：

- 新增或扩展自动化测试。
- 覆盖 `get_career_footprint`、`get_career_memory_gallery`、前端 normalizer、渲染函数和 loader。

约束：

- API 不返回 raw FIT、points、`points_json`、`track_json`、`storage_ref`、`file_path`、本地路径、`file://` 或 SQLite schema。
- 前端 normalizer 不使用 `Object.assign` 或 `...item` / `...album` / `...photo` 透传。
- 前端不从标题、城市、日期或 DOM 文本推断地图模式或区域 key。
- Memory Gallery 不绕过后端直接读取媒体路径。

验收：

- `tests/test_career_footprint_memory_gallery_security.py` 通过。
- 现有 Phase9 数据边界测试通过。
- 足迹前端和 Gallery 前端目标测试通过。

### 完成记录

- 新增测试：`tests/test_career_footprint_memory_gallery_security.py`。
- 覆盖新前端 normalizer / renderer 的 forbidden token、透传和旧 `get_career_memory` 调用检查。
- 覆盖后端 `get_career_footprint` 与 `get_career_memory_gallery` forbidden field 检查。
- 验证命令：`.venv312/bin/python -m pytest tests/test_career_footprint_memory_gallery_security.py tests/test_career_phase9_data_boundary_audit.py tests/test_career_footprint_frontend.py tests/test_career_memory_gallery_frontend.py tests/test_career_memory_gallery_api.py -q`
- 验证结果：`23 passed`
- 状态：Done
- 下一个任务：FM-12 真实数据与视觉验收

## FM-12：真实数据与视觉验收

### 摘要刷新

本轮完成真实库验收、静态视觉契约验收、最终相关回归和验收报告。Windows 真机、打包产物和截图自动化不在当前环境完成，按任务清单记录为后续验收项。

### 工程级提示词

目标：

用当前真实库和自动化测试确认生涯足迹与 Memory Gallery 可用，并沉淀验收报告。

范围：

- 真实库只读调用 `get_career_footprint()` 和 `get_career_memory_gallery()`。
- 新增 `docs/acs_next_footprint_memory_gallery_acceptance_report.md`。
- 运行相关最终回归。

约束：

- 不改真实库。
- 不执行打包。
- 不把未执行的 Windows / 打包 / 截图验收伪装成已完成。

验收：

- 当前真实库能返回足迹和 Gallery 数据。
- 验收报告记录真实数据、视觉契约、安全边界、未执行项和验证命令。
- 最终相关回归通过。

### 完成记录

- 新增验收报告：`docs/acs_next_footprint_memory_gallery_acceptance_report.md`。
- 真实库结果：
  - `get_career_footprint`: `map_mode=world`，`activity_count=253`，`region_count=6`，`country_count=2`，`without_region_count=25`。
  - `get_career_memory_gallery`: `album_count=5`，`photo_count=3`，`empty_album_count=2`，`cover_count=3`。
- 最终验证命令：`.venv312/bin/python -m pytest tests/test_career_footprint_api.py tests/test_career_footprint_frontend.py tests/test_career_footprint_map_assets.py tests/test_career_footprint_memory_gallery_security.py tests/test_career_memory_gallery_api.py tests/test_career_memory_gallery_frontend.py tests/test_career_memory_frontend_render.py tests/test_career_memory_media_frontend.py tests/test_career_gap_p1_11_frontend_data_linkage.py tests/test_career_phase9_data_boundary_audit.py tests/test_career_phase9_pywebview_envelope.py tests/test_career_phase9_macos_closure.py tests/test_career_race_map_frontend.py -q`
- 验证结果：`69 passed`
- 状态：Done
- 下一个任务：无，任务清单全部完成
