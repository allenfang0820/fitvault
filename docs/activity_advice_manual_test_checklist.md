# 活动建议人工验收与边界样例回归清单

> 状态：P5B 真实点击已出内容 / 待补齐矩阵与 route facts 一致性核对
> 日期：2026-06-12
> 执行人：Codex
> 应用版本 / commit：当前工作区未提交状态
> LLM 配置：未在本轮读取或修改；桌面端真实 LLM 生成未执行

---

## 1. 验收范围

本清单用于验证轨迹报告侧栏「活动建议」功能：

- 活动建议 UI 是否替代旧「风险预警」。
- 活动类型与计划活动时间是否只来自用户显式输入。
- 无计划活动时间时，天气检查是否只给信息不足或检查清单。
- 活动建议是否仅临时存在于前端内存。
- 切换轨迹、导入新文件、切 Tab、离开 report 侧栏、重新生成时是否清空旧建议。
- 旧 `__REPORT_RISK_ASSESSMENT__` 生产链路是否无回潮。

本轮已完成：

- 样例轨迹资产盘点。
- 静态契约检查。
- 自动化回归。
- 可重复执行的人工验收步骤落档。
- P5A 后端活动建议当前轨迹快照修复：DB 活动与无 `activity_id` 的当前 GPX/FIT 展示轨迹均可构建活动建议专用白名单快照。
- P5B 自动化回归复核、旧风险预警回潮扫描、活动建议链路扫描、发布说明落档。
- P5B 桌面端手动点击补充验收：用户在 pywebview 窗口中已看到「生成建议」返回内容。

本轮未完成：

- 完整桌面端矩阵验收。
- route facts 一致性核对。

阻塞说明：当前执行环境未启动桌面端 UI，也未进行 pywebview 文件选择和真实 LLM 调用；因此不得把 P4 判定为“已通过”。

P5B 阻塞说明：本轮已尝试启动桌面端应用，`python3 main.py` 可启动 pywebview 进程与 Watchdog，但 `http://127.0.0.1:27917/track.html` 对外访问返回 connection refused / `ERR_CONNECTION_REFUSED`，未能通过浏览器工具完成真实点击「生成建议」。因此不得标记 P5B 冻结通过。

P5B 手动补充验收：用户在 2026-06-12 提供桌面端截图，pywebview 当前页面为 `127.0.0.1:47778/track.html`，轨迹报告「活动建议」卡片已生成补给建议、天气检查、装备建议等内容。截图中用户显式选择活动类型为「登山」，计划活动时间为 `2026/12/01 17:03`，输出可见引用了高海拔、冬季傍晚、路线距离/爬升/最高海拔等路线准备语境。该结果解除“真实点击完全无输出”的阻塞，但截图中 UI 顶部显示 `8.34km / 爬升 896m / 最高 5337m`，AI 文案可见 `全程10.06km / 累计爬升1203m / 最高海拔5337m`，距离和爬升存在不一致，需作为 route facts 一致性残余风险继续核对。

P5A 修复说明：此前点击「生成建议」只依赖 DB `_ai_snapshot`，当前导入/展示但无 `activity_id` 的 GPX/FIT 会被误判为未加载轨迹。现已新增后端 `_activity_advice_snapshot`，在 `sync_track_context(...)` 中刷新；DB 活动来自 Resolver truth 白名单，临时轨迹来自后端点列聚合后的路线事实，不把 `points[]`、`placemarks[]`、历史天气或历史时间送入 LLM。

版本范围说明：KML 不作为本次版本目标，不计入本轮 P4 通过/阻塞条件。

---

## 2. 强制契约

- 当前功能名称只能是「活动建议」，不得恢复为「风险预警」。
- 活动建议不是安全预警、天气预报、医学建议或危险判断。
- 前端只能发送 `user_activity_type` 和 `planned_start_time`。
- `planned_start_time` 只能来自用户在卡片中的显式输入。
- 不得从 FIT/GPX 历史时间、轨迹点时间、活动详情时间或文件名自动填充计划活动时间。
- `user_activity_type` 只能来自用户选择，不得从文件名、活动标题、设备名或历史记录推断。
- 活动建议后端只能消费路线事实白名单 + 用户显式 planning context。
- 活动建议不得消费历史天气、`_track_weather`、`weather_json`、`points[]`、`placemarks[]`、`shadow_diff`、DOM 文本或前端推导事实。
- 未填写计划活动时间时，`weather_check` 必须表达信息不足或出发前检查清单，不得给出具体天气判断。
- 活动建议结果不写 DB、不写 `localStorage` / `sessionStorage`、不进入 `ai_snapshots`、不进入普通 AI 教练 `_chat_messages`。
- 切换轨迹、导入新文件、切主 Tab、离开 report 侧栏、重新生成建议时必须丢弃旧活动建议结果。

