# 轨迹加载性能 PLOAD-02 完成报告

> 日期：2026-08-03
> 任务：canonical 轨迹 bridge 与重复序列化优化
> 状态：Completed

## 1. 实现

- `syncCurrentTrackContextForActivityAdvice()` 改为条件 payload。
- canonical activity 只传 placemarks、filename、weather、activityId 和白名单 `activityAdviceRouteFacts`，不含 points。
- temporary session 继续通过 `payload.points = appState.points` 传递完整轨迹，保留临时 GPX / KML / FIT route facts 聚合。
- 后端 `sync_track_context()` 无需修改：points 本来就是可选字段；DB AI snapshot 仍由 activityId 构建，activity advice 仍优先使用 overview route facts。

## 2. Payload 对比

| activity | 修复前 full context | 修复后 canonical context | 节省 | 降幅 |
| ---: | ---: | ---: | ---: | ---: |
| `127` | `9,239,646 B` | `740 B` | `9,238,906 B` | `99.992%` |
| `907` | `7,782,530 B` | `299 B` | `7,782,231 B` | `99.996%` |

该数据来自真实 activity points 和与前端字段一致的 payload 结构；实际 pywebview bridge 时间仍需打包 UI 分段计时，但重复大 payload 已从合同上消除。

## 3. 合同回归

- canonical activity 无 points 时仍生成 DB AI snapshot 和 overview route facts activity advice snapshot。
- temporary activity 仍保存 `_track_points` 并生成 `temporary_track_context`。
- activity advice 不消费 points、placemarks、历史天气或 DOM 推导事实。
- `docs/js_api_contract.json` 已明确 persistence mode 条件 payload。

## 4. 验证

```text
52 passed
jq empty docs/js_api_contract.json: passed
node --check /tmp/fitvault_track_inline.js: passed
git diff --check: passed
```

adaptive review：未发现 canonical / temporary 路径混淆、事实来源变化或重复回退传输。

## 5. 下一项

进入 PLOAD-03，处理固定 `2.5s` 相机动画的感知等待，并把 ECharts、报告、雷达等非关键工作调度到首屏之后。
