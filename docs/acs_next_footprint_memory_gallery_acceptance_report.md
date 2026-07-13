---
title: ACS 足迹与 Memory Gallery 验收报告
version: v0.1.0
status: Completed
type: Acceptance Report
source:
  - docs/acs_next_footprint_memory_gallery_delivery_manual.md
  - docs/acs_next_footprint_memory_gallery_task_list.md
updated: 2026-07-13
---

# ACS 足迹与 Memory Gallery 验收报告

## 1. 验收范围

本轮完成足迹页两个模块：

- 生涯足迹：Activity-backed 行政区域点亮地图，支持中国 / 世界地图模式、hover/focus 摘要、click 详情、代表 Activity 回跳。
- Memory Gallery：Race Event-backed 赛事相册，4:3 相册墙、相册展开、单图大图预览、上一张 / 下一张、ESC 关闭。

## 2. 真实库验收

真实库：

```text
/Users/fanglei/.fitvault/user_profile.db
```

只读调用结果：

```text
get_career_footprint
- map_mode: world
- activity_count: 253
- region_count: 6
- country_count: 2
- china_region_count: 5
- overseas_region_count: 1
- without_region_count: 25
- region_keys sample: CN-BJ, CN-SC, CN-HK, CN-FJ, CN-JS, JP

get_career_memory_gallery
- album_count: 5
- photo_count: 3
- empty_album_count: 2
- cover_count: 3
- album sample: 雅安市 骑行, 常州市 公路骑行比赛, 名山区 骑行, 2023成都半程马拉松, 都江堰半程马拉松
```

结论：

- 当前真实库存在海外足迹，正确触发 `map_mode = world`。
- 中国区域和海外国家可同时点亮。
- 缺地区 Activity 进入 `without_region` 统计。
- Gallery 当前能生成 5 个赛事相册，其中 3 个有封面，2 个为空相册。

## 3. 视觉与交互验收

已完成：

- 暗黑地图骨架：本地区域资源，无 CDN。
- 足迹地图不接入在线地图服务：使用本地静态暗黑地图底图和区域点亮层，不提供缩放操作。
- 中国资源包含台湾 `CN-TW`。
- 世界资源包含当前后端支持的海外国家 key。
- 相册卡片固定 `4:3`。
- 无封面相册回退为赛事标题艺术字封面，不使用假照片。
- 相册展开照片网格保持后端排序。
- 单图预览支持关闭、上一张 / 下一张、ESC、左右键。
- 图片加载失败为局部状态。
- 移动端 CSS 已收敛到单列相册墙、双列照片网格。

未执行：

- Windows 真机验收。
- macOS / Windows 打包产物验收。
- 浏览器截图自动化验收；当前工作区未安装 Playwright 依赖，本轮以静态视觉契约测试替代。

## 4. 安全边界

已验证：

- API 不返回 raw FIT、points、`points_json`、`track_json`、`storage_ref`、`file_path`、本地路径、`file://` 或 SQLite schema。
- 前端 normalizer 不使用 `Object.assign` 或对象展开透传。
- 前端不从标题、城市、日期或 DOM 文本推断地图区域。
- Memory Gallery 不绕过后端读取媒体路径，只使用后端安全预览字段。

## 5. 验证命令

```bash
.venv312/bin/python -m pytest tests/test_career_footprint_memory_gallery_security.py tests/test_career_phase9_data_boundary_audit.py tests/test_career_footprint_frontend.py tests/test_career_memory_gallery_frontend.py tests/test_career_memory_gallery_api.py -q
.venv312/bin/python -m pytest tests/test_career_memory_gallery_frontend.py tests/test_career_memory_frontend_render.py tests/test_career_memory_media_frontend.py -q
.venv312/bin/python -m pytest tests/test_career_memory_gallery_api.py tests/test_career_media_safe_preview_api.py tests/test_career_phase9_pywebview_envelope.py -q
```

## 6. 结论

本轮交付满足交付手册和任务清单定义的核心目标，可作为后续打包、真机截图和产品微调的实现基线。

## 7. 截图反馈修正

2026-07-13 追加修正：

