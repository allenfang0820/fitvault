# P4 活动建议人工验收与边界样例回归提示词

> 任务类型：P4 人工验收 / 边界样例回归 / 验收清单落档
> 适用范围：轨迹报告侧栏「活动建议」桌面端体验、真实 FIT/GPX 样例、用户输入组合、阅后即焚生命周期、边界文案
> 前置条件：P0 契约已固化，P1 后端链路已实现，P2 前端 UI 已接入，P3 旧「风险预警」生产链路已删除
> 核心目标：用真实轨迹与边界样例验证「活动建议」功能可用、契约不越界、旧风险预警不回潮，并形成可重复执行的人工验收清单

---

## 零、架构契约核对

执行本任务前必须阅读并遵守：

- `docs/activity_advice_feature_design_v2.md`
- `docs/p1_activity_advice_backend_prompt.md`
- `docs/p2_activity_advice_frontend_prompt.md`
- `docs/p3_activity_advice_cleanup_prompt.md`
- `docs/js_api_contract.json`
- 当前生产实现：`main.py` / `llm_backend.py` / `track.html`
- 当前测试：`tests/test_activity_advice_prompts.py` / `tests/test_activity_advice_integration.py` / `tests/test_activity_advice_frontend.py` / `tests/test_activity_advice_cleanup.py`

本任务必须遵守以下强制契约：

- 当前功能名称只能是「活动建议」，不得在生产 UI 或验收结论中恢复为「风险预警」。
- 活动建议只用于路线准备建议，不是安全预警、天气预报、医学建议或危险判断。
- 前端只能向后端传用户显式 planning context：`user_activity_type` 与 `planned_start_time`。
- `planned_start_time` 只能来自用户在活动建议卡片中的显式输入，不得从 FIT/GPX 历史时间、轨迹点时间、活动详情时间或文件名提取。
- `user_activity_type` 只能来自用户选择，不得从文件名、活动标题、设备名或历史记录推断。
- 活动建议后端输入只允许后端路线事实白名单 + 用户显式 planning context。
- 活动建议不得消费历史天气、`_track_weather`、`weather_json`、`points[]`、`placemarks[]`、`shadow_diff`、DOM 文本或前端推导事实。
- 未填写计划活动时间时，`weather_check` 必须表达信息不足或出发前检查清单，不得给出具体天气判断。
- 活动建议结果只存在前端内存，不写 DB、不写 `localStorage` / `sessionStorage`、不进入 `ai_snapshots`、不进入普通 AI 教练 `_chat_messages`。
- 切换轨迹、导入新文件、切主 Tab、离开 report 侧栏、重新生成建议时必须丢弃旧活动建议结果。
- 本任务原则上不新增产品能力、不新增 DB 字段、不接入天气 API、不重写 prompt 主体；如人工验收发现问题，应优先记录为缺陷或下一任务，而不是在 P4 中大改实现。

---

## 一、任务背景

P0-P3 已完成从旧「风险预警」到新「活动建议」的迁移：

```text
__REPORT_ACTIVITY_ADVICE__ -> { ok, activity_advice }
```

当前仍需要一次贴近真实使用的人工验收，原因是：

1. GPX 可能只有纯路线几何，缺少运动类型和历史活动上下文。
2. FIT 可能带历史时间，但活动建议面向未来计划，不能自动使用历史时间。
3. 天气建议强依赖计划活动时间，未填写时必须降级为检查清单。
4. 活动建议是临时结果，生命周期必须和轨迹报告 UI 行为一致。
5. 自动化测试能保护契约，但无法完全判断文案是否越界、体验是否清楚。

P4 的目标是把这些边界变成可重复执行的人工验收表，并用当前桌面端实际跑一轮。

---

## 二、任务目标

完成 P4 人工验收与边界样例回归：

