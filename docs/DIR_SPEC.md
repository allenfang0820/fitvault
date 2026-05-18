# 徒步轨迹AI分析仪 — 项目目录规范 v1.0

> 适用版本：v0.3 及以后所有迭代  
> 最后更新：2025-05-18

---

## 一、根目录结构

```
徒步轨迹AI分析仪/
│
├── src/                        ← 【核心源码】所有业务代码
│   ├── main.py                 ←   应用入口（PyWebView API 绑定）
│   ├── profile_backend.py      ←   用户画像 / 活动数据库
│   ├── track_backend.py        ←   轨迹解析（GPX / FIT / KML）
│   └── mcp/
│       └── get_garmin_stats.py ←   MCP 数据同步脚本
│
├── web/
│   ├── index.html              ←   前端入口（重命名为 index.html）
│   ├── css/
│   │   └── styles.css          ←   样式文件
│   ├── js/
│   │   └── app.js              ←   前端逻辑（从 HTML 中抽离）
│   └── assets/
│       └── icons/              ←   静态资源
│
├── lib/                        ← 【第三方库】（不修改，版本锁定）
│   └── Cesium/                 ←   CesiumJS 地图引擎
│
├── tests/                      ← 【测试代码】
│   ├── test_track_parse.py     ←   轨迹解析单元测试
│   ├── test_profile_db.py      ←   数据库读写测试
│   └── test_fit_sport.py       ←   FIT 运动类型提取测试
│
├── .venv/                      ← 【虚拟环境】（依赖锁定）
│
├── .git/                       ← 【版本控制】
│
├── docs/                       ← 【文档】
│   ├── CHANGELOG.md            ←   变更日志
│   ├── API_SPEC.md             ←   API 规范文档
│   └── DIR_SPEC.md             ←   本规范文档
│
├── build/                      ← 【构建产物】
│   └── HikingTrackAnalyzer/
│
├── HikingTrackAnalyzer.spec    ←   PyInstaller 打包配置
├── requirements.txt            ←   Python 依赖（锁定版本）
├── README.md                   ←   项目说明
└── .gitignore
```

---

## 二、核心规范

### 2.1 新增功能 / 新模块 → 新文件夹

**触发条件**：新增独立功能模块（如新增数据源、新的分析工具、新 UI 面板）

**规则**：
- 在 `src/` 或 `web/` 下创建独立目录
- 命名格式：`功能名_描述`（如 `src/elevation_profile/`、`web/ai_coach_panel/`）
- 每个新文件夹必须包含 `__init__.py`（Python）或 `module.json`（前端）
- 新文件夹内按 `core/`（核心逻辑）、`ui/`（界面）、`tests/`（测试）子结构组织

**旧代码归档**：
- 废弃模块移至 `archive/` 目录，保持原结构不变
- 在 `docs/ARCHIVED_MODULES.md` 中记录归档原因和归档日期
- 归档后删除源码中的引用，确保 `import` 无歧义

---

### 2.2 功能迭代 / Bug修复 → 沿用旧文件夹

**触发条件**：对现有功能进行修改、增强、修复

**规则**：

| 操作类型 | 处理方式 |
|---------|---------|
| Bug 修复 | 直接修改原文件，同时在文件头注释中追加 `// FIXED: #issueId 描述` 或 `# FIXME: #issueId` |
| 功能增强 | 在原文件末尾追加新函数/方法，函数命名带 `_v2` 后缀（如 `parse_track_v2`） |
| 重构 | 将旧函数重命名为 `xxx_old()` 后保留，新实现覆盖原函数名 |
| 新增 API | 在 `src/` 目录下直接追加，不新建文件 |

**分支管理**：
- `main` 分支：稳定版本，所有功能通过 PR 合并
- `dev` 分支：开发中版本，可直接推送
- 功能分支命名：`feature/功能名` 或 `fix/问题描述`

**旧冗余代码清理机制**：
- 每次 `git commit` 前检查：是否有 `_old()` / `_v1()` / `deprecated` 函数
- 超过 **3 个废弃函数** 时，触发清理检查点
- 清理时保留最近 2 个版本的历史（通过 git 历史回溯）

---

### 2.3 目录规范检查节点

| 场景 | 检查人 | 检查时机 | 检查内容 |
|------|--------|---------|---------|
| 新增文件 | 开发者自检 | `git add` 前 | 文件是否放入正确目录？是否有 `__init__.py`？命名是否符合规范？ |
| PR 合并 | 代码评审者 | PR 创建时 | 新文件是否导致目录混乱？是否正确区分 `src/`/`web/`/`lib/`？ |
| 版本发布 | 维护者 | `git tag` 前 | `archive/` 中是否有可清理内容？`.venv/` 是否同步更新？ |
| 大版本迭代（v1.0→v2.0） | 架构师 | 规划阶段 | 是否需要重构目录结构？是否废弃模块需要归档？ |

---

## 三、文件命名规范

### 3.1 Python 文件

```
模块名.py              ← 例：track_parser.py
模块名_子功能.py       ← 例：track_parser_gpx.py
test_模块名.py         ← 例：test_track_parser.py
conftest.py            ← pytest 固定命名
```

### 3.2 前端文件

```
index.html             ← 入口文件（不再使用含日期的文件名）
模块名.js              ← 例：cesium_viewer.js
组件名.css             ← 例：sidebar_tabs.css
```

### 3.3 数据文件

```
activities_{日期}.db   ← 活动数据库快照（禁止在源码中硬编码路径）
profile_backup_{日期}.json ← 用户画像备份
```

---

## 四、依赖路径规范

### 4.1 Python 依赖

- 所有第三方库必须写入 `requirements.txt`（格式：`包名==版本号`）
- 禁止在代码中使用 `sys.path.insert` 引用本地模块，所有模块通过包导入
- 相对导入：`from . import module`，禁止 `from src import module`

### 4.2 前端依赖

- 所有外部 CDN 资源必须在 `web/libs.json` 中记录（名称/版本/URL/校验和）
- 大型库（如 Cesium）存放在 `lib/` 目录，从本地加载
- 不允许直接引用未记录的 CDN 资源

### 4.3 路径引用

```python
# ✅ 正确：使用 Path 对象和相对路径
from pathlib import Path
BASE_DIR = Path(__file__).parent.parent

# ✅ 正确：数据目录通过函数获取
TRACKS_DIR = Path.home() / ".hiking_track_ai" / "local_tracks"

# ❌ 错误：硬编码绝对路径
DATA_DIR = "/Users/fanglei/Desktop/AI track/data"
```

---

## 五、版本兼容要求

| 类型 | 要求 |
|------|------|
| Python 版本 | >= 3.11（类型注解 `str | None` 等语法需要） |
| 前端浏览器 | Chrome/Firefox/Safari 最近 2 个版本 |
| 数据库 | SQLite 3（内置，无需安装） |
| PyWebView | 锁定在 `requirements.txt` 中指定版本 |

---

## 六、违规处理

- 新增文件放入错误目录 → **PR 被拒绝**，要求重分类
- 未更新 `requirements.txt` 引入新依赖 → **PR 被拒绝**
- 硬编码路径（出现 `/Desktop/AI track/` 或类似） → **PR 被拒绝**
- 超过 3 个废弃函数未清理 → **触发代码评审警告**

---

## 七、变更记录

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2025-05-18 | v1.0 | 初始规范制定，完成 v0.3 重构后的目录规范化 |