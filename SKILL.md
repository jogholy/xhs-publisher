---
name: xhs-publisher
description: 小红书自动化发布工具。基于 Playwright 浏览器自动化，支持扫码登录（持久化会话）、自动发布图文笔记、AI 智能配图。发布时自动根据内容生成配图，优先使用 nano-banana-pro (Gemini 3 Pro Image)，代理不通时降级 qwen-image (通义万相)。当用户提到小红书、发帖、发笔记、XHS、/redbook 时触发。
---

# 小红书自动化发布

基于 Playwright 浏览器自动化的小红书笔记发布工具。支持 AI 智能生成小红书风格文案（多种风格模板），一键生成+发布。扫码登录一次，后续免登录。

## 前置要求

```bash
pip3 install playwright pillow cryptography
playwright install chromium
```

## 使用方式

所有命令通过 `scripts/xhs_auto.py` 执行，路径相对于本技能目录。

### 0. AI 生成内容（新功能）

#### 列出可用文案风格

```bash
python3 scripts/xhs_auto.py generate --list-styles
```

支持 4 种风格：
- `default` — 通用笔记（标题+正文+标签+互动引导）
- `review` — 测评种草（亮点、槽点、适合人群、购买建议）
- `tutorial` — 干货教程（步骤拆解、避坑指南、收藏引导）
- `daily` — 日常分享（轻松随意、有温度、引发共鸣）

#### 根据主题生成内容

```bash
python3 scripts/xhs_auto.py generate --topic "夏天防晒攻略" --style tutorial
```

可选参数：
- `--style` / `-s`：文案风格（默认 default）
- `--extra` / `-e`：额外指令（如"面向大学生群体"、"突出性价比"）

输出 JSON 包含：`title`、`content`、`tags`、`call_to_action`、`style`、`topic`、`model`

内容自动保存到 `content/gen_*.json`。

#### 一键生成 + 发布

```bash
python3 scripts/xhs_auto.py auto --topic "夏天防晒攻略" --style tutorial
```

自动完成：AI 生成文案 → AI 生成配图 → 登录检查 → 发布笔记。

可选参数：
- `--dry-run`：只生成不发布（预览内容）
- `--headless`：无头模式
- `--no-auto-image`：禁用自动配图
- `--extra`：额外指令

#### 也可独立使用内容生成脚本

```bash
python3 scripts/content_gen.py generate "主题" --style review --save
python3 scripts/content_gen.py styles
```

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

#### 多图发布

小红书笔记通常需要 3-9 张图。通过 `--image-count` 指定自动生成的图片数量：

```bash
# 发布时自动生成 5 张配图（1张封面 + 4张内容图）
python3 scripts/xhs_auto.py publish --title "标题" --content "正文" --image-count 5

# 一键生成+发布，默认 3 张图
python3 scripts/xhs_auto.py auto --topic "夏天防晒攻略" --style tutorial --image-count 5
```

多图生成逻辑：
- 第 1 张：封面图（3:4 竖版，突出标题主题，吸引眼球）
- 第 2-N 张：内容图（3:4 竖版，每张对应正文的一个段落/章节）
- 正文会自动按小标题/段落拆分，每张图的 prompt 基于对应段落内容
- 请求间隔 5 秒，避免触发 API 速率限制
- 部分图片生成失败不影响已成功的图片，会尽量多生成
- `auto` 命令默认 3 张，`publish` 命令默认 1 张

也可以手动指定多张图片：

```bash
python3 scripts/xhs_auto.py publish --title "标题" --content "正文" --images "cover.png,page1.png,page2.png"
```

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

### 4. 删除已发布笔记

批量删除笔记管理页面上的笔记。支持按状态筛选（全部/已发布/审核中/未通过）。

```bash
# 删除全部笔记（会提示确认）
python3 scripts/xhs_auto.py delete --headless

# 跳过确认直接删除
python3 scripts/xhs_auto.py delete --headless --yes

# 只删除已发布的笔记
python3 scripts/xhs_auto.py delete --tab published --headless --yes

# 只删除审核中的笔记
python3 scripts/xhs_auto.py delete --tab review --headless --yes

# 只删除未通过的笔记
python3 scripts/xhs_auto.py delete --tab failed --headless --yes

# 最多删除 5 篇
python3 scripts/xhs_auto.py delete --max 5 --headless --yes
```