---

## 3. 样例轨迹资产

盘点命令：

```bash
find . -iname "*.fit" -o -iname "*.gpx"
```

盘点结果：

| 样例 ID | 文件类型 | 文件名/来源 | 特征 | 是否已覆盖 | 备注 |
|---|---|---|---|---|---|
| FIT-01 | FIT | `local_tracks/240827212_ACTIVITY_1.fit` | DB/FIT 活动候选，约 1.3 MB | 未人工覆盖 | 待桌面端加载后确认 |
| FIT-02 | FIT | `local_tracks/门头沟徒步.fit` | 中文文件名，徒步语义候选，约 747 KB | 未人工覆盖 | 可用于活动类型不自动推断检查 |
| GPX-01 | GPX | `local_tracks/COURSE_443798.gpx` | GPX 路线候选，约 239 KB | 未人工覆盖 | 可用于纯路线检查 |
| GPX-02 | GPX | `local_tracks/471385635607839224_4.gpx` | 大 GPX 路线候选，约 6.3 MB | 未人工覆盖 | 可用于长路线或高复杂度路线检查 |
| GPX-03 | GPX | `local_tracks/test_naive.gpx` | 极小 GPX，约 338 B | 未人工覆盖 | 可用于短距离/最小数据检查 |
| CLIMB-01 | 任意 | 待人工确认 | 高爬升/高海拔/高坡度 | 未覆盖 | 需从 FIT/GPX 加载后确认指标 |
| SHORT-01 | GPX | `local_tracks/test_naive.gpx` | 短距离候选 | 未人工覆盖 | 需加载后确认距离 |
| NOELE-01 | 任意 | 待人工确认 | 无海拔或海拔缺失 | 未覆盖 | 需补样或解析后确认 |

补样建议：

- 新增 1 条明确无海拔 GPX 样例。
- 标注 1 条高爬升/高坡度轨迹作为固定回归样例。

非目标说明：KML 不作为本次版本目标，不计入 P4 通过/阻塞条件。

---

## 4. 输入组合矩阵

以下矩阵待桌面端人工执行。每条代表性轨迹至少覆盖一次。

| 用例 ID | 活动类型 | 计划活动时间 | 预期重点 | 结果 |
|---|---|---|---|---|
| IN-01 | 空 | 空 | 天气检查必须信息不足；不推断活动类型 | 未执行 |
| IN-02 | 徒步 / hiking | 空 | 可按徒步语境建议；天气仍信息不足 | 未执行 |
| IN-03 | 空 | 用户显式时间 | 可引用用户填写计划时间；不推断活动类型 | 未执行 |
| IN-04 | 越野跑 / trail_running | 用户显式时间 | 可结合活动类型和计划时间组织建议 | 未执行 |

人工验收记录项：

- 请求前 `datetime-local` 是否默认空。
- 切换轨迹后活动类型和计划时间是否清空。
- 输出是否出现“根据 FIT 开始时间”“历史活动当天”等越界表达。
- 输出是否出现“天气为晴/雨/温度 X”等未由天气 API 支撑的确定性天气。
- `weather_check.basis` 是否说明依据来自用户计划时间或信息不足。

---

## 5. 路线边界矩阵

| 用例 ID | 路线类型 | 推荐样例 | 预期重点 | 结果 |
|---|---|---|---|---|
| RT-01 | 纯 GPX 路线 | `local_tracks/COURSE_443798.gpx` | 即使无运动类型/计划时间，也能基于距离、爬升、海拔、位置给准备建议 | 未执行 |
| RT-02 | DB/FIT 活动路线 | `local_tracks/240827212_ACTIVITY_1.fit` | 使用后端路线事实，不使用前端 points 拼 prompt | 未执行 |
| RT-03 | 高爬升/高海拔路线 | 待确认 | 装备和体力安排体现爬升、海拔或坡度压力 | 未覆盖 |
| RT-04 | 短距离路线 | `local_tracks/test_naive.gpx` | 不应夸大补给、装备或体力压力 | 未执行 |
| RT-05 | 无海拔/海拔缺失路线 | 待补样 | 应承认信息不足，不硬编爬升/坡度建议 | 未覆盖 |
每个用例执行时记录：