1. 新建 `docs/activity_advice_manual_test_checklist.md`。
2. 明确验收环境、前置配置、样例轨迹、输入组合、预期行为和实际结果记录格式。
3. 至少覆盖 FIT / GPX 两类轨迹；KML 不作为本次版本目标。
4. 覆盖四类用户输入组合：
   - 无活动类型 + 无计划活动时间
   - 有活动类型 + 无计划活动时间
   - 无活动类型 + 有计划活动时间
   - 有活动类型 + 有计划活动时间
5. 覆盖路线边界：
   - 纯 GPX 路线
   - DB 活动路线
   - 高爬升 / 高海拔 / 高坡度路线
   - 短距离路线
   - 无海拔或海拔缺失路线
6. 验证天气时间边界：无计划时间时不伪造具体天气；有计划时间时也只能给检查建议，除非未来明确接入实时/预报天气 API。
7. 验证阅后即焚：切换轨迹、导入新文件、切主 Tab、离开 report 侧栏、重新生成时旧建议清空。
8. 验证旧风险预警不回潮：UI、响应字段、契约文案和生产扫描都不应恢复旧命名。
9. 运行 P1-P3 的自动化回归命令，并把结果记录到清单。

---

## 三、本任务改动范围

建议新增文件：

- `docs/activity_advice_manual_test_checklist.md`

允许改动文件：

- `docs/activity_advice_feature_design_v2.md`：如需追加 P4 验收状态或链接，可小幅更新。
- `docs/js_api_contract.json`：仅当发现契约描述与 P3 后实际状态不一致时修正。
- `tests/test_activity_advice_*.py`：仅当人工验收发现自动化门禁缺口，且可用静态测试稳定覆盖时补测。

原则上禁止改动：

- 不改 `main.py` 活动建议链路，除非人工验收发现明确 bug 且修复很小。
- 不改 `llm_backend.py` prompt 主体，除非发现严重越界文案必须收紧。
- 不改 `track.html` 视觉结构，除非发现阻塞验收的交互 bug。
- 不新增 DB 字段。
- 不接入天气 API。
- 不恢复旧风险预警代码。

如果必须修改生产代码：

- 先在完成报告中单独标明“P4 中发现并修复的缺陷”。
- 修复后必须重新运行 P1-P3 自动化回归。
- 不要把新增产品能力混入 P4。

---

## 四、验收清单文档结构

新建：

```text
docs/activity_advice_manual_test_checklist.md
```

建议结构如下：

```markdown
# 活动建议人工验收与边界样例回归清单

> 状态：待执行 / 执行中 / 已通过 / 有阻塞
> 日期：
> 执行人：
> 应用版本 / commit：
> LLM 配置：

## 1. 验收范围

## 2. 强制契约

## 3. 样例轨迹资产

## 4. 输入组合矩阵

## 5. 路线边界矩阵

## 6. 天气时间边界

## 7. 阅后即焚生命周期

## 8. 旧风险预警回潮检查

## 9. 自动化回归结果

## 10. 缺陷记录

## 11. 验收结论
```

---

## 五、样例轨迹资产盘点

执行前先盘点本地可用 FIT / GPX 轨迹文件，不要凭记忆假设：

```bash
find . -iname "*.fit" -o -iname "*.gpx"
```

或使用项目约定的轨迹目录和导入目录进行扫描。

在清单中记录：

| 样例 ID | 文件类型 | 文件名/来源 | 特征 | 是否已覆盖 | 备注 |
|---|---|---|---|---|---|
| FIT-01 | FIT |  | DB 活动 / 有历史时间 |  |  |
| GPX-01 | GPX |  | 纯路线 / 无运动类型 |  |  |
| CLIMB-01 | 任意 |  | 高爬升 / 高坡度 |  |  |
| SHORT-01 | 任意 |  | 短距离 |  |  |
| NOELE-01 | 任意 |  | 无海拔或海拔缺失 |  |  |

如果缺少 FIT / GPX 目标样例：

- 不要伪造已通过。
- 在清单写明“未覆盖：缺少对应样例”。
- 给出补样建议，例如新增一条无海拔 GPX 或短距离 GPX。

非目标说明：

- KML 不作为本次版本目标，不计入 P4 通过/阻塞条件。

---

## 六、输入组合验收矩阵

