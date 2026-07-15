# RCV2-26 工程级执行提示词：游泳正式纪录、Catalog、API 与测试闭环

## 目标

完成泳池/公开水域独立的 Catalog、候选、历史/API ViewModel 和安全测试闭环。

## 契约边界

- pool validation-required，不进入 active。
- open-water candidate-only，不进入 active。
- SWOLF 不成为正式纪录。
- 未知泳姿不自动进入 freestyle PB。
