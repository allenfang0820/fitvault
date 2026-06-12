# 视觉设计 Token 契约 v1

> **状态**: 已生效
> **版本**: v1.0
> **生效日期**: 2026-06-09
> **适用范围**: 全局 UI (`track.html` 主体 + 后续模块)
> **基线调研**: `docs/p0_remove_sidebar_placeholder_cards_prompt.md` 完成后即发现的字号散乱问题(track.html 共 53 个独立 rem 值、11 处 px 硬编码、JS 内嵌 ECharts 字号独立)
> **v1.0 落地决策**: 全局根字号 **16px → 19px**(整体放大 18.75%,经 2026-06-09 用户验证 OK,桌面端舒适阅读)

---

## 一句话契约

**所有 UI 元素的字号 / 行高 / 字重,必须从本文档定义的 `--fs-*` / `--lh-*` / `--fw-*` CSS 变量中选取,禁止硬编码数值;严禁在生产代码中引入未在本文档登记的字号档位。**

---

## 一、契约背景

### 1.1 现状盘点(调研基线)

| 维度 | 现状 | 问题 |
|---|---|---|
| CSS 变量 | `:root` 仅 5 个颜色变量,**0 个字号变量** | 字号完全硬编码,无法统一调整 |
| rem 值种类 | 53 个独立 rem 值(0.52 / 0.55 / 0.58 / 0.6 / 0.62 / 0.64 / 0.65 / 0.66 / 0.67 / 0.68 / 0.7 / 0.72 / 0.74 / 0.75 / 0.76 / 0.78 / 0.8 / 0.82 / 0.84 / 0.85 / 0.86 / 0.88 / 0.9 / 0.94 / 0.95 / 1.0 / 1.05 / 1.06 / 1.1 / 1.12 / 1.15 / 1.2 / 1.3 / 1.4 / 1.5 / 1.6 / 2.4 / 3.0) | 离散度过高,同一语义多种字号并存 |
| px 硬编码 | 11 处(11/12/13/14/16/20/28 px) | 无法随根字号缩放 |
| JS ECharts 字号 | `fontSize: 10 / 11 / 14 / 16` | 与 CSS 不对应,跨端不一致 |
| 设计文档 | `docs/v9_2_overview_design.md` 等偶有字号 demo,无 token 规范 | 没有可追溯的设计依据 |

### 1.2 解决目标

- 用 8 级字号 token + 3 级行高 + 4 级字重覆盖全部 UI 场景
- 同一语义层只允许一种 token,禁止"同一语义多种字号"
- 全部走 CSS 变量,支持暗色模式 / 高 DPI 屏幕 / 用户字号缩放
- ECharts JS 内嵌字号也要走同一套 token

---

## 二、字号 Token(`--fs-*`)

### 2.1 完整定义

```css
:root {
  /* === 字号(8 级 +1 基准)== */
  --fs-3xs: 0.55rem;   /* 10.5px  极小 / 角标 */
  --fs-2xs: 0.62rem;   /* 11.8px  迷你元数据 */
  --fs-xs:  0.68rem;   /* 12.9px 辅助文本 / 标签 */
  --fs-sm:  0.72rem;   /* 13.7px 正文(最常用) */
  --fs-md:  0.78rem;   /* 14.8px 卡片标题 */
  --fs-lg:  0.85rem;   /* 16.2px 重点数值 / 按钮 */
  --fs-xl:  0.95rem;   /* 18.1px 强调标题 */
  --fs-2xl: 1.1rem;    /* 20.9px 页内标题 */
  --fs-3xl: 1.5rem;    /* 28.5px 大展示值 */
  --fs-4xl: 2.4rem;    /* 45.6px 超大展示值 */

  /* 默认正文基准(用于 body / html) */
  font-size: 19px;   /* v1.0:16 → 19px,整体放大 18.75% */
}
```

> **v1.0 落地根字号为 19px**(原 16px,经 2026-06-09 用户视觉评估后调整为 19px,整体放大 18.75%)。所有 px 等价值已基于 19px 重算。**禁止再次修改根字号**;后续如需全局放大 /缩小,应通过 token rem 值调整比例,而不是动根字号。

### 2.2 语义映射表(强制,基于根字号 19px)

