---
name: xhs-publisher
description: 小红书自动化发布工具。基于 Playwright 浏览器自动化，支持扫码登录（持久化会话）、自动发布图文笔记、AI 智能配图。发布时自动根据内容生成配图，优先使用 nano-banana-pro (Gemini 3 Pro Image)，代理不通时降级 qwen-image (通义万相)。当用户提到小红书、发帖、发笔记、XHS、/redbook 时触发。
---

# 小红书自动化发布

基于 Playwright 浏览器自动化的小红书笔记发布工具。扫码登录一次，后续免登录。

## 前置要求

```bash
pip3 install playwright pillow
playwright install chromium
```

## 使用方式

所有命令通过 `scripts/xhs_auto.py` 执行，路径相对于本技能目录。

### 1. 登录（首次需要）

```bash
python3 scripts/xhs_auto.py login
```

- 浏览器打开小红书创作者平台登录页
- 截图保存二维码到 `screenshots/` 目录
- 用小红书 APP 扫码，等待登录成功
- 登录状态持久化到 `browser_data/`，后续无需重复扫码

登录成功后输出 JSON：
```json
{"success": true, "status": "logged_in", "qr_screenshot": "screenshots/qrcode_xxx.png"}
```

**重要**：登录命令必须在非 headless 模式下运行（需要显示浏览器窗口扫码）。将二维码截图发送给用户，让用户扫码。

### 2. 发布笔记

#### 直接指定内容

```bash
python3 scripts/xhs_auto.py publish \
  --title "笔记标题" \
  --content "笔记正文内容" \
  --tags "标签1,标签2,标签3"
```

#### 从 JSON 文件发布

```bash
python3 scripts/xhs_auto.py publish --file content/post.json
```

JSON 格式：
```json
{
  "title": "笔记标题（不超过20字）",
  "content": "笔记正文（不超过1000字）",
  "tags": ["标签1", "标签2"],
  "images": ["path/to/img1.png", "path/to/img2.png"]
}
```

#### 指定自定义图片

```bash
python3 scripts/xhs_auto.py publish \
  --title "标题" \
  --content "正文" \
  --images "img1.png,img2.png"
```

不指定图片时，自动使用 AI 生成配图（优先 Gemini，降级通义万相）。

#### 禁用自动配图

```bash
python3 scripts/xhs_auto.py publish --title "标题" --content "正文" --no-auto-image
```

## ⚠️ 重要约定

### /redbook 触发
当用户消息中包含 `/redbook` 时，自动触发小红书发布流程。

### 默认 AI 配图
发布笔记时如果未指定图片，自动根据标题和正文内容生成 AI 配图：

- **优先**：nano-banana-pro（Gemini 3 Pro Image），通过 `127.0.0.1:7897` 代理访问
- **降级**：qwen-image（通义万相），代理不通或 Gemini 失败时自动切换
- **兜底**：以上都失败时，生成带标题文字的默认封面

配图生成脚本：`scripts/image_gen.py`，也可独立使用：

```bash
python3 scripts/image_gen.py --prompt "图片描述" --output "output.png" --resolution 1K
```

#### 试运行（不实际发布）

```bash
python3 scripts/xhs_auto.py publish --file content/post.json --dry-run
```

#### 无头模式（后台运行）

```bash
python3 scripts/xhs_auto.py publish --title "标题" --content "正文" --headless
```

### 3. 检查登录状态

```bash
python3 scripts/xhs_auto.py status
```

输出：
```json
{"logged_in": true, "browser_data_exists": true, "checked_at": "..."}
```

## 发布流程

1. 启动浏览器（使用持久化上下文，自动恢复登录）
2. 检测登录状态，未登录则提示扫码
3. 导航到 `creator.xiaohongshu.com/publish/publish`
4. 点击「上传图文」TAB
5. 上传封面图片
6. 填写标题（限20字）
7. 填写正文（限1000字）
8. 输入 `#` 触发标签联想，添加标签
9. 点击发布按钮
10. 截图确认，保存发布报告

## 输出文件

- `screenshots/` - 登录二维码、发布前后截图
- `logs/xhs_YYYYMMDD.log` - 运行日志
- `logs/report_*.json` - 发布报告
- `browser_data/` - 持久化浏览器数据（登录凭据）
- `content/` - 内容文件和默认封面

## 限制和注意事项

- **标题**：不超过 20 字
- **正文**：不超过 1000 字
- **图片**：支持 JPG/PNG，建议 3:4 比例（1080×1440）
- **标签**：最多 10 个
- **每日发帖**：建议不超过 10 篇，避免账号风险
- **多设备**：同一账号不允许多个网页端同时登录
- **browser_data/** 包含登录凭据，妥善保管

## 与 OpenClaw 集成

### 定时发布

使用 cron 设置定时发布任务：

```json
{
  "schedule": {"kind": "cron", "expr": "0 8 * * *", "tz": "Asia/Shanghai"},
  "payload": {
    "kind": "agentTurn",
    "message": "发布一篇小红书笔记，主题是今日科技资讯"
  },
  "sessionTarget": "isolated"
}
```

### 对话中使用

- "帮我发一篇小红书，标题是 XXX，内容是 XXX"
- "检查小红书登录状态"
- "登录小红书"

## 故障排查

### 登录失败
```bash
rm -rf browser_data/
python3 scripts/xhs_auto.py login
```

### 发布失败
- 检查 `logs/` 目录下的日志
- 用 `--dry-run` 试运行排查
- 检查图片格式和大小
- 确认标题和正文长度限制

### 浏览器问题
```bash
playwright install chromium
```
