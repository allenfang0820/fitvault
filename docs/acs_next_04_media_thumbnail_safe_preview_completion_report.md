# ACS-Next-04 媒体缩略图与安全预览闭环完成报告

## 完成内容

- 统一后端安全预览转换：受控 `memory/photo/...` 引用仅在文件位于应用受控 `career_media` 目录、类型为 jpg/jpeg/png/webp 且大小合规时转换为 `data:image/...`。
- Activity Detail 赛事照片返回 `thumbnail_url` 与 `preview_url`，均为安全 data URL 或空字符串。
- Overview Banner 的 `hero_banner.media.image_ref` 仅返回安全 data URL；无安全预览时回到 `title_art` fallback。
- Memory Gallery 的 photo item 返回安全 `thumbnail_url`；Memory Gallery 继续只读展示，不提供上传或手填活动入口。
- 前端新增安全图片预览归一化，只有 `data:image/` 才进入 `<img>` 或 Banner 背景。

## 安全边界

- 不向前端/API/AI/Snapshot 返回 `storage_ref`、`file_path`、本地绝对路径、`file://`、raw FIT、points、`track_json`、SQLite schema。
- 后端可以内部读取受控媒体目录文件，但返回值只能是 data URL 或空字符串。
- 非受控路径、绝对路径、缺失文件、越权路径全部稳定降级为空预览。

## 非目标

- 不做复杂相册详情页。
- 不做媒体文件物理删除。
- 不做云同步。
- 不做轨迹截图自动生成。
- 不接入真实 AI Career Insight。
- 不执行 macOS/Windows 打包或真机验证。

## 验证记录

- 新增 `tests/test_career_media_safe_preview_api.py`。
- 新增 `tests/test_career_media_safe_preview_frontend.py`。
- 更新媒体相关 API / 前端测试断言，使其匹配安全 data URL 预览语义。

## 后续建议

下一任务建议进入 `ACS-Next-05：真实数据端到端人工验收准备与验收清单`，用真实活动数据逐项核查 Overview、Activity Detail 照片、Race Map、Memory Gallery、赛事档案、PB、荣誉与时间轴闭环，再考虑 AI 洞察。