- 输入轨迹。
- 用户填写项。
- AI 输出四个维度是否齐全。
- 是否有越界事实。
- 是否有旧风险预警词。
- 结论：通过 / 有问题 / 未覆盖。

---

## 6. 天气时间边界

| 用例 ID | 输入条件 | 预期 | 结果 |
|---|---|---|---|
| WX-01 | 不填计划活动时间 | `weather_check` 为信息不足或检查清单，不给具体天气 | 未执行 |
| WX-02 | 填写未来计划时间 | 可提醒按该时间检查天气，但不伪造具体天气 | 未执行 |
| WX-03 | FIT 带历史开始时间但计划时间为空 | 不引用 FIT 历史开始时间 | 未执行 |
| WX-04 | GPX 带轨迹点时间但计划时间为空 | 不引用轨迹点历史时间 | 未执行 |

自动化覆盖现状：

- `tests/test_activity_advice_prompts.py` 已覆盖 payload 禁止 `start_time` / `start_time_utc` / `weather_context`。
- `tests/test_activity_advice_integration.py` 已覆盖后端不向活动建议 builder 传 `_track_weather`。
- `tests/test_activity_advice_integration.py` 已覆盖无 `activity_id` 的临时轨迹可生成活动建议 route facts，且不携带 `points`、`placemarks`、`weather`、历史时间。
- `tests/test_activity_advice_integration.py` 已覆盖连续 `sync_track_context(...)` 会覆盖 `_activity_advice_snapshot`，不残留上一条轨迹事实。
- `tests/test_activity_advice_frontend.py` 已覆盖前端只发送 planning context。

---

## 7. 阅后即焚生命周期

| 用例 ID | 操作 | 预期 | 结果 |
|---|---|---|---|
| LIFE-01 | 生成活动建议后切换主 Tab | 旧建议清空 | 未执行 |
| LIFE-02 | 生成活动建议后离开 report 侧栏 | 旧建议清空 | 未执行 |
| LIFE-03 | 生成活动建议后导入新 GPX/FIT | 旧建议清空 | 未执行 |
| LIFE-04 | 生成活动建议后切换另一条轨迹 | 旧建议清空 | 未执行 |
| LIFE-05 | 对同一轨迹重新点击生成 | 旧建议先清空，再显示新结果 | 未执行 |
| LIFE-06 | 关闭/刷新页面后重新打开 | 不保留旧建议 | 未执行 |

自动化覆盖现状：

- `tests/test_activity_advice_frontend.py` 已静态覆盖 `switchTab` / `switchSidebarTab` / `applyDataAndRender` 调用 `resetActivityAdviceState`。
- `requestActivityAdvice()` 中静态覆盖重新生成前调用 `resetActivityAdviceState({ keepInputs: true })`。

人工执行时还需检查：

- `localStorage` / `sessionStorage` 不出现活动建议结果。
- 普通 AI 教练聊天历史不追加活动建议内容。
- DB 或历史记录不新增活动建议持久化字段。

---

## 8. 旧风险预警回潮检查

人工 UI 检查：

| 检查项 | 预期 | 结果 |
|---|---|---|
| 轨迹报告侧栏标题 | 只显示「活动建议」 | 未执行 |
| 按钮文案 | 不出现「风险预警」 | 未执行 |
| 错误文案 | 不出现「风险预警生成失败」 | 未执行 |
| 输出字段 | 不使用 `risk_assessment` | 未执行 |

静态检查已执行：

```bash
rg "REPORT_RISK_ASSESSMENT|__REPORT_RISK_ASSESSMENT__|build_risk_assessment|empty_risk_assessment|normalize_risk_assessment|_build_risk_assessment_messages|PY_REPORT_RISK_ASSESSMENT|requestRiskAssessment|buildRiskAssessmentHTML|resetRiskAssessmentState|currentRiskAssessment|risk-assessment|风险预警" main.py llm_backend.py track.html
rg "__REPORT_RISK_ASSESSMENT__|risk_assessment_contract|旧风险预警兼容名|待 cleanup 删除" docs/js_api_contract.json
```

结果：

- 生产代码扫描：通过，无匹配。
- `docs/js_api_contract.json` 旧兼容描述扫描：通过，无匹配。

---

## 9. 自动化回归结果

