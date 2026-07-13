---
title: ACS 足迹与 Memory Gallery 交付手册
aliases:
  - 运动生涯足迹交付手册
  - Footprint and Memory Gallery Delivery Manual
version: v0.1.0
status: Requirement Freeze
type: Delivery Manual
scope: ACS 足迹页、生涯足迹地图、赛事相册 Memory Gallery
updated: 2026-07-12
---

# ACS 足迹与 Memory Gallery 交付手册

## 1. 目标定义

本手册定义 ACS 足迹页接下来系列任务的产品目标、数据契约、交互规则和验收边界。

足迹页包含两个大的功能模块：

1. 生涯足迹
2. Memory Gallery

当前代码中的 `Race Map / 赛事足迹` 和轻量 `Memory Gallery` 只能视为历史基础，不等同于本轮目标形态。

## 2. 总体架构契约

### 2.1 Activity 是唯一事实源

所有足迹与相册展示必须能回溯到 Activity。

允许的数据来源：

- Activity 地理字段
- Activity 关联的 Race Event
- Activity Detail 中已上传、已排序、已受控存储的赛事照片
- 后端生成的安全 ViewModel

禁止：

- 前端根据标题、城市、日期或 DOM 文本推断地理区域
- 前端读取 raw FIT、`points_json`、`track_json` 或本地文件路径
- AI 生成或改写地理事实、赛事事实、照片排序事实
- Memory Gallery 另建一套与 Activity Detail 脱离的相册事实源

### 2.2 后端负责事实归一，前端只负责渲染

后端必须输出面向 UI 的 ViewModel：

- 生涯足迹地图所需的地图模式、区域列表、统计摘要和状态
- Memory Gallery 所需的赛事相册列表、封面、安全图片引用和照片列表

前端只消费 ViewModel，不做事实计算。

## 3. 模块一：生涯足迹

### 3.1 产品目标

生涯足迹用于回答：

```text
我的运动生涯已经点亮过哪些地区？
```

它不是单点经纬度散点图，也不是路线回放图，而是一张暗黑风格的区域点亮地图。

### 3.2 地图展示规则

地图按行政区域点亮：

- 中国内地按省级区域点亮
- 台湾区域必须包含在中国地区地图中
- 海外按国家、州、省或等价一级行政区点亮，具体粒度由可用地理数据决定

地图模式选择：

- 如果用户所有足迹都在中国地区，展示中国地区地图
- 如果用户存在海外足迹，展示世界地图
- 地图模式由后端根据地理事实判断并返回，前端不得自行判断

视觉风格：

- 暗黑地图底色
- 已点亮区域使用高对比但克制的亮色
- 未点亮区域低对比显示
- 地图上可展示区域名称或悬浮提示，但不能遮挡主体
- 空状态需要稳定，不展示假的点亮区域

### 3.3 数据粒度

生涯足迹应覆盖所有有可靠地理信息的运动 Activity，而不只限赛事。

后端需要把 Activity 地理字段归一为区域：

```text
Activity
  -> country / region_country
  -> province_or_state / region_province / region_state
  -> city / region_city
  -> footprint_region_key
```

最小可用闭环：

- 有中国城市但无省份时，后端可以通过受控映射补齐省份
- 有海外国家但无州/省时，可先点亮国家级区域
- 没有可靠地理信息的 Activity 进入 `without_region`，不参与地图点亮

### 3.4 建议 API

新增或重构为：

```text
get_career_footprint(filters?)
```

返回建议：

```json
{
  "map_mode": "china",
  "regions": [
    {
      "region_key": "CN-SC",
      "name": "四川",
      "country": "中国",
      "level": "province",
      "activity_count": 12,
      "race_count": 2,
      "first_activity_date": "2023-03-25",
      "latest_activity_date": "2026-07-09",
      "representative_activity_id": "358",
      "detail_link": {
        "activity_id": "358",
        "source": "career"
      }
    }
  ],
  "summary": {
    "activity_count": 251,
    "region_count": 8,
    "country_count": 1,
    "china_region_count": 8,
    "overseas_region_count": 0,
    "without_region_count": 9
  },
  "status": {
    "data_ready": true,
    "message": "生涯足迹已生成"
  }
}
```

补充约束：

- 顶层 `map_mode` 仍只表达首屏渲染中国图或世界图：`china` / `world`。
- `regions[].map_mode` 可表达具体区域下钻模式，例如 `china`、`japan`、`us`。
- 美国足迹只有在结构化国家字段为美国且州 / 城市字段可明确解析时，才返回 `US-xx` 与 `map_mode = us`；仅有国家字段时保持 `US` 国家级世界图点亮。

### 3.5 验收标准

- 只有中国足迹时，只显示中国地区地图，并包含台湾区域
- 存在海外足迹时，显示世界地图
- 地图按省份 / 州 / 行政区域点亮，而不是散点图
- 普通 Activity 可进入生涯足迹，不依赖赛事身份
- 没有可靠地理字段的 Activity 不被强行补坐标或点亮
- API 不返回 raw FIT、完整路线 points、本地路径、SQLite schema
- 前端不从标题、城市文案或日期推断区域

## 4. 模块二：Memory Gallery

### 4.1 产品目标

Memory Gallery 用赛事相册承载运动记忆。

它的主路径是：

```text
赛事相册墙 -> 单场赛事相册 -> 单张照片大图
```

### 4.2 相册墙

Memory Gallery 首屏按赛事为单位展示相册卡片。

卡片规则：

- 每张卡片代表一场赛事
- 卡片比例为 4:3
- 以小卡片网格方式排布
- 封面默认使用该赛事照片排序中的第一张
- 第一张图逻辑必须与 Overview Banner 保持一致
- 卡片显示赛事标题、时间、地点
- 卡片点击后展开该赛事相册