| Token | px 等价 | 用途 | 允许使用的元素 | 严禁使用 |
|---|---|---|---|---|
| `--fs-3xs` | 10.5 | 极小角标 / 箭头 | `.tab-arrow`、分页 `…` 省略号、徽标角标 | 任何正文 / 标签 |
| `--fs-2xs` | 11.8 | 迷你元数据 | 跳转按钮、迷你分页 | 任何正文 |
| `--fs-xs` | 12.9 | 辅助文本 | 表单元数据、标签、time-stamp | 卡片正文 |
| `--fs-sm` | 13.7 | **正文(默认)** | 卡片正文、列表项、说明文字 | 标题 |
| `--fs-md` | 14.8 | **卡片标题** | `.sidebar-card .head`、section 内标题 | 数值 |
| `--fs-lg` | 16.2 | **重点数值 / 按钮** | 按钮文字、mini-stat 数值 | 大标题 |
| `--fs-xl` | 18.1 | 强调副标题 | 弹层标题、副标题 | 正文 |
| `--fs-2xl` | 20.9 | **页内主标题** | Modal 标题、Section H2 | 卡片正文 |
| `--fs-3xl` | 28.5 | **大展示值** | `.metric-card .val`、Hero 数值 | 副标题 |
| `--fs-4xl` | 45.6 | **超大展示** | 启动屏 / 异常态 / 空态标题 | 普通 UI |

### 2.3 映射规则(决策树)

```text
是角标 / 极小元数据吗?
 ├──是 → --fs-3xs 或 --fs-2xs
 └──否 → 是辅助 / 元数据吗?
 ├──是 → --fs-xs
 └──否 → 是卡片正文 / 普通段落吗?
 ├──是 → --fs-sm
 └──否 → 是卡片标题 / section 内 H3 吗?
 ├──是 → --fs-md
 └──否 → 是按钮文字 / 重点数值吗?
 ├──是 → --fs-lg
 └──否 → 是弹层标题 / 副标题吗?
 ├──是 → --fs-xl
 └──否 → 是 Modal 标题 / 页内 H2 吗?
 ├──是 → --fs-2xl
 └──否 → 是 metric 大数值(Hero)?
 ├──是 → --fs-3xl
 └──否 → 是异常态 / 启动屏标题?
 └──是 → --fs-4xl
```

**禁止跳级**:从 `--fs-xs` 直接跳 `--fs-xl` 是反模式,会导致视觉跳跃过大。

---

## 三、行高 Token(`--lh-*`)

### 3.1 完整定义

```css
:root {
  --lh-tight:  1.2;   /* 紧凑:大数值、徽标、单行展示 */
  --lh-normal: 1.5;   /* 常规:正文、卡片正文 */
  --lh-loose:  1.75;  /* 宽松:长段落、说明文字 */
}
```

### 3.2 语义映射表

| Token | 适用元素 | 严禁用于 |
|---|---|---|
| `--lh-tight` | 大数值、单行标签、按钮文字 | 多行正文 |
| `--lh-normal` | 卡片正文、列表项、说明文字 | 单行密集元素 |
| `--lh-loose` | 长段落、Modal 说明、空态描述 | 标签、单行元素 |

---

## 四、字重 Token(`--fw-*`)

### 4.1 完整定义

```css
:root {
  --fw-regular:  400;  /* 常规:辅助文本 */
  --fw-medium:   500;  /* 中等:次要标签 */
  --fw-semibold: 600;  /* 半粗:卡片标题、按钮 */
  --fw-bold:     700;  /* 粗:数值、强调 */
}
```

### 4.2 语义映射表

| Token | 适用场景 |
|---|---|
| `--fw-regular` | 辅助文本 / meta / 长段落正文 |
| `--fw-medium` | 次要标签、time-stamp |
| `--fw-semibold` | 卡片标题、section 内 H3、按钮 |
| `--fw-bold` | 重点数值、状态徽标、强调 |

> 禁止使用 800 / 900(项目无对应语义);如有视觉需求,先用 `--fw-bold`,新增 token 须走本文 §八 升级流程。

---

## 五、字族 Token(`--ff-*`)

### 5.1 完整定义

