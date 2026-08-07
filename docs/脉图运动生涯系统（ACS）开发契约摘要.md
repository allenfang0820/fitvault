# 脉图运动生涯系统（ACS）开发契约摘要

> 用途：`ACS-Overview-Highlight-Carousel` 以及后续 ACS Overview 轮播相关任务的门禁摘要。每项任务开始前先刷新本摘要、开发任务清单和交付手册；只有目标、范围或合同严重偏离时，才回到原始契约全文。
>
> 来源：
> - `docs/脉图运动生涯系统（ACS）开发团队交付手册.md`
> - `docs/脉图运动生涯系统（ACS）开发任务清单.md`
> - `docs/js_api_contract.json`
> - `docs/acs_next_01_race_photo_banner_completion_report.md`
> - `docs/acs_next_04_media_thumbnail_safe_preview_completion_report.md`

## 冻结合同

- ACS Overview 的主视觉仍是 `hero_banner`；它优先展示赛事记忆，其次才是普通 Activity 的运动记忆兜底。
- `hero_banner.slides` 是 Banner 的精选投影池，最多 10 条；它和 Timeline 共享同一套活动事件语义，只是展示粒度不同。
- 轮播池可以混合赛事和非赛事代表活动，但必须清晰标注入选原因，不能把普通 Activity 伪装成赛事。
- 赛事类候选优先；非赛事类候选补位。
- Banner 精选排序固定为：已确认 / 高置信赛事优先；有安全照片的赛事优先；PB / 记录突破优先于普通成就；年度最长距离、年度最长时长、年度最高海拔、年度最大爬升优先于普通运动类型代表；首次城市 / 国家作为地点类代表事件补位；同层级按代表性分值和时间倒序兜底。
- 同一 Activity 在 Banner 精选中只能出现一次；Timeline 作为全量投影可保留赛事、PB、成就、里程碑等正式语义节点，但不得脱离同一活动事件规则另起语义。
- 同一 `event_type` 最多 2 条，避免 10 条里只剩一种运动或一种语义。
- 轮播池建议纳入的非赛事代表活动包括：年度最长距离、年度最长时长、年度最高海拔、年度累计爬升里程碑、PB / 记录突破、成就、首次到达新城市 / 新国家、各运动类型代表活动。
- 轮播池中的赛事条目可以展示安全照片或标题艺术字；非赛事条目只能展示标题艺术字或数字卡。
- 所有轮播条目都必须可回跳 Activity Detail，并且前端不得从 DOM、标题、曲线或空值自行推断赛事 / PB / 里程碑事实。
- API 不返回 raw FIT、points、track_json、file_path、storage_ref、本地路径或 SQLite schema。

## 本轮实施边界

- 允许修改：`career_backend.py`、`track.html`、`docs/js_api_contract.json`、本契约摘要、任务清单以及与这次轮播规则直接相关的测试。
- 不允许扩大到：赛事识别算法重构、记录中心、足迹、AI 总结、打包、真机验证、数据库迁移。
- 允许同步时间轴的活动事件语义字段与去重规则，但不改时间轴 UI 形态和入口结构。
- 当前只做规则落地与验证，不做复杂视觉新系统，也不把非赛事条目伪装成赛事卡。

## 关键完成定义

- 赛事轮播与非赛事代表活动轮播同时可用。
- 总数上限 10 条，去重有效。
- 赛事优先、非赛事补位、类型限额、文案区分全部生效。
- Banner 与 Timeline 共享同一套活动事件语义字段，前端只消费后端事实，不自行推断“精彩瞬间”的语义。
- `docs/js_api_contract.json`、任务清单与交付手册保持一致。