| 命令 | 结果 | 备注 |
|---|---|---|
| `python3 -m unittest discover -s tests -p 'test_activity_advice_*.py'` | 通过，27 tests OK | 有 urllib3 LibreSSL 环境警告 |
| `python3 -m unittest discover -s tests -p 'test_response_envelope_contract.py'` | 通过，25 tests OK | 有 urllib3 LibreSSL 环境警告和既有 ResourceWarning |
| `python3 -m json.tool docs/js_api_contract.json` | 通过 | JSON 合法 |
| `PYTHONPYCACHEPREFIX=/private/tmp python3 -m py_compile main.py llm_backend.py` | 通过 | 编译通过 |
| `python3 -m pytest tests/test_e2e_fatigue_review.py` | 通过，42 passed | 有 urllib3 LibreSSL 环境警告 |
| `python3 -m unittest discover -s tests -p 'test_fatigue_review_ai_preflight_p8.py'` | 通过，6 tests OK | 有 urllib3 LibreSSL 环境警告 |
| bundled Node 解析 `track.html` 内联脚本 | 通过，`parsed scripts: 5` | 使用 `/Users/fanglei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node` |

P5A 追加自动化回归：

| 命令 | 结果 | 备注 |
|---|---|---|
| `python3 -m unittest discover -s tests -p 'test_activity_advice_*.py'` | 通过，32 tests OK | 新增当前轨迹快照与 payload 白名单覆盖；有 urllib3 LibreSSL 环境警告 |
| `python3 -m unittest discover -s tests -p 'test_response_envelope_contract.py'` | 通过，25 tests OK | 有 urllib3 LibreSSL 环境警告和既有 ResourceWarning |
| `python3 -m json.tool docs/js_api_contract.json` | 通过 | JSON 合法 |
| `PYTHONPYCACHEPREFIX=/private/tmp python3 -m py_compile main.py llm_backend.py` | 通过 | 编译通过 |
| `python3 -m pytest tests/test_e2e_fatigue_review.py` | 通过，42 passed | 有 urllib3 LibreSSL 环境警告 |
| `python3 -m unittest discover -s tests -p 'test_fatigue_review_ai_preflight_p8.py'` | 通过，6 tests OK | 有 urllib3 LibreSSL 环境警告 |
| 旧风险预警生产链路扫描 | 通过，无匹配 | `rg` 退出码 1 表示未命中 |

P5B 追加自动化回归：

| 命令 | 结果 | 备注 |
|---|---|---|
| `python3 -m unittest discover -s tests -p 'test_activity_advice_*.py'` | 通过，32 tests OK | 有 urllib3 LibreSSL 环境警告 |
| `python3 -m unittest discover -s tests -p 'test_response_envelope_contract.py'` | 通过，25 tests OK | 有 urllib3 LibreSSL 环境警告和既有 ResourceWarning |
| `python3 -m json.tool docs/js_api_contract.json` | 通过 | JSON 合法 |
| `PYTHONPYCACHEPREFIX=/private/tmp python3 -m py_compile main.py llm_backend.py` | 通过 | 编译通过 |
| `python3 -m pytest tests/test_e2e_fatigue_review.py` | 通过，42 passed | 有 urllib3 LibreSSL 环境警告 |
| `python3 -m unittest discover -s tests -p 'test_fatigue_review_ai_preflight_p8.py'` | 通过，6 tests OK | 有 urllib3 LibreSSL 环境警告 |
| bundled Node 解析 `track.html` 内联脚本 | 通过，`parsed scripts: 5` | 使用 bundled Node |
| 旧风险预警生产链路扫描 | 通过，无匹配 | `rg` 退出码 1 表示未命中 |
| 活动建议链路扫描 | 通过，链路存在 | `REPORT_ACTIVITY_ADVICE`、`_activity_advice_snapshot`、`requestActivityAdvice` 均存在 |

P5B 桌面端尝试记录：

| 项目 | 结果 | 备注 |
|---|---|---|
| `python3 main.py` | 可启动 | pywebview 进程启动，Watchdog 已启动 |
| `urllib.request` 访问 `http://127.0.0.1:27917/track.html` | 失败 | connection refused |
| Browser 插件访问 `http://127.0.0.1:27917/track.html` | 失败 | `net::ERR_CONNECTION_REFUSED` |
| 真实点击「生成建议」 | 未执行 | 无可访问页面 |
| 真实 OpenClaw / LLM 输出判断 | 未执行 | 未完成真实点击 |

