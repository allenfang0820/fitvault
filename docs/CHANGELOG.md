# 变更日志

## v0.4.2（2025-05-31）

### 功能新增
- **运动画像模块**：从"生理画像"升级为"运动画像"，新增 10 个生理指标字段（`lactate_threshold_pace`、`pb_1km`、`pb_1mile`、`longest_run_km`、`longest_ride_time`、`cycling_40km_time`、`cycling_80km_time`、`longest_cycle_km`、`longest_swim_distance_m`、`swimming_100m_pb`），支持后端字段别名兼容（`username`/`weight_kg`/`resting_heart_rate`/`hrv`/`vo2_max`）
- **指标分组切换**：运动画像指标按「生理数据」「跑步／徒步」「骑行」「游泳」四组按钮式切换，无刷新抖动
- **运动记录筛选**：个人运动数据页支持按运动类型过滤，使用统一展示类型键修复筛选失效问题
- **轨迹分析工具缓存**：运动记录从 SQLite 缓存加载，不再阻塞式触发 FIT 同步
- **SQLite 缓存软删除**：新增 `file_mtime`/`file_size` 缓存、`deleted_at` 软删除、批量删除接口
- **脏类型自动清理**：GPX 文件名误写入 sport_type 的问题在解析层、入库层、查询层三层防护

### 优化改进
- **两模块数据同源**：轨迹分析工具左侧运动记录与个人运动数据页共用 `_query_activity_list_records` 查询路径
- **加载速度优化**：轨迹分析工具历史列表加载耗时从数秒降至 0.11s（与个人运动数据页 0.04s 的差值 < 500ms）
- **地理编码优化**：轨迹分析工具左侧记录移除 `getCityNameAsync` 异步 HTTP 请求，改用 DB `region` 字段
- **布局紧凑化**：生理画像/运动能力卡片区域高度缩减 15-22%，标签工作区缩减 17%，表格/工具栏紧密优化

### 修复
- 运动类型筛选键不一致（`road_cycling` 等显示类型与原始 `sport_type` 不匹配）已修复
- 运动画像新增字段保存后无法读取的 bug 已修复
- 筛选/分页操作错误触发 FIT 同步的问题已修复