```css
:root {
  --ff-base: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  --ff-mono: ui-monospace, SFMono-Regular, "SF Mono", Consolas, "Liberation Mono", Menlo, monospace;
}

body {
  font-family: var(--ff-base);
}

.metric-value,
.tabular-nums {
  font-variant-numeric: tabular-nums;
  font-family: var(--ff-mono);
}
```

### 5.2 用途说明

- `--ff-base`:全局默认字族
- `--ff-mono`:等宽字族,用于 metric 数值 / 时长 / 距离等需要对齐的数字

---

## 六、变量使用规范

### 6.1 必须使用 CSS 变量

```css
/* ✅ 正确 */
.card-title { font-size: var(--fs-md); font-weight: var(--fw-semibold); }
.metric-val { font-size: var(--fs-3xl); font-weight: var(--fw-bold); line-height: var(--lh-tight); }

/* ❌ 错误 */
.card-title { font-size: 0.78rem; font-weight: 600; }
.metric-val { font-size: 1.5rem; font-weight: 700; line-height: 1.2; }
```

### 6.2 严禁场景

- ❌ 任何 `font-size: 0.78rem`(直接写 rem 值)
- ❌ 任何 `font-size: 12px`(直接写 px 值)
- ❌ 任何未登记的字号档位(如 `--fs-md2`、`--fs-2md` 等自行定义)
- ❌ 在 CSS 中使用 `font-size: large / medium / small / larger / smaller`
- ❌ 在 `<style>` 中使用 `font-size: inherit` 作为默认(应显式选择 token)
- ❌ JS 内嵌 `fontSize: 16`(应通过 `getComputedStyle` 读 CSS 变量)

### 6.3 ECharts / 第三方 JS 库

ECharts 等 JS 库不接受 CSS 变量直接读取,需在初始化时读取:

```javascript
function getFsTokenPx(tokenName) {
  const probe = document.createElement('span');
  probe.style.fontSize = `var(${tokenName})`;
  document.body.appendChild(probe);
  const px = getComputedStyle(probe).fontSize;
  probe.remove();
  return parseFloat(px);
}

const echartsOption = {
  title: {
    textStyle: {
      fontSize: getFsTokenPx('--fs-md'),  // 12.5px
    },
  },
};
```

> 或者在每个组件初始化时显式传入已计算好的 px 值(从 CSS 变量查表)。

---

## 七、迁移路径

### 7.1 当前代码 vs Token 映射表(供后续替换参考)

| 当前 rem 值 | 推荐 token | 备注 |
|---|---|---|
| 0.55 / 0.58 / 0.6 | `--fs-3xs` 或 `--fs-2xs` | 极小 |
| 0.62 / 0.64 / 0.65 / 0.66 / 0.67 / 0.68 | `--fs-xs` | 辅助文本 |
| 0.7 / 0.72 / 0.74 / 0.75 / 0.76 | `--fs-sm` | 正文 |
| 0.78 / 0.8 / 0.82 / 0.84 | `--fs-md` | 卡片标题 |
| 0.85 / 0.86 / 0.88 | `--fs-lg` | 数值 / 按钮 |
| 0.9 / 0.94 / 0.95 / 1.0 | `--fs-xl` | 强调 |
| 1.05 / 1.06 / 1.1 / 1.12 / 1.15 | `--fs-2xl` | 页内标题 |
| 1.2 / 1.3 / 1.4 | `--fs-2xl` 或 `--fs-3xl` | 视场景 |
| 1.5 / 1.6 | `--fs-3xl` | 大展示值 |
| 2.4 / 3.0 | `--fs-4xl` | 超大展示 |

### 7.2 实施阶段(建议渐进,不在本契约强制)

| 阶段 | 内容 | 风险 |
|---|---|---|
| **P1 引入变量** | 在 `:root` 加入全部 `--fs-*` / `--lh-*` / `--fw-*` / `--ff-*` | 0 风险 |
| **P2 新代码生效** | 所有新写的 CSS / JS 必须使用 token | 低 |
| **P3 渐进替换** | 按模块(颜色 > 字号 > 行高 > 字重)逐个替换 | 中,需逐模块回归 |
| **P4 全量替换 + CI 守卫** | 替换完毕,加 grep / lint 规则禁止新硬编码 | 中,需 CI 配置 |

---

## 八、契约变更规则

### 8.1 新增 token 流程

如需新增字号档位(如 `--fs-5xl` 用于演示场景):

