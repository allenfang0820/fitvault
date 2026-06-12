# P0 活动详情侧栏占位卡清理提示词

> 任务类型：P0 死代码清理与 UI 减负
> 适用范围：活动详情 Modal 「概览」Tab 侧栏 4 张卡 → 3 张卡
> 核心目标：移除「身体状态」「活动摘要」两张纯占位卡,固化占位契约边界,补静态回归测试
> 前置背景：调研确认这两张卡从未承载真实数据(空态卡 + 文案指向复盘 Tab AI 洞察),删除不影响既有功能

---

## 零、架构契约核对

执行本任务前必须阅读并遵守：

- `docs/risk_warning_feature_design_v1.md`(轨迹报告相关契约参考)
- 全局架构契约 `fit-arch-contrac` §五 UI 风格 / §六 shadow_diff 隔离
- 现有实现位置：`track.html` 第 [L7234-L7295](file:///Users/fanglei/应用开发/AI%20track/track.html#L7234-L7295) 行附近

本任务必须遵守以下契约：

- 占位卡函数 `_buildPlaceholderSidebarCard(title, icon, msg)` 必须保留(训练收益 / 环境挑战空态降级仍要复用)。
- 不删除任何真实数据卡(天气 / 训练收益 / 环境挑战)。
- 不修改 `_buildTrainingBenefitCard` / `_buildEnvironmentChallengeCard` / `_buildWeatherCard` 业务逻辑。
- 不修改复盘 Tab、风险预警按钮、AI 洞察调用链路。
- 不修改 `_ai_snapshot`、不写 DB、不引入新 CSS 类。
- 删除后必须保证视觉上侧栏剩 3 张卡(天气 / 训练收益 / 环境挑战),无白板 / 无空白。

---

## 一、任务背景

当前活动详情 Modal「概览」Tab 右侧栏由 `renderActivityDetailSidebar` 渲染 4 张卡:

| 卡 | 函数 | 数据源 | 状态 |
|---|---|---|---|
| 🌦️ 历史天气 | `_buildWeatherCard` | `record.weather_context` | ✅ 实卡 |
| 🔥 训练收益 | `_buildTrainingBenefitCard` | `record.detail.training_effect` | ✅ 实卡(V9.4) |
| ⛰️ 环境挑战 | `_buildEnvironmentChallengeCard` | `record.detail.environment_challenge` | ✅ 实卡(V_ENV.1.7) |
| ❤️ 身体状态 | `_buildPlaceholderSidebarCard` | — | ❌ **纯占位** |
| ✨ 活动摘要 | `_buildPlaceholderSidebarCard` | — | ❌ **纯占位** |

**证据链**(为什么是占位):

1. **函数名自带占位语义**:[track.html L7290](file:///Users/fanglei/应用开发/AI%20track/track.html#L7290) `function _buildPlaceholderSidebarCard(title, icon, msg)`,前缀 `_buildPlaceholder...` 明确标记。
2. **返回 HTML 用 `.empty-msg` 类**:[track.html L7293](file:///Users/fanglei/应用开发/AI%20track/track.html#L7293) `'<div class="empty-msg">⏳ ' + msg + '。</div>'`,沙漏 emoji 表示"等待中"。
3. **文案明确指向复盘 Tab**:
   - 身体状态:`'训练压力 / 恢复需求 / 当前状态将在「复盘」Tab 的 AI 洞察中呈现'`
   - 活动摘要:`'AI 活动摘要将在「复盘」Tab 生成'`
4. **代码注释自承"数据源延后解决"**:[track.html L7235](file:///Users/fanglei/应用开发/AI%20track/track.html#L7235) `// 决策:3 张新卡(训练收益/身体状态/活动摘要)数据源延后解决,V9.2.2 M0 显示占位`。

**真实功能已被替代**:

- 「身体状态」的语义 → 已由复盘 Tab 的 `__FATIGUE_REVIEW_INSIGHT__`(疲劳复盘 AI 洞察)承担。
- 「活动摘要」的语义 → 已由轨迹报告「风险预警」改造后的「活动建议」(`__REPORT_ACTIVITY_ADVICE__`,见 `p0_activity_advice_contract_prompt.md`)承担。

**结论**:两张卡是过渡期占位,无信息增量,只是视觉噪音,删除安全。

---

## 二、任务目标

完成侧栏占位卡清理:

1. 删除 `renderActivityDetailSidebar` 中两张占位卡的渲染调用。
2. 同步更新 5 处注释(4 处在 `track.html`,1 处在函数头),保证注释与代码一致。
3. 更新既有测试:`test_environment_challenge_frontend.py` 与 `test_v9_2_overview_m0.py` 中关于 4-card 的断言。
4. 新增 `tests/test_sidebar_placeholder_cleanup.py` 静态回归测试,固化"占位卡不应出现在 sidebar"契约。
5. 验证 `_buildPlaceholderSidebarCard` 函数仍被 训练收益 / 环境挑战 空态降级调用,功能不受影响。

---

## 三、本任务改动范围

### 3.1 必改文件

| 文件 | 改动类型 | 范围 |
|---|---|---|
| `track.html` | 删除 JS | L7258-L7259 共 2 行 |
| `track.html` | 改注释 | L7234 / L7235 / L3431 / L4831 / L4833 / L7225 共 6 处 |
| `tests/test_environment_challenge_frontend.py` | 改断言 | L171-L189 共 5 处断言 |
| `tests/test_v9_2_overview_m0.py` | 改断言 | L407-L430 范围,4-card / placeholder-message 断言 |
| `tests/test_sidebar_placeholder_cleanup.py` | 新建 | 静态断言:占位卡不应出现在 sidebar 渲染调用 |

### 3.2 禁止改动(避免破坏既有功能)

| 文件 / 位置 | 禁止原因 |
|---|---|
| `_buildPlaceholderSidebarCard` 函数定义 [L7288-L7295](file:///Users/fanglei/应用开发/AI%20track/track.html#L7288-L7295) | 训练收益 / 环境挑战 空态降级仍要调用 |
| `_buildTrainingBenefitCard` 中 `_buildPlaceholderSidebarCard('训练收益', ...)` [L7330](file:///Users/fanglei/应用开发/AI%20track/track.html#L7330) | 实卡 + 占位降级混合,占位仍必要 |
| `_buildEnvironmentChallengeCard` 中 `_buildPlaceholderSidebarCard('环境挑战', ...)` [L7419](file:///Users/fanglei/应用开发/AI%20track/track.html#L7419) | 同上 |
| `_buildWeatherCard` / `_buildTrainingBenefitCard` / `_buildEnvironmentChallengeCard` 业务逻辑 | 与本任务无关 |
| `main.py` / `llm_backend.py` | 与本任务无关,占位卡纯前端 |
| 复盘 Tab / 风险预警 / AI 洞察 / 雷达图 / 训练计划 | 与本任务无关 |
| `docs/risk_warning_feature_design_v1.md` | 历史调研文档,不动 |
| `docs/p0_activity_advice_contract_prompt.md` | 平行的另一条改造任务 |

---

## 四、目标契约

### 4.1 删除后侧栏结构契约

```text
renderActivityDetailSidebar(weather, record) 渲染顺序(严格固定):
  1. _buildWeatherCard(weather, esc)              ← 实卡(必现)
  2. _buildTrainingBenefitCard(record)            ← 实卡(空态降级为占位)
  3. _buildEnvironmentChallengeCard(record)       ← 实卡(空态降级为占位)
  // 不再渲染第 4 / 第 5 张
```

### 4.2 函数留存契约

```text
_buildPlaceholderSidebarCard(title, icon, msg):
  - 函数定义保留
  - 训练收益 / 环境挑战 空态降级继续调用
  - 任何其他业务卡片不得调用此函数(除了以上两处已存在的降级路径)
```

### 4.3 测试契约

```text
test_sidebar_placeholder_cleanup.py 必须断言:
  - renderActivityDetailSidebar 函数体内 不应再出现 '身体状态' / '活动摘要' 字串
  - _buildPlaceholderSidebarCard 函数定义 仍存在
  - 训练收益 / 环境挑战 的空态降级调用 仍存在
  - 历史占位 4-card 文案 '4 张卡(环境/训练收益/身体状态/活动摘要)' 在 track.html 不应再出现
```

### 4.4 注释契约

```text
track.html 内的"4 张卡"描述必须改为"3 张卡(天气/训练收益/环境挑战)"或同等准确表述。
涉及 6 处:
  - L7234 函数头注释
  - L7235 "数据源延后解决"注释
  - L3431 CSS 注释
  - L4831 HTML 注释
  - L4833 HTML 注释
  - L7225 HTML 注释
```

---

## 五、实施步骤

### Step 1: 删除占位卡 JS 调用(1 个 commit)

**文件**: `track.html` [L7254-L7260](file:///Users/fanglei/应用开发/AI%20track/track.html#L7254-L7260)

```diff
 html += _buildWeatherCard(weather, esc);
 // V9.4.0:训练收益卡(契约 §7) — 真值从 record.detail.training_effect 读
 html += _buildTrainingBenefitCard(record);
 // V_ENV.1.7:环境挑战卡 — 真值从 record.detail.environment_challenge 读
 html += _buildEnvironmentChallengeCard(record);
-html += _buildPlaceholderSidebarCard('身体状态', '❤️', '训练压力 / 恢复需求 / 当前状态将在「复盘」Tab 的 AI 洞察中呈现');
-html += _buildPlaceholderSidebarCard('活动摘要', '✨', 'AI 活动摘要将在「复盘」Tab 生成');
 sidebar.innerHTML = html;
```

### Step 2: 同步 6 处注释(同 commit)

| 行号 | 原内容 | 新内容 |
|---|---|---|
| L7234 | `// === V9.2.2 §E12 侧栏 4 张卡(环境/训练收益/身体状态/活动摘要) ===` | `// === V9.2.2 §E12 侧栏 3 张卡(天气/训练收益/环境挑战); 训练收益/环境挑战有空态降级占位 ===` |
| L7235 | `// 决策:3 张新卡(训练收益/身体状态/活动摘要)数据源延后解决,V9.2.2 M0 显示占位` | `// 决策:训练收益/环境挑战为空态降级占位;身体状态/活动摘要两张占位卡已于本次清理删除` |
| L3431 | `右列(1fr,flex 1):4 张卡(环境/训练收益/身体状态/活动摘要) 跨全高` | `右列(1fr,flex 1):3 张卡(天气/训练收益/环境挑战) 跨全高` |
| L4831 | `<!-- Row 1+2 Col 3: 4 张卡垂直堆叠(环境/训练收益/身体状态/活动摘要) -->` | `<!-- Row 1+2 Col 3: 3 张卡垂直堆叠(天气/训练收益/环境挑战) -->` |
| L4833 | `<!-- 4 张卡由 renderActivityDetailSidebar 渲染 -->` | `<!-- 3 张卡由 renderActivityDetailSidebar 渲染 -->` |
| L7225 | `// V9.2.2 §E12 侧栏 4 张卡(环境/训练收益/身体状态/活动摘要)` | `// V9.2.2 §E12 侧栏 3 张卡(天气/训练收益/环境挑战)` |

### Step 3: 更新既有测试(独立 commit)

**文件 1**: `tests/test_environment_challenge_frontend.py` [L171-L189](file:///Users/fanglei/应用开发/AI%20track/tests/test_environment_challenge_frontend.py#L171-L189)

- 删除 `idx_body_state` / `idx_body` / `idx_sum` 3 个变量定义
- 删除 5 处 `assertLess` 断言(原本断言 EC < body < sum)
- 保留 `idx_weather < idx_te < idx_ec` 顺序断言

**文件 2**: `tests/test_v9_2_overview_m0.py` [L407-L430](file:///Users/fanglei/应用开发/AI%20track/tests/test_v9_2_overview_m0.py#L407-L430)

- `test_4_card_titles_in_sidebar_render` → 改名为 `test_3_card_titles_in_sidebar_render`
- 断言中的 `'训练收益'` / `'环境挑战'` 数量保持
- 删除 `'身体状态'` / `'活动摘要'` 相关断言
- `test_placeholder_message_includes_review_tab_hint` → 改名 `test_training_effect_placeholder_message_includes_review_tab_hint`
  - 仅断言训练收益占位文案含「复盘」Tab 提示
  - 不再断言身体状态 / 活动摘要占位文案

### Step 4: 新增静态回归测试(同 commit 3)

**新建**: `tests/test_sidebar_placeholder_cleanup.py`

```python
"""活动详情侧栏占位卡清理回归测试。固化占位契约边界。

§4.1 删除后侧栏结构契约 + §4.2 函数留存契约 + §4.4 注释契约。
"""
import os
import re
import unittest


class TestSidebarPlaceholderCleanup(unittest.TestCase):
    """V_PLC P0: 身体状态/活动摘要两张占位卡必须已从 renderActivityDetailSidebar 删除。"""

    @classmethod
    def setUpClass(cls):
        track_html_path = os.path.join(
            os.path.dirname(__file__), "..", "track.html"
        )
        with open(track_html_path, "r", encoding="utf-8") as f:
            cls.html = f.read()

    def _extract_render_sidebar_body(self):
        """提取 renderActivityDetailSidebar 函数体(到下一个 function 定义前)。"""
        idx = self.html.find("function renderActivityDetailSidebar(")
        self.assertGreater(idx, 0, "缺 renderActivityDetailSidebar 函数")
        end = self.html.find("\n    function ", idx + 50)
        return self.html[idx:end]

    def test_no_body_state_in_sidebar_render(self):
        """§4.1 删除后侧栏结构契约:身体状态不应出现在 renderActivityDetailSidebar。"""
        body = self._extract_render_sidebar_body()
        self.assertNotIn("身体状态", body, "身体状态 占位卡仍存在于 renderActivityDetailSidebar")

    def test_no_activity_summary_in_sidebar_render(self):
        """§4.1 删除后侧栏结构契约:活动摘要不应出现在 renderActivityDetailSidebar。"""
        body = self._extract_render_sidebar_body()
        self.assertNotIn("活动摘要", body, "活动摘要 占位卡仍存在于 renderActivityDetailSidebar")

    def test_placeholder_builder_function_still_exists(self):
        """§4.2 函数留存契约:_buildPlaceholderSidebarCard 仍存在(供训练收益/环境挑战空态用)。"""
        self.assertIn(
            "function _buildPlaceholderSidebarCard(",
            self.html,
            "_buildPlaceholderSidebarCard 函数定义已被误删",
        )

    def test_training_effect_placeholder_still_uses_builder(self):
        """§4.2 函数留存契约:训练收益空态仍调 _buildPlaceholderSidebarCard。"""
        # _buildTrainingBenefitCard 体内仍应有 _buildPlaceholderSidebarCard('训练收益', ...)
        idx_te = self.html.find("function _buildTrainingBenefitCard(")
        self.assertGreater(idx_te, 0)
        end = self.html.find("\n    function ", idx_te + 50)
        te_body = self.html[idx_te:end]
        self.assertIn(
            "_buildPlaceholderSidebarCard('训练收益'",
            te_body,
            "训练收益空态降级路径被误删",
        )

    def test_environment_challenge_placeholder_still_uses_builder(self):
        """§4.2 函数留存契约:环境挑战空态仍调 _buildPlaceholderSidebarCard。"""
        idx_ec = self.html.find("function _buildEnvironmentChallengeCard(")
        self.assertGreater(idx_ec, 0)
        end = self.html.find("\n    function ", idx_ec + 50)
        ec_body = self.html[idx_ec:end]
        self.assertIn(
            "_buildPlaceholderSidebarCard('环境挑战'",
            ec_body,
            "环境挑战空态降级路径被误删",
        )

    def test_no_4_card_phrase_in_track_html(self):
        """§4.4 注释契约:历史 '4 张卡(环境/训练收益/身体状态/活动摘要)' 文案不应再出现。"""
        # 不区分单复数匹配,允许"侧栏 4 张卡"
        pattern = re.compile(r"4\s*张卡[^)\n]*身体状态")
        self.assertNotRegex(
            pattern, self.html,
            "track.html 仍含历史 '4 张卡(...身体状态...)' 注释",
        )
        pattern2 = re.compile(r"4\s*张卡[^)\n]*活动摘要")
        self.assertNotRegex(
            pattern2, self.html,
            "track.html 仍含历史 '4 张卡(...活动摘要...)' 注释",
        )

    def test_render_order_preserved(self):
        """§4.1 删除后侧栏结构契约:渲染顺序 weather → te → ec 必须保持。"""
        body = self._extract_render_sidebar_body()
        idx_weather = body.find("_buildWeatherCard(")
        idx_te = body.find("_buildTrainingBenefitCard(")
        idx_ec = body.find("_buildEnvironmentChallengeCard(")
        self.assertGreater(idx_weather, 0)
        self.assertGreater(idx_te, 0)
        self.assertGreater(idx_ec, 0)
        self.assertLess(idx_weather, idx_te, "天气卡应在训练收益之前")
        self.assertLess(idx_te, idx_ec, "训练收益应在环境挑战之前")


if __name__ == "__main__":
    unittest.main()
```

### Step 5: 验证

```bash
# 1. 静态检查:renderActivityDetailSidebar 内不应再出现 身体状态 / 活动摘要
grep -nE "身体状态|活动摘要" track.html

# 预期:仅可能在 _buildPlaceholderSidebarCard 之外的注释/字符串中残留(若仍有,继续清理)
# 但函数体内必须 0 命中(由 test_no_body_state_in_sidebar_render 守护)

# 2. 占位卡函数仍存在
grep -nE "function _buildPlaceholderSidebarCard\(" track.html
# 预期:1 命中

# 3. 占位卡仅被训练收益/环境挑战调用
grep -nE "_buildPlaceholderSidebarCard\(" track.html
# 预期:3 命中(定义 1 + 训练收益 1 + 环境挑战 1)

# 4. 既有测试不能挂
python3 -m unittest test_environment_challenge_frontend test_training_effect_frontend test_v9_2_overview_m0 test_v9_0_detail_tab_review

# 5. 新测试通过
python3 -m unittest test_sidebar_placeholder_cleanup
```

### Step 6: 手工测试

- [ ] 打开任一活动详情 Modal,切换到「概览」Tab
- [ ] 右侧栏应只剩:🌦️ 历史天气 / 🔥 训练收益 / ⛰️ 环境挑战 三张卡
- [ ] 「❤️ 身体状态」「✨ 活动摘要」字样不再出现
- [ ] 「训练收益」空态降级(老 FIT 文件无 TE 字段)仍正常显示占位
- [ ] 「环境挑战」空态降级(phase<1)仍正常显示占位
- [ ] 切到「复盘」Tab,功能不受影响
- [ ] 风险预警「AI 分析」按钮工作正常
- [ ] 切走 / 切回 Modal,占位卡状态正常

---

## 六、验收标准

### 6.1 代码验收

- [ ] [track.html L7254-L7260](file:///Users/fanglei/应用开发/AI%20track/track.html#L7254-L7260) 中 2 行占位卡渲染调用已删除
- [ ] [track.html L7288-L7295](file:///Users/fanglei/应用开发/AI%20track/track.html#L7288-L7295) `_buildPlaceholderSidebarCard` 函数定义保留
- [ ] [track.html L7330](file:///Users/fanglei/应用开发/AI%20track/track.html#L7330) 训练收益空态降级调用保留
- [ ] [track.html L7419](file:///Users/fanglei/应用开发/AI%20track/track.html#L7419) 环境挑战空态降级调用保留
- [ ] L7234 / L7235 / L3431 / L4831 / L4833 / L7225 共 6 处注释已同步更新

### 6.2 测试验收

- [ ] `tests/test_environment_challenge_frontend.py` L171-L189 范围 5 处断言已更新
- [ ] `tests/test_v9_2_overview_m0.py` L407-L430 范围 4-card 断言已更新
- [ ] 新建 `tests/test_sidebar_placeholder_cleanup.py` 通过

### 6.3 静态验收

- [ ] `grep -nE "身体状态|活动摘要" track.html` 在 `renderActivityDetailSidebar` 函数体内 0 命中
- [ ] `grep -nE "function _buildPlaceholderSidebarCard\(" track.html` = 1 命中
- [ ] `grep -nE "_buildPlaceholderSidebarCard\(" track.html` = 3 命中(定义 + 训练收益 + 环境挑战)

### 6.4 既有功能验收

- [ ] 既有 7 个测试文件全过:
  - `test_environment_challenge_frontend`
  - `test_training_effect_frontend`
  - `test_v9_2_overview_m0`
  - `test_v9_0_detail_tab_review`
  - `test_fatigue_review_quality_gate`
  - `test_p7_fatigue_review_design`
  - 其它相关测试文件
- [ ] 复盘 Tab / 风险预警 / AI 洞察按钮全部正常工作
- [ ] Modal 关闭 / 重新打开,无内存泄漏 / DOM 残留

---

## 七、完成报告要求

完成本任务后,请输出:

```text
P0 侧栏占位卡清理完成报告

1. 本次目标
2. 已更新文件清单(track.html / tests/ 新建)
3. 删除的 JS 行(L7258 / L7259)
4. 注释同步情况(6 处)
5. 测试更新与新建清单
6. 静态检查结果(grep 输出)
7. 验收结果
8. 未完成事项
9. 下一步建议
```

---

## 八、下一步建议

P0 完成后,建议进入:

```text
P1 视觉与布局调优(可选):
  - 验证侧栏剩 3 张卡后布局是否协调(可能需要调整 grid 高度或 gap)
  - 评估是否需要在「环境挑战」卡下方加 spacer 防止空白

P2 与活动建议改造并行:
  - 风险预警 → 活动建议重构(p0_activity_advice_contract_prompt.md 已开 P0)
  - 本次删除的「活动摘要」语义将由活动建议承担

P3 历史文档清理(可选):
  - docs/detail_tab_review_manual_test_checklist.md 中是否仍引用「身体状态/活动摘要」卡片
  - docs/fatigue_review_realignment_plan_v1.md 中 "身体状态如何变化" 是否需要在概览 Tab 显式入口
```

---

> **结束**: 本任务为 P0 死代码清理,工作量小(约 6 处编辑 + 2 个测试文件 + 1 个新测试),不影响既有功能。完成后视觉上侧栏由 4 张卡减为 3 张卡,信息密度提升,与复盘 Tab AI 洞察定位一致。