- 将足迹前端从“网格 + 小锚点”改为“暗黑地图底图 + 区域点亮层”，避免看起来没有地图。
- 世界地图模式下，将中国省级足迹聚合为 `CN` 国家级点亮，避免海外足迹触发世界地图后中国区域不亮。
- 未点亮区域不再渲染成可点击对象，避免出现“德国 0 活动”这类误导详情。
- 缺地区 Activity 不再逐条展示，避免出现 `Activity #113` 这类用户不可理解记录；页面只保留缺地区数量汇总。

## 8. 静态足迹地图与空相册封面修正

2026-07-13 追加修正：

- 确认此前实现没有接入第三方地图服务，仅为本地 SVG 示意底图。
- 因足迹功能只需要按省份 / 州 / 行政区域点亮，不需要缩放或道路级地图，已撤销 OSM / 天地图等在线瓦片方案。
- 足迹地图默认使用本地静态暗黑底图，确保无外网、无第三方 Key 时仍可见。
- 不引入 Leaflet/Mapbox 等新外部 JS 库，继续遵守现有前端依赖边界。
- Memory Gallery 空相册封面不再显示“暂无封面”，改为赛事标题艺术字封面。

## 9. 本地行政区 Shape 点亮修正

2026-07-13 追加修正：

- 足迹地图已从“静态底图 + 锚点按钮”升级为“本地 SVG path 行政区 shape 填色”。
- `assets/career_footprint_map_regions.json` 已升级为 path 资源结构，包含 `path`、`label_x`、`label_y`。
- 中国地图 shape 资源覆盖后端中国区域 key，并包含 `CN-TW`。
- 世界地图 shape 资源覆盖当前后端海外国家 key；世界模式下中国省级足迹继续聚合为 `CN`。
- 未点亮区域仅低对比展示，不绑定点击详情；已点亮区域保留 hover / focus 摘要、click 详情和代表 Activity 回跳。
- 当前 shape 不依赖在线地图服务；中国地图已升级为本地真实省级行政区边界 path 资源。

## 10. 真实地图资源与 Banner 风格空封面修正

2026-07-13 追加修正：

- 中国地图使用 `assets/career_footprint_map_regions.json` 内置真实省级行政区边界 path，并包含台湾、香港、澳门。
- 世界地图不接入 OSM、天地图、高德、Mapbox、Leaflet 或在线瓦片；仅使用仓库已随包携带的 `lib/Cesium/Assets/Textures/NaturalEarthII/0/0/0.jpg` 与 `0/1/0.jpg` 作为本地 Natural Earth 底图。
- 足迹地图仍保持静态点亮，不提供缩放、平移、道路级地图或在线地图 Key 配置。
- Memory Gallery 空相册封面 fallback 已对齐 Overview Banner 的标题艺术字风格：中文字体栈、渐变剪裁文字、斜体倾角、强投影与标题倒影。
- 新增/更新测试覆盖本地地图资源、禁止在线地图服务、真实边界 path、Natural Earth 本地底图，以及空相册 banner 风格 fallback。

## 11. ECharts GeoJSON Choropleth 足迹地图修正

2026-07-13 追加修正：

- 足迹地图已从“栅格底图 + 手写 SVG path 叠加”升级为“本地 GeoJSON + ECharts `registerMap` 静态 Choropleth”。
- 新增本地地图资源：
  - `assets/career_footprint_world.geo.json`
  - `assets/career_footprint_china.geo.json`
  - `assets/career_footprint_maps_manifest.json`
  - `assets/career_footprint_maps.js`
- 世界图负责国家 / 地区级点亮；中国省级足迹在世界图聚合为 `CN`。
- 点击世界图中的中国可下钻到中国省级地图；当前仅支持 `CN -> china` 下钻，日本 / 美国等 admin-1 地图资源预留后续任务。
- 默认不显示全部区域标签，仅 hover / emphasis 显示名称，避免“中国本”这类标签重叠。
- 运行时不访问 OSM、天地图、高德、Mapbox、Leaflet、在线瓦片或 CDN 地图资源；新增脚本仅为本地地图数据资产，不是第三方运行库。
- `get_career_footprint` ViewModel、pywebview envelope 与 JS API 契约未变。

## 12. 地图视窗与海外国家覆盖修正

2026-07-13 追加修正：

