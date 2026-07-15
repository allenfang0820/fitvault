# RCV2-02 工程级执行提示词

任务：Golden fixtures 与算法可行性样本冻结

目标：建立可复算、脱敏、最小但覆盖关键边界的 Records Center V2 golden fixtures，让后续骑行、徒步、游泳、公开水域和越野 Resolver 在真实泳池/越野样本缺失时仍有稳定测试输入。

输入摘要：

- `RCV2-01` 确认真实库普通骑行 94 条，其中 67 条有功率流；徒步 7 条、登山 5 条、步行 38 条；游泳 2 条且均为公开水域；越野跑 0 条。
- 当前没有真实泳池样本，也没有真实越野样本。
- 当前没有独立 canonical `pool_length` Activity 字段，且旧 resolver 有 25m fallback；V2 正式泳池纪录不得使用 fallback。
- 当前 `duration_sec` 主要来自 FIT `total_timer_time`，elapsed 语义需继续质量标记。

前置依赖：`RCV2-01`。

文件范围：

- 可写：`tests/fixtures/records_center_v2/golden_manifest.json`、`tests/test_records_center_v2_golden_fixtures.py`、本提示词、完成报告、滚动摘要、V2 任务清单。
- 禁止：真实库、业务 Resolver、API、前端、打包产物。

冻结契约：

- Fixtures 不得来自未经脱敏的真实轨迹。
- Fixtures 不得包含本地路径、真实文件名、真实坐标、设备序列号、个人资料、体重历史或账号信息。
- Golden output 是算法实现的验收输入，不得反向改变 V2 产品规则。
- 真实泳池和越野缺样本时，fixture 全绿也不能把 Catalog 标为真实数据 Verified。

实施步骤：

1. 创建 manifest，声明版本、更新流程、敏感字段黑名单和 case 列表。
2. 覆盖骑行功率：0W、缺失值、非 1Hz、长断点、暂停、尖峰。
3. 覆盖徒步海拔：GPS 尖峰、连续爬升、断点和平坡容差。
4. 覆盖泳池：25m/50m、连续 Length、休息中断、泳姿 unknown、pool length 缺失。
5. 覆盖公开水域：750m `±5%` 边界、GPS 跳点/手动距离候选。
6. 覆盖越野路线：同向、反向、低重合、起终点/长度/覆盖率/走廊默认阈值。
7. 添加 schema 和敏感字段扫描测试。
8. 更新完成报告、滚动摘要和任务状态。

非目标：

- 不实现算法。
- 不生成真实 DB dry-run。
- 不开放任何 Catalog。

验证：

```bash
.venv312/bin/python -m pytest tests/test_records_center_v2_golden_fixtures.py -q
.venv312/bin/python -m json.tool tests/fixtures/records_center_v2/golden_manifest.json >/dev/null
```

完成定义：

- 后续 Resolver 任务可直接读取 manifest，获得确定输入、预期证据、不适用原因和 candidate-only 标记。