每条代表性轨迹至少执行以下四组：

| 用例 ID | 活动类型 | 计划活动时间 | 预期重点 | 结果 |
|---|---|---|---|---|
| IN-01 | 空 | 空 | 天气检查必须信息不足；不推断活动类型 |  |
| IN-02 | 徒步 / hiking | 空 | 可按徒步语境建议；天气仍信息不足 |  |
| IN-03 | 空 | 用户显式时间 | 可引用用户填写计划时间；不推断活动类型 |  |
| IN-04 | 越野跑 / trail_running 等 | 用户显式时间 | 可结合活动类型和计划时间组织建议 |  |

验收要点：

- 请求前 `datetime-local` 默认空。
- 切换轨迹后两个输入建议清空或符合 P2 约定。
- AI 输出中不能出现“根据你的 FIT 开始时间”“历史活动当天”等暗示。
- AI 输出中不能说“天气为晴/雨/温度 X”这类未由实时预报支持的确定性天气。
- `weather_check.basis` 或文案应清楚说明依据来自用户计划时间或信息不足。

---

## 七、路线边界验收矩阵

| 用例 ID | 路线类型 | 预期重点 | 结果 |
|---|---|---|---|
| RT-01 | 纯 GPX 路线 | 即使无运动类型/计划时间，也能基于距离、爬升、海拔、位置给准备建议 |  |
| RT-02 | DB 活动路线 | 使用后端路线事实，不使用前端 points 拼 prompt |  |
| RT-03 | 高爬升/高海拔路线 | 装备和体力安排应体现爬升、海拔或坡度压力 |  |
| RT-04 | 短距离路线 | 不应夸大补给、装备或体力压力 |  |
| RT-05 | 无海拔/海拔缺失路线 | 应承认信息不足，不硬编爬升/坡度建议 |  |

记录每个用例：

- 输入轨迹
- 用户填写项
- AI 输出四个维度是否齐全
- 是否有越界事实
- 是否有旧风险预警词
- 结论：通过 / 有问题 / 未覆盖

---

## 八、阅后即焚生命周期验收

必须人工验证以下触发点：

| 用例 ID | 操作 | 预期 | 结果 |
|---|---|---|---|
| LIFE-01 | 生成活动建议后切换主 Tab | 旧建议清空 |  |
| LIFE-02 | 生成活动建议后离开 report 侧栏 | 旧建议清空 |  |
| LIFE-03 | 生成活动建议后导入新 GPX/FIT | 旧建议清空 |  |
| LIFE-04 | 生成活动建议后切换另一条轨迹 | 旧建议清空 |  |
| LIFE-05 | 对同一轨迹重新点击生成 | 旧建议先清空，再显示新结果 |  |
| LIFE-06 | 关闭/刷新页面后重新打开 | 不保留旧建议 |  |

同时检查：

- `localStorage` / `sessionStorage` 不应出现活动建议结果。
- 普通 AI 教练聊天历史不应追加活动建议内容。
- DB 或历史记录中不应新增活动建议持久化字段。

---

## 九、旧风险预警回潮检查

人工 UI 检查：

- 轨迹报告侧栏只显示「活动建议」。
- 按钮不应出现「风险预警」。
- 错误文案不应出现「风险预警生成失败」。
- 输出字段和前端状态不应使用 `risk_assessment`。

静态命令：

```bash
rg "REPORT_RISK_ASSESSMENT|__REPORT_RISK_ASSESSMENT__|build_risk_assessment|empty_risk_assessment|normalize_risk_assessment|_build_risk_assessment_messages|PY_REPORT_RISK_ASSESSMENT|requestRiskAssessment|buildRiskAssessmentHTML|resetRiskAssessmentState|currentRiskAssessment|risk-assessment|风险预警" main.py llm_backend.py track.html
rg "__REPORT_RISK_ASSESSMENT__|risk_assessment_contract|旧风险预警兼容名|待 cleanup 删除" docs/js_api_contract.json
```

预期：无匹配。

---

## 十、自动化回归命令