参数：
- `--tab`：筛选 `all`/`published`/`review`/`failed`（默认 all）
- `--max`：最多删除数量（默认 100）
- `--yes` / `-y`：跳过确认直接删除
- `--headless`：无头模式

输出 JSON：
```json
{"deleted": 7, "errors": [], "screenshot": "screenshots/after_delete_xxx.png", "tab": "全部笔记"}
```

删除逻辑：hover 笔记卡片显示操作按钮 → 点击删除 → 确认弹窗 → 滚动加载更多 → 循环直到清空。

## ⚠️ AI 内容合规（2026年2月新规）

小红书自 2026年2月12日起严格执行 AI 内容标识要求（依据《人工智能生成合成内容标识办法》）。本工具已自动合规：

1. **正文声明**：`content_gen.py` 自动在正文末尾追加「📝 本文由 AI 辅助创作」
2. **图片水印**：`image_gen.py` 自动在 AI 配图右下角添加「AI生成」水印（半透明黑底白字，高度 ≥ 最短边 5%）
3. **平台声明**：`xhs_auto.py` 发布时自动勾选「笔记含AI合成内容」声明

不合规后果：限流、限制搜索、降低曝光，多次违规封号。

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

## 定时发布

通过 `schedule` 子命令管理定时发布任务，底层使用 OpenClaw cron 调度。

### 添加定时任务

三种调度方式：

```bash
# 每天早上 9 点发布（cron 表达式）
python3 scripts/xhs_auto.py schedule add --topic "每日科技资讯" --cron "0 9 * * *" --name "早间快报"

# 指定时间一次性发布
python3 scripts/xhs_auto.py schedule add --topic "周末好去处" --style daily --at "2026-02-15T18:00:00"

# 每隔 N 分钟发布（测试用）
python3 scripts/xhs_auto.py schedule add --topic "测试主题" --every 60
```

可选参数：
- `--style` / `-s`：文案风格（default/review/tutorial/daily）
- `--extra` / `-e`：额外指令
- `--tz`：时区（默认 Asia/Shanghai）
- `--name`：任务名称

命令输出包含 `cron_job` 对象，需要用 cron tool 的 `add` action 提交给 OpenClaw 完成注册，然后用 `link` 回填 jobId：

```bash
# 回填 OpenClaw 返回的 jobId
python3 scripts/xhs_auto.py schedule link --task-id xhs_xxx --cron-job-id <jobId>
```

### 查看任务列表

```bash
python3 scripts/xhs_auto.py schedule list
```

### 暂停/恢复/删除任务

```bash
python3 scripts/xhs_auto.py schedule disable --task-id xhs_xxx
python3 scripts/xhs_auto.py schedule enable --task-id xhs_xxx
python3 scripts/xhs_auto.py schedule remove --task-id xhs_xxx
```

暂停/恢复/删除后，需同步操作 OpenClaw cron（命令输出会提示对应的 cron_job_id）。

### Agent 操作流程（重要）

当用户要求设置定时发布时，agent 应按以下步骤操作：

1. 调用 `xhs_auto.py schedule add` 创建本地任务，获取 `cron_job` 对象
2. 用 cron tool 的 `add` action 将 `cron_job` 提交给 OpenClaw，获取 `jobId`
3. 调用 `xhs_auto.py schedule link` 回填 `jobId` 到本地记录
4. 暂停/恢复/删除时，同步操作本地记录和 OpenClaw cron

## 热点数据采集

从百度热搜、头条热榜、B站热搜采集实时热点话题，无需 API Key。

### 查看热榜

```bash
# 查看所有热榜（默认 JSON 输出）
python3 scripts/xhs_auto.py trending fetch

# 可读文本格式，每源 Top 10
python3 scripts/xhs_auto.py trending fetch --text --limit 10

# 只看某个源
python3 scripts/xhs_auto.py trending fetch --text --source baidu

# 跳过缓存（默认 5 分钟缓存）
python3 scripts/xhs_auto.py trending fetch --text --no-cache
```

