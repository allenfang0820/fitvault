# 活动建议 P5B 发布说明

> 状态：真实点击已出内容 / 待补齐矩阵与 route facts 一致性核对
> 日期：2026-06-12
> 范围：轨迹报告「活动建议」P0-P5A 后的验收冻结记录

---

## 发布范围

本轮发布范围是轨迹报告侧栏「活动建议」功能：

- 用「活动建议」替代旧「风险预警」语义。
- 用户可选填写活动类型和计划活动时间。
- 点击「生成建议」后，通过 `__REPORT_ACTIVITY_ADVICE__` 调用大模型。
- 后端向 LLM 提供活动建议专用 route facts 白名单和用户显式 planning context。
- 输出补给建议、天气检查、装备建议、体力安排四类内容。

KML 不作为本次版本目标。

---

## 用户可见变化

- 轨迹报告中展示「活动建议」卡片，而不是「风险预警」。
- 「生成建议」按钮会生成一次性的路线准备建议。
- 活动类型和计划活动时间为可选输入，默认不自动填充。
- 未填写计划活动时间时，天气部分只应提供出发前检查清单或说明信息不足。
- GPX 纯路线也可以基于距离、爬升、海拔、起点等路线事实生成建议。

---

## 数据与 AI 输入边界

活动建议只允许消费：

- `_activity_advice_snapshot` 中的路线事实白名单。
- 用户显式填写的 `user_activity_type`。
- 用户显式填写的 `planned_start_time`。

活动建议禁止消费：

- 全量 `points[]`、`placemarks[]`。
- FIT / GPX 历史 `start_time`、`start_time_utc`、点列 `time/timestamp`。
- 历史天气、`_track_weather`、`weather_json`、`weather_context`。
- `shadow_diff`、`diff`、原始 records。
- DOM 文本、UI fallback、前端拼接 prompt。

活动建议结果不写 DB、不写 `localStorage` / `sessionStorage`、不进入 `ai_snapshots`，也不污染普通 AI 教练聊天会话。

---

## 已移除 / 不再支持

- 旧「风险预警」生产链路已删除。
- 不再支持 `__REPORT_RISK_ASSESSMENT__`。
- 不再输出 `risk_assessment`。
- 不再使用旧风险预警 UI、旧风险等级语义或旧兼容描述。

---

## 非目标范围

本轮不做：

- KML 活动建议验收。
- 天气 API 接入或真实天气预测。
- 医学建议、安全保证或危险等级判断。
- 路线事实算法增强。
- UI 重新设计。
- 活动建议持久化。

---

## 验收结果

自动化与静态门禁结果：

| 项目 | 结果 |
|---|---|
| 活动建议自动化测试 | 通过，32 tests OK |
| 响应 envelope 契约测试 | 通过，25 tests OK |
| `docs/js_api_contract.json` JSON 校验 | 通过 |
| `main.py` / `llm_backend.py` 编译 | 通过 |
| 复盘关联 E2E 测试 | 通过，42 passed |
| 复盘 AI preflight 测试 | 通过，6 tests OK |
| 旧风险预警生产链路扫描 | 通过，无匹配 |
| `track.html` 内联脚本解析 | 通过，`parsed scripts: 5` |

人工验收结果：

- 当前执行环境中 `python3 main.py` 可启动 pywebview 进程和文件监听。
- `http://127.0.0.1:27917/track.html` 外部访问返回 `ERR_CONNECTION_REFUSED` / connection refused。
- 用户手动测试补充确认：pywebview 页面 `127.0.0.1:47778/track.html` 可用，点击「生成建议」后已经能看到活动建议内容。
- 截图显示用户显式选择「登山」，计划活动时间为 `2026/12/01 17:03`。
- 截图可见输出包含补给建议、天气检查、装备建议，并引用高海拔、冬季傍晚、路线距离/爬升/最高海拔等准备语境。
- 截图未见旧「风险预警」文案，未见引用 FIT/GPX 历史开始时间。

因此“真实点击完全无输出”的阻塞已解除。但截图中 UI 顶部显示 `8.34km / 爬升896m / 最高5337m`，AI 文案可见 `全程10.06km / 累计爬升1203m / 最高海拔5337m`，距离和爬升存在不一致；加上完整矩阵尚未覆盖，本轮暂不建议给出 P5B 冻结通过。

---

## 已知限制

- P5B 真实点击已能生成内容，但 route facts 一致性仍待核对。
- 当前未完成截图路线中 UI 顶部事实与 AI 文案事实差异的根因确认。
- 纯 GPX、DB/FIT、高爬升、短路线的桌面端真实输出尚未逐项验收。
- 高爬升和无海拔固定样例仍需进一步标定。
- 当前环境提示 `urllib3` 使用 LibreSSL 2.8.3，不影响本轮测试通过。
- `tests/test_response_envelope_contract.py` 存在既有 ResourceWarning，不影响本轮测试通过。

---

## 回滚 / 降级策略

如果桌面端真实验收发现阻塞级问题：

- 保留「活动建议」UI，但可在发布前暂缓开放真实 LLM 生成入口。
- 后端继续返回 `{ ok, activity_advice }` 空态结构，避免前端崩溃。
- 不恢复旧「风险预警」命名、旧 sentinel 或旧 `risk_assessment` 输出。
- 根据问题类型进入 `P5A-2` 或 `P5C` 修复。

---

## 后续建议

优先级建议：

1. 优先核对截图中 UI 顶部 `8.34km/896m/5337m` 与 AI 文案 `10.06km/1203m/5337m` 的 route facts 来源差异。
2. 覆盖纯 GPX、DB/FIT、短路线、高爬升路线的真实输出。
3. 如果确认 route facts 质量或同源性不足，进入 `P5A-2 活动建议路线事实增强`。
4. 如果 LLM 输出越界，进入 `P5C 活动建议 Prompt 与 Normalizer 质量闸门`。
5. 全部通过后，再进入 `P6 活动建议发布后观察与反馈收集`。