- 生涯足迹地图容器高度已加大，避免世界图在宽屏下被压缩成过窄横条；移动端也同步提高最小高度。
- ECharts `map` series 显式设置 `layoutCenter` / `layoutSize`，让世界图和中国图主动填充视窗，避免真实边界图在容器内显得过小。
- 中国下钻态新增地图内“返回世界图”按钮，保留工具栏返回入口，避免用户进入中国省级图后找不到返回路径。
- 世界国家资源从 8 个国家扩展到 23 个国家，覆盖既有国家、热门马拉松国家与东南亚热门旅游国家。
- 新增国家包括：意大利、西班牙、荷兰、希腊、加拿大、南非、泰国、越南、马来西亚、印度尼西亚、菲律宾、柬埔寨、老挝、缅甸、文莱等；新加坡继续以小面资源支持。
- 后端国家归一表同步扩展，前端仍只消费后端结构化 `country_code` / `region_key`，不从标题或城市文本推断。

2026-07-13 二次修正：

- 修复首次进入足迹子页时 ECharts 在隐藏页初始化导致地图空白的问题；切换到足迹页后会延迟重绘 / resize。
- 世界图资源改为完整 Natural Earth 110m 国家轮廓，世界图始终展示完整世界底图，仅按国家 key 点亮已有足迹。
- 中国图对 `CN-TW` 增加基础可见边界样式，台湾即使未点亮也保持可辨识。
- 新增日本 `JP -> japan` 下钻，随包本地日本都道府县 GeoJSON 共 47 个区域；后端仅从结构化国家 / 省州 / 城市字段解析 `JP-xx`，前端不做地理推断。
- 针对首次进入生涯页时多接口并发加载导致赛事档案 / 足迹 / 相册偶发失败的问题，赛事档案、足迹与 Memory Gallery API 请求增加一次短延迟自动重试；避免首次 SQLite/schema 竞争失败后 UI 永久停留在错误态。
- 世界图填充比例提升到 `layoutSize: 150%`，减少上下留白，让世界轮廓更贴合地图视窗。
- 世界图中 `TW` 作为 `CN` 的同色镜像区域处理，hover/click 均按“中国”展示与下钻；中国图仍使用 `CN-TW` 表达台湾区域。
- 日本结构化城市别名补充“神户 / 神戸”，真实数据中的神户足迹会解析为 `JP-28` 兵库，并在日本下钻图点亮。
- 根因修复：赛事档案 / 足迹 / 相册等读取接口首次并发加载时会同时执行 `ensure_career_schema()` 写入 schema meta，导致 SQLite `database is locked`。已为 ACS schema ensure 增加进程内互斥锁、默认连接 `busy_timeout` 和默认库 schema-ready 缓存，读接口并发不再互相争抢 schema 写锁。

2026-07-14 追加修正：

- Memory Gallery 相册增加结构化 `footprint` 字段，来源为相册对应 Activity / Race 的结构化地理字段；前端不从相册标题、赛事标题或地点展示文案推断地理位置。
- 点击相册后，上方足迹地图进入“当前相册足迹”聚焦模式，只点亮该相册对应的区域：例如成都 / 雅安 / 都江堰相册聚焦 `CN-SC` 四川，常州相册聚焦 `CN-JS` 江苏。
- 相册聚焦只改变地图点亮范围；活动数、赛事数、首次/最近活动、城市数等区域统计优先复用完整生涯足迹中的真实区域桶，避免把四川等区域错误显示为当前相册的 `1` 次活动 / `1` 场赛事。
- 关闭相册 / 返回相册墙时退出聚焦模式，并恢复当前筛选下完整生涯足迹地图。
- 暂未提供结构化 `footprint.region_key` 的相册不会触发地图聚焦；未来新增北美、欧洲、亚洲主要国家 admin-1 下钻资产时，可复用同一 `footprint` 联动入口。

2026-07-14 美国下钻最小增量：

- 新增 `US -> us` 美国州级下钻，范围仅限美国。
- 新增独立懒加载地图脚本 `assets/career_footprint_us.js`，主地图包 `assets/career_footprint_maps.js` 仍只内置 world / china / japan。
- 后端美国区域解析遵守结构化字段契约：州 / 城市明确时返回 `US-xx` 与 `map_mode = us`，仅国家明确时仍返回 `US` 与 `map_mode = world`。
- 前端世界图点击美国、或点击美国相册时进入美国州图；相册聚焦继续只消费后端 `album.footprint`，不从标题和展示地点推断。