P5B 用户手动补充验收：

| 项目 | 结果 | 备注 |
|---|---|---|
| pywebview 页面 | 通过 | 用户截图显示 `127.0.0.1:47778/track.html` 可用 |
| 真实点击「生成建议」 | 通过 | 已生成活动建议内容 |
| 活动类型显式输入 | 通过 | 截图显示选择「登山」 |
| 计划活动时间显式输入 | 通过 | 截图显示 `2026/12/01 17:03` |
| 输出四类建议 | 部分可见通过 | 截图可见补给建议、天气检查、装备建议；下方体力安排可能被截断，待滚动确认 |
| 天气时间语境 | 通过 | 输出围绕用户计划时间做检查建议，未见使用历史 FIT/GPX 时间 |
| 旧风险预警文案 | 通过 | 截图未见「风险预警」文案 |
| route facts 一致性 | 待核对 | UI 顶部 `8.34km/896m/5337m` 与 AI 文案 `10.06km/1203m/5337m` 存在差异 |

已知环境提示：

- `urllib3` 提示当前 Python ssl 模块使用 LibreSSL 2.8.3，不影响本轮测试通过。
- `tests/test_response_envelope_contract.py` 有既有未关闭文件 `ResourceWarning`，不影响本轮测试通过。

---

## 10. 缺陷记录

| 缺陷 ID | 严重级别 | 描述 | 状态 | 建议 |
|---|---|---|---|---|
| P4-BLOCK-001 | 中 | 未执行桌面端真实点击与真实 LLM 输出人工判断 | 阻塞人工验收通过 | 进入 P5A 或单独人工验收轮次执行 |
| P4-GAP-001 | 低 | 高爬升/无海拔样例尚未标定 | 未覆盖 | 从现有 FIT/GPX 中标定或补样 |
| P5A-FIX-001 | 中 | 当前导入/展示但无 DB `activity_id` 的轨迹无法进入活动建议 LLM route facts | 已修复 | 待桌面端点击当前 19.19 km / 1118 m 轨迹确认真实输出 |
| P5B-BLOCK-001 | 高 | 未能完成桌面端真实点击「生成建议」与真实 OpenClaw / LLM 输出判断 | 已部分解除 | 用户手动截图确认已能生成内容；仍需补齐矩阵 |
| P5B-GAP-001 | 中 | 活动建议文案中的距离/爬升与 UI 顶部路线事实不一致 | 待核对 | 核对 `_activity_advice_snapshot` 与当前 UI 轨迹是否同源、是否存在旧快照残留或 DB/临时快照口径差异 |

P5A 已修复需要立即修改生产代码的缺陷；仍需桌面端真实点击确认 LLM 输出质量。

---

## 11. 验收结论

结论：P5B 真实点击已出内容，但暂不建议冻结通过。

已通过部分：

- 活动建议自动化契约回归通过。
- P5B 自动化回归复核通过。
- P3 cleanup 静态门禁通过。
- 旧风险预警生产代码与契约旧兼容描述无回潮。
- 活动建议链路扫描符合契约，前端生成建议仍只发送 planning context。
- 发布说明已落档到 `docs/activity_advice_release_notes_p5b.md`。
- 用户手动截图确认「生成建议」已经可返回活动建议内容。
- 本地 FIT/GPX 样例资产已盘点。
- 可重复执行的人工验收矩阵已落档。

未通过 / 未完成部分：

- 完整人工矩阵尚未执行，包括纯 GPX、DB/FIT、短路线、高爬升/无海拔样例。
- 活动建议文案中的距离/爬升与 UI 顶部路线事实存在差异，需确认是否为快照口径差异或旧快照残留。
- 未完成高爬升、无海拔样例标定。
- 阅后即焚生命周期只完成静态/自动化覆盖，未完成 UI 人工点击确认。

下一步建议：

- 暂不进入发布冻结；先核对 route facts 一致性，并补齐纯 GPX / DB-FIT / 短路线 / 高爬升或无海拔样例。
- 如果用户可以提供或确认高爬升、无海拔样例，则直接按本清单执行桌面端人工验收。
- 如果真实输出越界，进入 `P5C 活动建议 Prompt 与 Normalizer 质量闸门`。
- 如果 route facts 质量不足，进入 `P5A-2 活动建议路线事实增强`。
- 人工验收全部通过后，再将状态更新为 `P5B 冻结通过`，并进入 `P6 活动建议发布后观察与反馈收集`。