支持的数据源：
- `baidu` — 百度热搜
- `toutiao` — 头条热榜
- `bilibili` — B站热搜

### 提取去重话题列表

```bash
python3 scripts/xhs_auto.py trending topics --limit 10
```

从所有热榜中提取去重后的热门话题，适合用作内容创作灵感。

### 根据热点一键生成内容

```bash
# 选第 4 个热点，用日常分享风格生成
python3 scripts/xhs_auto.py hot --pick 4 --style daily

# 按关键词匹配热点
python3 scripts/xhs_auto.py hot --keyword "旅游" --style tutorial

# 默认取第一个热点
python3 scripts/xhs_auto.py hot
```

可选参数：
- `--pick N`：选择第 N 个热点（从 1 开始）
- `--keyword`：按关键词匹配热点
- `--style`：文案风格（default/review/tutorial/daily）
- `--extra`：额外指令
- `--publish`：生成后直接发布
- `--dry-run`：试运行
- `--image-count`：自动生成图片数量（默认 3）

### 热点 + 生成 + 发布一条龙

```bash
python3 scripts/xhs_auto.py hot --pick 1 --style daily --publish --headless --image-count 3
```

也可独立使用采集脚本：

```bash
python3 scripts/trending.py fetch --limit 5
python3 scripts/trending.py topics --limit 10
python3 scripts/trending.py sources
```

## 笔记互动数据

从创作者中心「内容管理」页抓取每篇笔记的阅读、点赞、收藏、评论、分享数据。

### 抓取互动数据

```bash
# 抓取最近 20 篇笔记的互动数据
python3 scripts/xhs_auto.py engagement fetch --limit 20 --headless

# 查看缓存数据（不启动浏览器）
python3 scripts/xhs_auto.py engagement cached
```

### 生成每日报告

```bash
# 完整报告（含互动数据抓取）
python3 scripts/xhs_auto.py engagement report --headless

# JSON 格式
python3 scripts/xhs_auto.py engagement report --headless --json

# 仅发布统计（不抓取互动数据）
python3 scripts/xhs_auto.py engagement report --no-engagement
```

报告内容包括：
- 今日/累计发布数、成功率
- 热门标签
- 总阅读、点赞、收藏、评论、分享数
- 最佳笔记（按点赞+收藏排名）
- 各笔记明细数据

也可独立使用：

```bash
python3 scripts/engagement.py fetch --limit 20 --headless
python3 scripts/engagement.py report --headless --json
python3 scripts/engagement.py cached
```

## 发布数据统计

基于 `logs/report_*.json` 汇总发布历史、成功率、标签分布等。

### 查看统计

```bash
# 全部统计
python3 scripts/xhs_auto.py stats

# 最近 7 天
python3 scripts/xhs_auto.py stats --days 7

# 指定日期
python3 scripts/xhs_auto.py stats --date 2026-02-12

# JSON 输出
python3 scripts/xhs_auto.py stats --json
```

统计内容包括：
- 总发布数、成功/失败数、成功率
- 平均正文长度
- 每日发布数量
- 热门标签 Top 10
- 最近 5 篇发布记录
- 失败记录及错误原因

也可独立使用：

```bash
python3 scripts/stats.py --days 7 --json
```

## 评论自动互动

通过 Playwright 抓取小红书创作者中心的评论，用 AI 生成个性化回复并自动发送。

### 抓取评论

```bash
python3 scripts/xhs_auto.py comments fetch --limit 20
```

从创作者中心评论管理页抓取未回复的评论，返回 JSON 列表。

### 自动回复评论

```bash
# 试运行（只生成回复，不实际发送）
python3 scripts/xhs_auto.py comments reply --limit 10 --style friendly --dry-run

# 正式回复
python3 scripts/xhs_auto.py comments reply --limit 10 --style friendly

# 无头模式
python3 scripts/xhs_auto.py comments reply --limit 5 --style humorous --headless
```