赛事卡片建议字段：

```json
{
  "race_id": "race:358",
  "activity_id": "358",
  "title": "雅安市 骑行",
  "event_date": "2026-07-09",
  "location_text": "雅安市/中国",
  "cover": {
    "media_id": "media:1",
    "preview": "data:image/..."
  },
  "photo_count": 5,
  "detail_link": {
    "activity_id": "358",
    "source": "career"
  }
}
```

### 4.3 单场赛事相册

点击赛事相册卡片后，展开该赛事已上传的所有照片。

展开方式可以是：

- 页面内展开面板
- 弹层 modal
- 抽屉式详情面板

但必须满足：

- 展示该赛事所有已启用照片
- 保持照片排序
- 第一张照片仍是封面和 Banner 默认图
- 显示赛事标题、时间、地点
- 可返回相册墙
- 不暴露本地文件路径或 `storage_ref`

### 4.4 单张照片大图

用户点击相册中的单张照片后，进一步展开大图。

大图预览要求：

- 使用安全预览或应用受控媒体读取结果
- 支持关闭
- 建议支持上一张 / 下一张
- 展示当前照片序号
- 不在前端直接拼接本地路径
- 图片加载失败时显示局部错误态，不影响相册关闭和切换

### 4.5 数据来源

Memory Gallery 必须复用 Activity Detail 已有赛事照片数据。

当前既有能力：

- 赛事 Activity Detail 可上传照片
- 照片最多 5 张
- 支持排序
- 排序第一张作为 Overview Banner
- 删除采用软删除
- 后端生成安全预览

本轮 Memory Gallery 不应重新建立独立上传入口作为首要目标。相册墙应先消费这些既有照片事实。

### 4.6 建议 API

可以新增或扩展：

```text
get_career_memory_gallery(filters?)
```

返回建议：

```json
{
  "albums": [
    {
      "race_id": "race:358",
      "activity_id": "358",
      "title": "雅安市 骑行",
      "event_date": "2026-07-09",
      "location_text": "雅安市/中国",
      "cover_media_id": "media:1",
      "cover_preview": "data:image/...",
      "photo_count": 5,
      "photos": [
        {
          "media_id": "media:1",
          "sort_order": 0,
          "preview": "data:image/...",
          "width": 1600,
          "height": 1200
        }
      ],
      "detail_link": {
        "activity_id": "358",
        "source": "career"
      }
    }
  ],
  "summary": {
    "album_count": 3,
    "photo_count": 12,
    "empty_album_count": 1
  },
  "status": {
    "data_ready": true,
    "message": "Memory Gallery 已生成"
  }
}
```

## 5. 前端实现要求

### 5.1 页面结构

足迹页建议结构：

```text
Footprint Page
├── 生涯足迹
│   ├── 暗黑地图
│   ├── 点亮区域摘要
│   └── 无地理信息活动提示
└── Memory Gallery
    ├── 赛事相册墙
    ├── 单场赛事相册展开
    └── 单张照片大图预览
```

### 5.2 视觉要求

生涯足迹：

- 暗黑底图
- 区域点亮清晰
- 不使用营销式大段说明
- 不使用无法承载真实地图语义的装饰图

Memory Gallery：

- 4:3 卡片
- 网格排布
- 卡片文字不能压住主体照片
- 标题、时间、地点保持可读
- 空相册状态克制，不用假照片

### 5.3 交互要求

- 点击地图区域，可展示该区域摘要
- 点击区域代表活动，可回跳 Activity Detail
- 点击相册卡片，展开赛事相册
- 点击照片，打开大图
- 大图支持关闭，建议支持上一张 / 下一张
- 所有可点击入口必须保留键盘可达性

## 6. 非目标

本轮不要求：

- 路线回放
- 完整轨迹热力图
- 复杂相册云同步
- 媒体文件物理删除
- AI 自动生成相册文案
- 前端自行地理编码
- 接入外部赛事数据库

## 7. 开发拆解建议

### Task A：足迹数据契约冻结

- 明确 `get_career_footprint` ViewModel
- 明确中国 / 世界地图模式判断规则
- 明确省份 / 州 / 国家归一字段
- 增加后端单测覆盖中国-only、海外、有缺失地理信息三类样例

### Task B：暗黑地图前端骨架

- 接入中国地图与世界地图静态区域渲染
- 支持后端 `map_mode`
- 支持区域点亮、hover、点击摘要
- 不接入路线 points

### Task C：Memory Gallery 相册 ViewModel

- 按 Race Event 聚合相册
- 复用 Activity Detail 已有照片排序
- 第一张照片作为 `cover`
- 返回赛事标题、时间、地点、安全预览和照片列表

### Task D：Memory Gallery 前端

- 4:3 赛事相册卡片墙
- 点击相册展开照片网格
- 点击照片打开大图
- 支持关闭和上一张 / 下一张

### Task E：端到端验收

- 用真实库验证中国-only 地图
- 构造海外样例验证世界地图
- 验证无坐标 / 无地区 Activity 不被误点亮
- 验证赛事照片排序第一张同步影响 Banner 与 Gallery 封面
- 验证安全边界不泄露本地路径

## 8. 验收红线

- 生涯足迹不能退化成赛事经纬度散点图
- 中国-only 不能显示世界地图
- 中国地图必须包含台湾区域
- 海外足迹必须触发世界地图
- Memory Gallery 必须按赛事组织相册
- 相册封面必须复用第一张图逻辑
- 点击相册必须能看到该相册所有照片
- 点击单张照片必须能展开大图
- 前端不得推断事实或读取本地路径