1. 写 RFC:`docs/rfcs/token_addition_vN.md`,说明用途 / 频次 / 必要性
2. 评审通过后,修改本文 §二 加入新 token
3. 同时更新 §2.2 语义映射表
4. 同时更新 §7.1 当前代码映射表
5. 通知所有前端 owner

### 8.2 弃用 token 流程

如需弃用某 token(如 `--fs-3xs` 实际未使用):

1. 在本文档 §二 标记为 `[DEPRECATED]`,注明弃用日期
2. 保留 1 个版本周期的兼容性
3. CI / lint 规则对弃用 token 发警告

### 8.3 版本号

- 本文档遵守 [语义化版本](https://semver.org/lang/zh-CN/) 原则
- 不兼容变更(删 token / 改 token 值)→ MAJOR 版本
- 新增 token / 新增映射 → MINOR 版本
- 文档纠错 / 措辞调整 → PATCH 版本

---

## 九、CI / 测试守卫(建议 P4 加入)

```bash
# 1. 禁止生产 CSS 出现硬编码 rem
grep -nE "font-size:\s*[0-9.]+rem" track.html
# 预期:0 命中(P4 完成后)

# 2. 禁止生产 CSS 出现硬编码 px(允许 1px border 等非字号场景)
grep -nE "font-size:\s*[0-9]+px" track.html
# 预期:0 命中

# 3. 禁止 JS ECharts 内嵌数字字号
grep -nE "fontSize:\s*[0-9]+" track.html
# 预期:0 命中(允许字符串 'var(--fs-*)')

# 4. token 必须全部定义
grep -E "^\s+--fs-" track.html | wc -l
# 预期:≥ 10(8 级 +1 基准 + 1 极端值)
```

---

## 十、契约附录

### 10.1 完整的 `:root` 定义模板

```css
:root {
  /* === 颜色 === */
  --primary: #2ecc71;
  --primary-hover: #27ae60;
  --bg: #0f172a;
  --panel: rgba(15, 23, 42, 0.85);
  --text: #f8fafc;

  /* === 字号(8 级 +1 基准,基于根字号 19px)== */
   --fs-3xs: 0.55rem;   /* 10.5px  极小 / 角标 */
   --fs-2xs: 0.62rem;   /* 11.8px 迷你元数据 */
   --fs-xs:  0.68rem;   /* 12.9px 辅助文本 */
   --fs-sm:  0.72rem;   /* 13.7px 正文 */
   --fs-md:  0.78rem;   /* 14.8px 卡片标题 */
   --fs-lg:  0.85rem;   /* 16.2px 数值 / 按钮 */
   --fs-xl:  0.95rem;   /* 18.1px 强调 */
   --fs-2xl: 1.1rem;    /* 20.9px 页内标题 */
   --fs-3xl: 1.5rem;    /* 28.5px 大展示值 */
   --fs-4xl: 2.4rem;    /* 45.6px 超大展示 */

  /* === 行高 === */
  --lh-tight:  1.2;
  --lh-normal: 1.5;
  --lh-loose:  1.75;

  /* === 字重 === */
  --fw-regular:  400;
  --fw-medium:   500;
  --fw-semibold: 600;
  --fw-bold:     700;

  /* === 字族 === */
  --ff-base: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
             "Helvetica Neue", Arial, "PingFang SC", "Hiragino Sans GB",
             "Microsoft YaHei", sans-serif;
  --ff-mono: ui-monospace, SFMono-Regular, "SF Mono", Consolas,
             "Liberation Mono", Menlo, monospace;

   /* === 根字号基准(v1.0:19px,禁止修改)== */
   font-size: 19px;
}

body {
  font-family: var(--ff-base);
  font-size: var(--fs-sm);
  line-height: var(--lh-normal);
}
```

### 10.2 变更日志

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-06-09 | 初版:8 级字号 + 3 级行高 + 4 级字重 + 2 级字族 |
| v1.0 | 2026-06-09 | **落地决策**:全局根字号 `16px → 18px`,整体放大 12.5%(用户视觉评估 OK) |

---

> **结束**: 本契约从 v1.0 起强制生效。所有新增 UI 模块必须遵守,既有代码通过 P1-P4 渐进迁移。任何 token 调整必须走 §八 变更流程。