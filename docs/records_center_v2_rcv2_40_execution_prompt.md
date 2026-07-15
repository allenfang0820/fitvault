# RCV2-40 工程级执行提示词：真实数据备份、staging dry-run 与人工复核

## 任务目标

在不写真实库的前提下，对当前真实数据做备份、staging 副本 dry-run 和人工复核摘要，形成 RCV2-41 用户决策依据。

## 输入摘要

- 当前任务：`RCV2-40 真实数据备份、staging dry-run 与人工复核`。
- 前置：`RCV2-08` 发布/真实数据门禁已冻结，`RCV2-39` 自动化测试矩阵已全绿。
- 用户明确要求：候选先保持候选，不写真实库；暂时不要打包。

## 冻结契约

- 不得对真实库执行 schema apply、records rebuild apply 或 candidate confirm/reject。
- 只允许读取真实库、复制备份/副本、在 staging 副本执行 schema ensure / plan / dry-run。
- 真实库 dry-run 前后必须验证关键计数、mtime 或 hash 不变。
- 报告不得包含 raw FIT、轨迹、路径、设备标识、体重详情或 candidate evidence。
- 结论只能给 RCV2-41 决策建议，不自动改变 Catalog 可用性或真实数据状态。

## 文件范围

- 生成备份/副本：`docs/records_center_v2_real_data/rcv2_40/`
- 新增完成报告：`docs/records_center_v2_rcv2_40_completion_report.md`
- 更新任务清单与滚动摘要。

## 非目标

- 不修改真实库。
- 不确认或拒绝候选。
- 不修改 Resolver 规则。
- 不打包。

## 实施步骤

1. 读取当前 `profile_backend.DB_PATH` 与源库基础信息。
2. 计算源库 hash、mtime、核心表计数。
3. 复制源库到 backup 与 staging，并计算 hash 验证一致。
4. 在 staging 副本上执行 `ensure_career_schema()` 和 V2 migration/rebuild dry-run。
5. 输出按 sport/family/reason/cache/route/candidate 的汇总。
6. 对骑行、徒步、公开水域、泳池、越野做只读样本复核。
7. 再次计算源库 hash、mtime、核心表计数，证明真实库未变化。
8. 写完成报告，明确 RCV2-41 需要用户决策的事项。

## 验证命令

```bash
.venv312/bin/python -m py_compile career_backend.py main.py
.venv312/bin/python - <<'PY'
# RCV2-40 read-only source audit + staging dry-run script
PY
```

## 完成定义

- 源库前后 hash/mtime/关键计数不变。
- 备份和 staging 副本存在且初始 hash 与源库一致。
- staging dry-run 完成且报告可读。
- 完成报告写入。
- 任务清单标记 `RCV2-40 Done`、`RCV2-41 In Progress`。