必须运行并记录结果：

```bash
python3 -m unittest discover -s tests -p 'test_activity_advice_*.py'
python3 -m unittest discover -s tests -p 'test_response_envelope_contract.py'
python3 -m json.tool docs/js_api_contract.json >/tmp/js_api_contract_check.json
PYTHONPYCACHEPREFIX=/private/tmp python3 -m py_compile main.py llm_backend.py
```

建议运行并记录结果：

```bash
python3 -m pytest tests/test_e2e_fatigue_review.py
python3 -m unittest discover -s tests -p 'test_fatigue_review_ai_preflight_p8.py'
```

如果本机 `node` 可用，检查 `track.html` 内联脚本：

```bash
node -e "const fs=require('fs'); const html=fs.readFileSync('track.html','utf8'); const scripts=[...html.matchAll(/<script[^>]*>([\\s\\S]*?)<\\/script>/gi)].map(m=>m[1]); for (const [i,script] of scripts.entries()) new Function(script); console.log('parsed scripts:', scripts.length);"
```

如果 `node` 不在 PATH，可使用项目 bundled Node，路径以当前环境为准。

---

## 十一、执行方式建议

### 11.1 如果当前环境可启动桌面端

1. 启动应用。
2. 导入或选择样例轨迹。
3. 打开轨迹报告侧栏。
4. 对每个输入组合点击「生成建议」。
5. 记录四个维度的输出、边界文案、异常和截图路径。
6. 执行阅后即焚操作，记录结果。
7. 跑自动化回归。
8. 更新 `docs/activity_advice_manual_test_checklist.md`。

### 11.2 如果当前环境无法启动桌面端

仍需完成可执行清单：

1. 盘点样例资产。
2. 写清楚人工验收步骤、预期、记录表格。
3. 跑静态和自动化回归。
4. 在清单中标注“桌面端人工点击未执行”，列出阻塞原因。
5. 不要把未执行的人工验收标为通过。

---

## 十二、验收结论标准

可以判定 P4 通过的条件：

- 自动化回归全部通过。
- 至少 1 条 FIT 或 DB 活动路线通过。
- 至少 1 条 GPX 纯路线通过。
- 四种输入组合至少在一条代表性路线中全部通过。
- 无计划活动时间时，天气检查不伪造具体天气。
- 历史 FIT/GPX 时间没有被自动填入或引用。
- 阅后即焚触发点全部通过。
- 生产 UI 和生产代码无旧「风险预警」回潮。
- 所有未覆盖项都有明确原因和补样建议。

如果不能满足以上条件：

- P4 状态应标为“有阻塞”或“部分通过”。
- 必须记录阻塞原因。
- 必须给出 P5 修复或补样任务建议。

---

## 十三、完成报告格式

完成本任务后，请输出：

```text
P4 活动建议人工验收与边界样例回归完成报告

1. 本次目标
2. 已创建/更新文件
3. 样例轨迹覆盖情况
4. 输入组合覆盖情况
5. 路线边界覆盖情况
6. 阅后即焚验证结果
7. 旧风险预警回潮检查结果
8. 自动化回归结果
9. 未覆盖项 / 阻塞项
10. 下一步建议
```

---

## 十四、下一任务建议

P4 完成后，根据验收结论选择：

```text
P5A 活动建议缺陷修复与回归
```

适用场景：

- P4 发现活动建议越界使用历史时间。
- P4 发现天气检查伪造具体天气。
- P4 发现阅后即焚触发点遗漏。
- P4 发现 GPX 纯路线无法生成可用建议。

或：

```text
P5B 活动建议验收冻结与发布说明
```

适用场景：

- P4 人工验收和自动化回归均通过。
- 只需要整理发布说明、限制说明和后续增强方向。

P5B 推荐输出：

- `docs/activity_advice_release_notes.md`
- 明确 v1 限制：不做天气预报、不做安全预警、不做医学建议、不持久化结果。
- 记录后续可选增强：实时天气 API、用户体能画像联动、路线补给点建议、离线装备清单模板。
