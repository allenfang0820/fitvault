# ACS-Next-01 赛事照片上传与 Banner 真实照片模式完成报告

## 本任务范围

本任务完成单张赛事 Banner 照片闭环：

- 为已确认赛事活动选择一张本地图片。
- 将图片复制到应用受控目录 `~/.fitvault/workspace/career_media/race_banner/`。
- 在 ACS 中只保存 `memory/photo/race_banner/...` 安全逻辑引用。
- `get_career_overview.hero_banner` 在有照片时返回 `mode=photo`。
- 前端 Overview Banner 使用后端 `hero_banner.media.image_ref` 渲染照片背景。

## 修改文件

- `career_backend.py`
- `main.py`
- `track.html`
- `docs/js_api_contract.json`
- `docs/脉图运动生涯系统（ACS）开发任务清单.md`
- `tests/test_career_memory_media_api.py`
- `tests/test_career_overview_api_closure.py`
- `tests/test_career_overview_frontend_render.py`
- `tests/test_career_phase9_macos_closure.py`
- `tests/test_career_task_list_status_reconciliation.py`
- `tests/test_career_race_photo_banner_api.py`

## 媒体安全引用方案

- DB 仅保存 `career_memory_items.storage_ref = memory/photo/race_banner/...`。
- API 不返回 `storage_ref`、源文件路径、目标绝对路径、`file_path` 或 `file://`。
- Overview 在受控文件存在时将图片转换为 `data:image/...;base64,...` 供前端渲染。
- 若受控文件不可读，仍保留逻辑引用，不回退为本地路径。
- 只允许 `jpg/jpeg/png/webp`，单文件上限 15MB。

## Overview 行为

- 有赛事照片：`hero_banner.mode = photo`，`media.has_photo = true`。
- 无赛事照片：继续使用 `title_art` 艺术字 fallback。
- 无活动：继续返回稳定 `empty` Banner。

## 前端行为

- Banner 右上角新增“设置照片 / 更换照片”按钮。
- 仅在当前 Banner 绑定已确认赛事活动时可用。
- 点击后调用 `pick_and_save_career_race_photo(activity_id)`。
- 保存成功后重新加载 Overview；保存失败只显示 Banner 局部错误，不阻塞 ACS 页面。
- 赛事 Activity Detail 的概览页在圈速统计下方提供方框内 `+` 入口，使用当前活动详情上下文设置一张 Banner 照片，不要求用户手动填写 `activity_id`。

## 未完成事项

- 未做复杂相册布局。
- 未做多图轮播。
- 未做一次最多 5 张、拖拽排序或首图排序规则。
- 未做缩略图生成。
- 未做媒体删除生命周期。
- 未做 Race Map。
- 未接真实 AI。
- 未执行 macOS 打包产物验证。
- 未执行 Windows 真机或 Windows 打包验证。

## 兼容性说明

本任务完成 macOS 当前代码层验证。路径处理使用 `Path`、受控目录复制和逻辑引用，覆盖中文文件名与空格文件名场景。Windows 真机、Windows 打包后读写权限、pywebview 文件选择器真实表现仍需后续专项验收。

## 验证命令

```bash
python3 -m pytest tests/test_career_memory_media_api.py tests/test_career_overview_api_closure.py tests/test_career_race_photo_banner_api.py tests/test_career_overview_frontend_render.py tests/test_career_phase9_macos_closure.py tests/test_career_task_list_status_reconciliation.py -q
# 42 passed
```

```bash
python3 -m pytest tests/test_career*.py tests/test_track_html_sync_logic.py -q
# 385 passed
```

```bash
PYTHONPYCACHEPREFIX=/private/tmp/codex-pycache python3 -m py_compile career_backend.py main.py
python3 -m json.tool docs/js_api_contract.json >/dev/null
# passed
```

测试中仅出现本机 Python 环境的 `urllib3 / LibreSSL` warning，与本任务无关。

## 下一个建议任务

`ACS-Next-02：Memory Gallery 媒体生命周期闭环`