回复风格：
- `friendly` — 友好亲切，像朋友聊天（默认）
- `professional` — 专业有深度
- `humorous` — 幽默风趣，适当用网络流行语和 emoji
- `brief` — 简短精炼，一两句话

### 回复统计

```bash
python3 scripts/xhs_auto.py comments stats
```

### 安全机制

- 已回复的评论自动跳过（基于 `data/comments.json` 去重）
- 每条回复间隔 3 秒，避免频率过高
- 回复长度限制 10-80 字，保持自然
- 支持 dry-run 预览，确认后再正式回复
- 回复记录最多保留 2000 条，自动清理

也可独立使用：

```bash
python3 scripts/comments.py fetch --limit 10
python3 scripts/comments.py reply --limit 5 --style friendly --dry-run
python3 scripts/comments.py stats
```

## 与 OpenClaw 集成

### 对话中使用

- "帮我发一篇小红书，标题是 XXX，内容是 XXX"
- "帮我写一篇小红书笔记，主题是夏天防晒"
- "用测评风格写一篇关于 XXX 的小红书"
- "一键生成发布一篇关于 XXX 的小红书"
- "每天早上 9 点自动发一篇关于科技资讯的小红书"
- "设置定时发布，周五下午 6 点发一篇周末推荐"
- "查看小红书定时任务"
- "暂停/删除定时任务 xhs_xxx"
- "看看现在有什么热点"
- "根据今天的热搜写一篇小红书"
- "用第 3 个热点生成一篇测评笔记"
- "查看发布统计"
- "看看最近 7 天发了多少篇"
- "自动回复评论"
- "用幽默风格回复最近 5 条评论"
- "先预览评论回复，不要发送"
- "检查小红书登录状态"
- "登录小红书"
- "列出小红书文案风格"

## 安全与稳定性

### 反检测增强

浏览器启动时自动应用反检测措施（`scripts/stealth.py`）：

- UA 随机化：每次启动从 13 个 Chrome 版本 × 3 个平台中随机组合
- Viewport 随机化：从 10 种常见分辨率中随机选取，±微调避免指纹匹配
- WebGL 渲染器伪装：返回常见 NVIDIA 显卡信息
- `navigator.webdriver` 属性隐藏
- `navigator.plugins` / `languages` 伪装
- `chrome.runtime` 补全（Playwright 缺失修复）
- Permissions API 修复
- Playwright 特征清除（`__playwright` 等）
- 启动参数优化（禁用自动化标记、infobars 等）

无需手动配置，`create_browser_context` 已自动集成。

### API Key 加密存储

支持将明文 API Key 迁移到 Fernet 加密文件（`keys.enc`），密钥派生自机器指纹 + 可选密码。

```bash
# 查看加密存储状态
python3 scripts/xhs_auto.py keystore status

# 从 openclaw.json 迁移明文 Key 到加密存储
python3 scripts/xhs_auto.py keystore migrate

# 查看已加密的 Key（脱敏显示）
python3 scripts/xhs_auto.py keystore list

# 手动设置/更新 Key
python3 scripts/xhs_auto.py keystore set --key-name bailian_api_key --key-value "sk-xxx"

# 验证 Key 是否可读
python3 scripts/xhs_auto.py keystore get --key-name bailian_api_key
```

迁移后，内容生成模块会优先从加密文件读取 API Key，fallback 到 openclaw.json 明文配置。

可选：设置环境变量 `XHS_KEY_PASSWORD` 增加密码保护。

### 错误恢复机制

发布流程内置自动重试和错误恢复（`scripts/recovery.py`）：

- 页面导航：最多 3 次重试，失败时自动刷新
- 发布按钮点击：最多 3 次重试，每次间隔递增
- 页面健康检查：发布前自动检测页面状态，异常时尝试恢复
- 错误现场截图：每次失败自动保存截图到 `screenshots/`，便于排查
- 通用重试装饰器：`@retry(max_retries=3, delay=5, backoff=2)` 可用于任意函数

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
