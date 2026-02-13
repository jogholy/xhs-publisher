#!/usr/bin/env python3
"""
小红书自动化发布工具
基于 Playwright 浏览器自动化，支持扫码登录、持久化会话、自动发帖
"""

import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime
from pathlib import Path

# 配置日志
LOG_DIR = Path(__file__).parent.parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            LOG_DIR / f'xhs_{datetime.now():%Y%m%d}.log',
            encoding='utf-8'
        )
    ]
)
log = logging.getLogger(__name__)

# 路径常量
SKILL_DIR = Path(__file__).parent.parent
BROWSER_DATA = SKILL_DIR / 'browser_data'
CONTENT_DIR = SKILL_DIR / 'content'
SCREENSHOTS_DIR = SKILL_DIR / 'screenshots'

for d in [BROWSER_DATA, CONTENT_DIR, SCREENSHOTS_DIR]:
    d.mkdir(exist_ok=True)

# 小红书 URL
XHS_HOME = 'https://www.xiaohongshu.com'
XHS_CREATOR = 'https://creator.xiaohongshu.com'
XHS_PUBLISH = 'https://creator.xiaohongshu.com/publish/publish'
XHS_LOGIN = 'https://creator.xiaohongshu.com/login'


def create_browser_context(playwright, headless=False):
    """创建持久化浏览器上下文（含反检测）"""
    sys.path.insert(0, str(Path(__file__).parent))
    from stealth import random_user_agent, random_viewport, get_stealth_args, get_stealth_ignore_args, apply_stealth

    ua = random_user_agent()
    vp = random_viewport()
    log.info(f'浏览器指纹: UA={ua[:50]}... viewport={vp["width"]}x{vp["height"]}')

    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(BROWSER_DATA),
        headless=headless,
        viewport=vp,
        user_agent=ua,
        locale='zh-CN',
        timezone_id='Asia/Shanghai',
        args=get_stealth_args(),
        ignore_default_args=get_stealth_ignore_args(),
    )
    apply_stealth(context)
    return context


def check_login(page, timeout=5000):
    """检查是否已登录"""
    try:
        page.goto(XHS_CREATOR, wait_until='domcontentloaded', timeout=15000)
        time.sleep(2)

        # 如果跳转到了登录页，说明未登录
        if '/login' in page.url:
            return False

        # 尝试检测页面上的用户信息元素
        try:
            page.wait_for_selector('.user, .creator-header, .sidebar', timeout=timeout)
            return True
        except Exception:
            # 没跳转到登录页，也可能已登录
            return '/login' not in page.url

    except Exception as e:
        log.warning(f'检查登录状态时出错: {e}')
        return False


def do_login(page, timeout=300):
    """
    执行扫码登录
    返回截图路径（二维码截图），用户需要用小红书 APP 扫码
    """
    log.info('开始登录流程...')
    page.goto(XHS_LOGIN, wait_until='domcontentloaded', timeout=15000)
    time.sleep(5)

    # 点击左上角二维码小图标，切换到扫码登录模式
    # 小红书创作者平台默认显示短信登录，需要点击二维码图标切换
    try:
        qr_icon = page.locator('img.css-wemwzq').first
        if qr_icon.is_visible():
            qr_icon.click()
            log.info('已点击二维码图标，切换到扫码登录模式')
            time.sleep(3)
        else:
            log.warning('未找到二维码图标，尝试备用方式')
            # 备用：尝试点击任何小的二维码图片
            small_imgs = page.locator('.login-box-container img')
            for i in range(small_imgs.count()):
                img = small_imgs.nth(i)
                box = img.bounding_box()
                if box and box['width'] < 100 and box['height'] < 100:
                    img.click()
                    log.info('已点击备用二维码图标')
                    time.sleep(3)
                    break
    except Exception as e:
        log.warning(f'切换扫码模式失败: {e}')

    # 截取扫码登录页面的二维码区域
    qr_screenshot = SCREENSHOTS_DIR / f'qrcode_{datetime.now():%Y%m%d_%H%M%S}.png'
    # 尝试只截取二维码图片区域
    try:
        qr_img = page.locator('img.css-1lhmg90').first
        if qr_img.is_visible():
            qr_img.screenshot(path=str(qr_screenshot))
            log.info(f'二维码截图已保存（元素截图）: {qr_screenshot}')
        else:
            page.screenshot(path=str(qr_screenshot), full_page=False)
            log.info(f'二维码截图已保存（全页截图）: {qr_screenshot}')
    except Exception:
        page.screenshot(path=str(qr_screenshot), full_page=False)
        log.info(f'二维码截图已保存（全页截图）: {qr_screenshot}')

    # 等待登录成功
    log.info(f'请用小红书 APP 扫描二维码登录（{timeout}秒超时）...')
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(3)
        current_url = page.url
        if '/login' not in current_url:
            log.info('登录成功！')
            success_shot = SCREENSHOTS_DIR / f'login_success_{datetime.now():%Y%m%d_%H%M%S}.png'
            page.screenshot(path=str(success_shot))
            return str(qr_screenshot)

    raise TimeoutError(f'登录超时（{timeout}秒），请重试')


def publish_note(page, title, content, tags=None, images=None, dry_run=False, auto_image=True, image_count=1, overflow_text=''):
    """
    发布小红书笔记（含错误恢复）

    Args:
        page: Playwright page 对象
        title: 笔记标题（不超过20字）
        content: 笔记正文（不超过1000字）
        tags: 标签列表（可选）
        images: 图片路径列表（可选，不传则自动生成配图）
        dry_run: 试运行，不实际点击发布
        auto_image: 没有图片时是否自动用 AI 生成配图（默认 True）
        image_count: 自动生成图片数量（1-9，默认 1，仅在 auto_image 且无 images 时生效）
        overflow_text: 溢出文本（超过编辑器限制的部分，将生成文字排版图片）
    """
    sys.path.insert(0, str(Path(__file__).parent))
    from recovery import safe_navigate, save_error_snapshot, check_page_health, recover_page

    log.info(f'开始发布笔记: {title}')

    # 1. 导航到发布页（带重试）
    try:
        safe_navigate(page, XHS_PUBLISH, timeout=20000, retries=3)
    except Exception as e:
        log.error(f'导航到发布页失败: {e}')
        shot = save_error_snapshot(page, 'nav_publish_fail')
        _save_report(title, content, tags, False, f'导航失败: {e}')
        return {'success': False, 'error': f'导航到发布页失败: {e}', 'screenshot': shot}
    time.sleep(5)

    # 2. 用 JS 点击「上传图文」TAB（避免视口外点击失败）
    try:
        result = page.evaluate('''() => {
            const all = document.querySelectorAll('*');
            for (const el of all) {
                if (el.children.length === 0 && el.textContent.trim() === '上传图文') {
                    el.click();
                    return true;
                }
            }
            return false;
        }''')
        if result:
            log.info('已点击上传图文 TAB')
        else:
            log.info('未找到上传图文 TAB，可能已在图文模式')
        time.sleep(3)
    except Exception as e:
        log.warning(f'点击上传图文 TAB 失败: {e}')

    # 3. 上传图片（无图片时自动 AI 生成配图）
    image_paths = images or []
    if not image_paths and auto_image:
        if image_count > 1:
            log.info(f'未提供图片，自动生成 {image_count} 张 AI 配图...')
            generated = _auto_generate_multi_images(title, content, count=image_count)
            if generated:
                image_paths = generated
                log.info(f'多图生成完成: {len(generated)} 张')
            else:
                log.warning('多图生成全部失败，尝试单张...')
                single = _auto_generate_image(title, content)
                if single:
                    image_paths = [single]
        else:
            log.info('未提供图片，自动生成 AI 配图...')
            generated = _auto_generate_image(title, content)
            if generated:
                image_paths = [generated]
                log.info(f'AI 配图生成成功: {generated}')
            else:
                log.warning('AI 配图生成失败，使用默认封面')

        if not image_paths:
            default_cover = CONTENT_DIR / 'default_cover.png'
            if not default_cover.exists():
                _generate_default_cover(default_cover, title)
            image_paths = [str(default_cover)]
    elif not image_paths:
        default_cover = CONTENT_DIR / 'default_cover.png'
        if not default_cover.exists():
            _generate_default_cover(default_cover, title)
        image_paths = [str(default_cover)]

    # 溢出文本 → 文字排版图片（追加到配图后面）
    if overflow_text and overflow_text.strip():
        try:
            from image_gen import render_text_pages
            # 超长模式：封面1张 + 文字页最多8张
            max_text_pages = 9 - min(len(image_paths), 1)  # 至少保留1张封面
            text_pages = render_text_pages(
                overflow_text, CONTENT_DIR, prefix='text_page',
                title=title, max_pages=max_text_pages,
            )
            if text_pages:
                # 只保留1张AI封面，剩下全给文字页
                image_paths = image_paths[:1]
                image_paths.extend(text_pages)
                log.info(f'全文转图片: 封面1张 + 文字{len(text_pages)}页，共{len(image_paths)}张')
        except Exception as e:
            log.warning(f'溢出文本图片生成失败（不影响发布）: {e}')

    try:
        upload_input = page.locator('input[type="file"]').first
        upload_input.set_input_files(image_paths)
        log.info(f'已上传 {len(image_paths)} 张图片')
        # 多图上传需要更长等待时间
        wait_sec = max(8, len(image_paths) * 4)
        time.sleep(wait_sec)
    except Exception as e:
        log.warning(f'图片上传失败: {e}')

    # 4. 填写标题
    try:
        title_input = page.locator('input[placeholder*="标题"]').first
        title_input.click()
        title_input.fill(title[:20])
        log.info(f'标题已填写: {title[:20]}')
        time.sleep(0.5)
    except Exception as e:
        log.error(f'标题填写失败: {e}')

    # 5. 填写正文（tiptap ProseMirror 编辑器）
    try:
        body_editor = page.locator('div.ProseMirror[contenteditable="true"]').first
        if not body_editor.is_visible():
            body_editor = page.locator('[contenteditable="true"]').first
        body_editor.click()
        body_editor.type(content[:1000], delay=20)
        log.info(f'正文已填写（{len(content[:1000])}字）')
        time.sleep(0.5)
    except Exception as e:
        log.error(f'正文填写失败: {e}')

    # 6. 添加标签（通过话题按钮）
    if tags:
        _add_tags(page, tags)

    # 6.5 勾选「笔记含AI合成内容」声明（合规要求）
    try:
        _check_ai_declaration(page)
    except Exception as e:
        log.warning(f'AI声明勾选失败（不影响发布）: {e}')

    # 截图记录
    pre_publish_shot = SCREENSHOTS_DIR / f'pre_publish_{datetime.now():%Y%m%d_%H%M%S}.png'
    page.screenshot(path=str(pre_publish_shot), full_page=True)
    log.info(f'发布前截图: {pre_publish_shot}')

    # 7. 点击发布
    if dry_run:
        log.info('[DRY RUN] 试运行模式，跳过发布')
        return {
            'success': True,
            'dry_run': True,
            'title': title,
            'screenshot': str(pre_publish_shot)
        }

    # 发布（带重试）
    max_publish_retries = 3
    for attempt in range(1, max_publish_retries + 1):
        try:
            # 检查页面健康
            health = check_page_health(page)
            if not health['ok']:
                log.warning(f'发布前页面异常: {health.get("error")}，尝试恢复...')
                if not recover_page(page, XHS_PUBLISH):
                    raise RuntimeError('页面恢复失败')

            publish_btn = page.locator('button:has-text("发布")').last
            publish_btn.wait_for(state='visible', timeout=5000)
            publish_btn.click()
            log.info('已点击发布按钮')
            time.sleep(5)

            # 验证发布是否真的成功
            publish_success = False
            error_msg = None

            # 检查1: 页面是否跳转离开发布页（成功发布后通常跳转到笔记管理）
            current_url = page.url
            if '/publish/publish' not in current_url:
                publish_success = True
                log.info(f'发布成功（页面已跳转: {current_url}）')

            # 检查2: 页面上是否出现"发布成功"提示
            if not publish_success:
                success_loc = page.get_by_text('发布成功', exact=False)
                if success_loc.count() > 0:
                    publish_success = True
                    log.info('发布成功（检测到成功提示）')

            # 检查3: 检测错误提示（弹窗/toast）
            if not publish_success:
                for err_text in ['发布失败', '内容违规', '请修改', '超出限制', '字数超', '审核', '请检查']:
                    err_loc = page.get_by_text(err_text, exact=False)
                    for i in range(err_loc.count()):
                        if err_loc.nth(i).is_visible():
                            error_msg = f'页面提示: {err_loc.nth(i).text_content().strip()[:100]}'
                            log.error(f'发布失败 — {error_msg}')
                            break
                    if error_msg:
                        break

            # 检查4: 再等几秒看是否跳转（有些情况跳转较慢）
            if not publish_success and not error_msg:
                time.sleep(5)
                current_url = page.url
                if '/publish/publish' not in current_url:
                    publish_success = True
                    log.info(f'发布成功（延迟跳转: {current_url}）')

            # 发布后截图
            post_shot = SCREENSHOTS_DIR / f'published_{datetime.now():%Y%m%d_%H%M%S}.png'
            page.screenshot(path=str(post_shot))

            if publish_success:
                log.info(f'发布完成！截图: {post_shot}')
                _save_report(title, content, tags, True)
                return {
                    'success': True,
                    'title': title,
                    'screenshot': str(post_shot)
                }
            elif error_msg:
                raise RuntimeError(error_msg)
            else:
                # 没跳转也没报错，标记为不确定
                log.warning('发布状态不确定（页面未跳转，未检测到成功/失败提示）')
                _save_report(title, content, tags, False, '发布状态不确定')
                return {
                    'success': False,
                    'error': '发布状态不确定，页面未跳转',
                    'screenshot': str(post_shot),
                    'uncertain': True,
                }

        except Exception as e:
            log.warning(f'发布尝试 {attempt}/{max_publish_retries} 失败: {e}')
            save_error_snapshot(page, f'publish_retry{attempt}')
            if attempt < max_publish_retries:
                time.sleep(5)
            else:
                log.error(f'发布在 {max_publish_retries} 次尝试后仍失败: {e}')
                err_shot = save_error_snapshot(page, 'publish_final_fail')
                _save_report(title, content, tags, False, str(e))
                return {
                    'success': False,
                    'error': str(e),
                    'screenshot': err_shot,
                    'retries': max_publish_retries,
                }


def _check_ai_declaration(page):
    """勾选「笔记含AI合成内容」声明（小红书2026年2月新规合规要求）"""
    import time as _time

    # 先滚动到底部确保"内容设置"区域可见
    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    _time.sleep(1)

    # 点击「添加内容类型声明」展开下拉（用 locator + get_by_text）
    decl_loc = page.get_by_text('添加内容类型声明', exact=True)
    if decl_loc.count() == 0:
        # 备选：模糊匹配
        decl_loc = page.get_by_text('内容类型声明')
    if decl_loc.count() == 0:
        log.warning('未找到「添加内容类型声明」按钮')
        return False

    decl_loc.first.click()
    _time.sleep(1.5)

    # 点击「笔记含AI合成内容」
    ai_loc = page.get_by_text('笔记含AI合成内容', exact=True)
    if ai_loc.count() == 0:
        ai_loc = page.get_by_text('AI合成内容')
    if ai_loc.count() == 0:
        log.warning('未找到「笔记含AI合成内容」选项')
        return False

    ai_loc.first.click()
    _time.sleep(1)
    log.info('已勾选「笔记含AI合成内容」声明')
    return True


def _add_tags(page, tags):
    """添加标签 - 通过话题按钮或在正文中输入 #"""
    added = 0
    for tag in tags[:10]:  # 最多10个标签
        try:
            # 在正文编辑器中输入 # 触发标签联想
            editor = page.locator('div.ProseMirror[contenteditable="true"]').first
            if not editor.is_visible():
                editor = page.locator('[contenteditable="true"]').first
            editor.click()
            editor.type(f' #{tag}', delay=80)
            time.sleep(1.5)

            # 尝试从联想列表中选择第一个匹配项
            try:
                suggestion = page.locator(f'[class*="topic"] >> text="{tag}"').first
                if suggestion.is_visible(timeout=2000):
                    suggestion.click()
                    added += 1
                    time.sleep(0.5)
                    continue
            except Exception:
                pass

            # 备用：尝试点击任何弹出的联想列表项
            try:
                popup_item = page.locator('[class*="suggest"] li, [class*="topic-list"] div, [class*="hash-tag"] div').first
                if popup_item.is_visible(timeout=1000):
                    popup_item.click()
                    added += 1
                    time.sleep(0.5)
                    continue
            except Exception:
                pass

            # 联想没匹配到，标签文本已输入
            added += 1

        except Exception as e:
            log.warning(f'添加标签 "{tag}" 失败: {e}')

    log.info(f'已添加 {added} 个标签')


def _auto_generate_image(title, content):
    """
    根据笔记标题和正文自动生成 AI 配图
    优先 nano-banana-pro，降级 qwen-image
    返回图片路径或 None
    """
    try:
        # 导入同目录下的 image_gen 模块
        sys.path.insert(0, str(Path(__file__).parent))
        from image_gen import generate_image

        # 用标题+正文前100字构造图片 prompt
        context = content[:100] if content else ''
        prompt = (
            f"为小红书笔记生成一张精美配图。"
            f"笔记标题：{title}。"
            f"内容摘要：{context}。"
            f"要求：高质量、吸引眼球、适合社交媒体、色彩鲜明、3:4竖版构图"
        )

        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = str(CONTENT_DIR / f'ai_cover_{ts}.png')

        result = generate_image(prompt, output_path, resolution='1K')
        if result['success']:
            log.info(f'AI 配图生成成功 [引擎: {result["engine"]}]: {output_path}')
            return output_path
        else:
            log.warning(f'AI 配图生成失败: {result.get("error", "未知")}')
            return None

    except Exception as e:
        log.warning(f'AI 配图生成异常: {e}')
        return None


def _split_content_sections(content):
    """将正文按段落/小标题拆分成若干段，用于生成分段配图"""
    import re
    sections = []
    current = []
    for line in content.split('\n'):
        stripped = line.strip()
        # 遇到小标题时切段
        if re.match(r'^[【\[#✅❌🔥💡📌🎯🏷️📝]', stripped) and current:
            text = '\n'.join(current).strip()
            if len(text) > 15:
                sections.append(text)
            current = []
        if stripped:
            current.append(stripped)
    if current:
        text = '\n'.join(current).strip()
        if len(text) > 15:
            sections.append(text)
    return sections if sections else [content]


def _auto_generate_multi_images(title, content, count=3):
    """
    根据笔记标题和正文自动生成多张 AI 配图。
    第 1 张为封面（3:4 竖版），后续为内容图（3:4 竖版）。
    每张图的 prompt 基于对应的内容段落，确保图文匹配。

    Args:
        title: 笔记标题
        content: 笔记正文
        count: 生成图片数量（1-9，默认 3）

    Returns:
        list[str]: 生成成功的图片路径列表（可能少于 count）
    """
    count = max(1, min(9, count))
    sys.path.insert(0, str(Path(__file__).parent))
    from image_gen import generate_image

    # 拆分内容段落
    sections = _split_content_sections(content)

    # 构建每张图的 prompt
    prompts = []

    # 封面：突出标题，吸引眼球
    prompts.append(
        f"为小红书笔记生成一张精美封面图。"
        f"标题：{title}。"
        f"要求：高质量、吸引眼球、色彩鲜明、3:4竖版构图、适合社交媒体封面、"
        f"画面干净有设计感、不要包含文字"
    )

    # 内容图：每张对应一个段落
    for i in range(1, count):
        if i - 1 < len(sections):
            section = sections[i - 1][:150]
        else:
            # 段落不够时，用标题+序号生成变体
            section = f"{title} 第{i}部分"
        prompts.append(
            f"为小红书笔记生成一张内容配图（第{i+1}张）。"
            f"笔记标题：{title}。"
            f"本页内容：{section}。"
            f"要求：高质量、3:4竖版构图、与内容相关、风格统一、不要包含文字"
        )

    # 逐张生成
    generated = []
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    for idx, prompt in enumerate(prompts):
        suffix = 'cover' if idx == 0 else f'page{idx}'
        output_path = str(CONTENT_DIR / f'ai_{suffix}_{ts}.png')
        log.info(f'生成第 {idx+1}/{count} 张图片...')
        try:
            result = generate_image(prompt, output_path, resolution='1K')
            if result['success']:
                generated.append(output_path)
                log.info(f'  ✓ 第 {idx+1} 张成功 [{result["engine"]}]: {output_path}')
            else:
                log.warning(f'  ✗ 第 {idx+1} 张失败: {result.get("error", "未知")}')
        except Exception as e:
            log.warning(f'  ✗ 第 {idx+1} 张异常: {e}')
        # 请求间隔，避免触发 API 速率限制
        if idx < len(prompts) - 1:
            time.sleep(5)

    log.info(f'多图生成完成: {len(generated)}/{count} 张成功')
    return generated


def _generate_default_cover(path, title=''):
    """生成默认封面图"""
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new('RGB', (1080, 1440), color=(255, 240, 245))
        draw = ImageDraw.Draw(img)

        # 尝试加载中文字体
        font = None
        font_paths = [
            '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
            '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
            '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
            '/System/Library/Fonts/PingFang.ttc',
        ]
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    font = ImageFont.truetype(fp, 48)
                    break
                except Exception:
                    continue

        if font is None:
            font = ImageFont.load_default()

        # 绘制标题文字
        if title:
            text = title[:15]
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            x = (1080 - tw) // 2
            draw.text((x, 600), text, fill=(50, 50, 50), font=font)

        img.save(str(path))
        log.info(f'默认封面已生成: {path}')

    except ImportError:
        # 没有 Pillow，创建一个最小的 PNG
        import struct
        import zlib

        def create_minimal_png(width=1080, height=1440):
            raw = b''
            for _ in range(height):
                raw += b'\x00' + b'\xff\xf0\xf5' * width
            compressed = zlib.compress(raw)

            def chunk(ctype, data):
                c = ctype + data
                return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

            ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
            return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', compressed) + chunk(b'IEND', b'')

        with open(str(path), 'wb') as f:
            f.write(create_minimal_png())
        log.info(f'默认封面已生成（最小PNG）: {path}')


def _save_report(title, content, tags, success, error=None):
    """保存发布报告"""
    report = {
        'time': datetime.now().isoformat(),
        'title': title,
        'content_length': len(content),
        'tags': tags or [],
        'result': {
            'success': success,
            'error': error
        }
    }
    report_file = LOG_DIR / f'report_{datetime.now():%Y%m%d_%H%M%S}.json'
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log.info(f'发布报告: {report_file}')


# ─── CLI ────────────────────────────────────────────────────

def cmd_login(args):
    """登录命令"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        ctx = create_browser_context(pw, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        if check_login(page):
            log.info('已经登录，无需重复登录')
            screenshot = SCREENSHOTS_DIR / f'already_logged_{datetime.now():%Y%m%d_%H%M%S}.png'
            page.screenshot(path=str(screenshot))
            print(json.dumps({
                'success': True,
                'status': 'already_logged_in',
                'screenshot': str(screenshot)
            }, ensure_ascii=False))
        else:
            qr_path = do_login(page, timeout=args.timeout)
            print(json.dumps({
                'success': True,
                'status': 'logged_in',
                'qr_screenshot': qr_path
            }, ensure_ascii=False))

        ctx.close()


def cmd_publish(args):
    """发布命令"""
    from playwright.sync_api import sync_playwright

    # 解析内容
    title = args.title
    content = args.content
    tags = args.tags.split(',') if args.tags else None
    images = args.images.split(',') if args.images else None

    # 从 JSON 文件读取
    if args.file:
        with open(args.file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        title = title or data.get('title', '')
        content = content or data.get('content', '')
        tags = tags or data.get('tags', [])
        images = images or data.get('images', [])

    if not title or not content:
        print(json.dumps({
            'success': False,
            'error': '必须提供标题和正文'
        }, ensure_ascii=False))
        sys.exit(1)

    with sync_playwright() as pw:
        ctx = create_browser_context(pw, headless=args.headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # 检查登录
        if not check_login(page):
            print(json.dumps({
                'success': False,
                'error': '未登录，请先执行 login 命令'
            }, ensure_ascii=False))
            ctx.close()
            sys.exit(1)

        # 发布
        result = publish_note(
            page,
            title=title,
            content=content,
            tags=tags,
            images=images,
            dry_run=args.dry_run,
            auto_image=not args.no_auto_image,
            image_count=args.image_count
        )

        print(json.dumps(result, ensure_ascii=False, indent=2))
        ctx.close()
        sys.exit(0 if result['success'] else 1)


def cmd_status(args):
    """检查登录状态"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        ctx = create_browser_context(pw, headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        logged_in = check_login(page)
        result = {
            'logged_in': logged_in,
            'browser_data_exists': BROWSER_DATA.exists() and any(BROWSER_DATA.iterdir()),
            'checked_at': datetime.now().isoformat()
        }

        print(json.dumps(result, ensure_ascii=False, indent=2))
        ctx.close()


def cmd_generate(args):
    """AI 生成内容"""
    sys.path.insert(0, str(Path(__file__).parent))
    from content_gen import generate_content, save_content, list_templates

    if args.list_styles:
        templates = list_templates()
        print(json.dumps(templates, ensure_ascii=False, indent=2))
        return

    if not args.topic:
        print(json.dumps({'success': False, 'error': '必须提供主题 (--topic)'}, ensure_ascii=False))
        sys.exit(1)

    try:
        result = generate_content(
            topic=args.topic,
            style=args.style,
            extra_instructions=args.extra or '',
        )
        path = save_content(result)
        result['saved_to'] = path
        log.info(f'内容已生成并保存: {path}')
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        log.error(f'内容生成失败: {e}')
        print(json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False))
        sys.exit(1)


def cmd_schedule(args):
    """定时发布管理"""
    sys.path.insert(0, str(Path(__file__).parent))
    from schedule import (add_task, remove_task, list_tasks, get_task,
                          toggle_task, format_task_summary, update_cron_job_id)

    action = args.schedule_action

    if action == 'list':
        tasks = list_tasks()
        if not tasks:
            print(json.dumps({'tasks': [], 'message': '暂无定时任务'}, ensure_ascii=False))
            return
        result = []
        for tid, task in tasks.items():
            result.append({**task, 'summary': format_task_summary(task)})
        print(json.dumps({'tasks': result, 'count': len(result)}, ensure_ascii=False, indent=2))

    elif action == 'add':
        if not args.topic:
            print(json.dumps({'success': False, 'error': '必须提供 --topic'}, ensure_ascii=False))
            sys.exit(1)
        if not args.cron_expr and not args.at_time and not args.every_minutes:
            print(json.dumps({'success': False, 'error': '必须指定调度方式: --cron / --at / --every'}, ensure_ascii=False))
            sys.exit(1)

        result = add_task(
            topic=args.topic,
            style=args.style,
            extra=args.extra or '',
            cron_expr=args.cron_expr,
            at_time=args.at_time,
            every_minutes=int(args.every_minutes) if args.every_minutes else None,
            tz=args.tz,
            headless=True,
            name=args.name,
        )

        # 输出 cron_job 供 agent 调用 OpenClaw cron API 创建
        print(json.dumps({
            'success': True,
            'task_id': result['task_id'],
            'cron_job': result['cron_job'],
            'message': '本地任务已创建，请用 cron tool 的 add action 将 cron_job 提交给 OpenClaw',
            'summary': format_task_summary(result['local_record']),
        }, ensure_ascii=False, indent=2))

    elif action == 'remove':
        if not args.task_id:
            print(json.dumps({'success': False, 'error': '必须提供 --task-id'}, ensure_ascii=False))
            sys.exit(1)
        cron_job_id = remove_task(args.task_id)
        print(json.dumps({
            'success': True,
            'task_id': args.task_id,
            'cron_job_id': cron_job_id,
            'message': f'本地任务已删除。' + (f'请用 cron tool remove 删除 OpenClaw cron job: {cron_job_id}' if cron_job_id else '无关联的 cron job'),
        }, ensure_ascii=False, indent=2))

    elif action == 'enable':
        if not args.task_id:
            print(json.dumps({'success': False, 'error': '必须提供 --task-id'}, ensure_ascii=False))
            sys.exit(1)
        task = toggle_task(args.task_id, True)
        if task:
            print(json.dumps({
                'success': True, 'task_id': args.task_id, 'enabled': True,
                'cron_job_id': task.get('cron_job_id'),
                'message': '已启用。' + (f'请用 cron tool update 启用 OpenClaw cron job: {task.get("cron_job_id")}' if task.get('cron_job_id') else ''),
            }, ensure_ascii=False, indent=2))
        else:
            print(json.dumps({'success': False, 'error': f'任务不存在: {args.task_id}'}, ensure_ascii=False))

    elif action == 'disable':
        if not args.task_id:
            print(json.dumps({'success': False, 'error': '必须提供 --task-id'}, ensure_ascii=False))
            sys.exit(1)
        task = toggle_task(args.task_id, False)
        if task:
            print(json.dumps({
                'success': True, 'task_id': args.task_id, 'enabled': False,
                'cron_job_id': task.get('cron_job_id'),
                'message': '已暂停。' + (f'请用 cron tool update 暂停 OpenClaw cron job: {task.get("cron_job_id")}' if task.get('cron_job_id') else ''),
            }, ensure_ascii=False, indent=2))
        else:
            print(json.dumps({'success': False, 'error': f'任务不存在: {args.task_id}'}, ensure_ascii=False))

    elif action == 'link':
        # 回填 cron_job_id
        if not args.task_id or not args.cron_job_id:
            print(json.dumps({'success': False, 'error': '必须提供 --task-id 和 --cron-job-id'}, ensure_ascii=False))
            sys.exit(1)
        ok = update_cron_job_id(args.task_id, args.cron_job_id)
        print(json.dumps({'success': ok, 'task_id': args.task_id, 'cron_job_id': args.cron_job_id}, ensure_ascii=False))

    else:
        print(json.dumps({'success': False, 'error': f'未知操作: {action}'}, ensure_ascii=False))
        sys.exit(1)


def cmd_trending(args):
    """热点数据采集"""
    sys.path.insert(0, str(Path(__file__).parent))
    from trending import fetch_trending, fetch_all_trending, get_top_topics, format_trending_text, SOURCES

    action = args.trending_action

    if action == 'sources':
        for key, info in SOURCES.items():
            print(f"  {info['emoji']} {key} — {info['name']}")
        return

    if action == 'topics':
        topics = get_top_topics(limit=args.limit)
        print(json.dumps(topics, ensure_ascii=False, indent=2))
        return

    # fetch
    if args.no_cache:
        data = fetch_trending(sources=args.sources, limit=args.limit)
    else:
        data = fetch_all_trending(limit=args.limit)
        if args.sources:
            data = {k: v for k, v in data.items() if k in args.sources or k.startswith('_')}

    if args.text:
        print(format_trending_text(data, limit=args.limit))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_hot(args):
    """根据热点话题一键生成内容（可选发布）"""
    sys.path.insert(0, str(Path(__file__).parent))
    from trending import get_top_topics
    from content_gen import generate_content, save_content

    # 获取热点话题
    topics = get_top_topics(limit=30)
    if not topics:
        print(json.dumps({'success': False, 'error': '获取热点失败'}, ensure_ascii=False))
        sys.exit(1)

    # 选择话题
    if args.pick:
        # 按序号选
        idx = args.pick - 1
        if idx < 0 or idx >= len(topics):
            print(json.dumps({'success': False, 'error': f'序号超出范围 (1-{len(topics)})'}, ensure_ascii=False))
            sys.exit(1)
        chosen = topics[idx]
    elif args.keyword:
        # 按关键词匹配
        matched = [t for t in topics if args.keyword in t['title']]
        if not matched:
            print(json.dumps({
                'success': False,
                'error': f'未匹配到含「{args.keyword}」的热点',
                'available': [t['title'] for t in topics[:10]],
            }, ensure_ascii=False, indent=2))
            sys.exit(1)
        chosen = matched[0]
    else:
        # 默认取第一个非置顶热点
        chosen = topics[0]

    topic = chosen['title']
    log.info(f'选中热点: {topic} (来源: {chosen["source"]})')

    # 生成内容
    extra = args.extra or ''
    extra_full = f'基于当前热点话题创作，来源: {chosen["source"]}。{extra}'.strip()
    try:
        result = generate_content(
            topic=topic,
            style=args.style,
            extra_instructions=extra_full,
        )
        path = save_content(result)
        result['saved_to'] = path
        result['hot_topic'] = chosen
        log.info(f'热点内容已生成: {result["title"]}')
    except Exception as e:
        print(json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False))
        sys.exit(1)

    if args.publish:
        # 一键发布
        from playwright.sync_api import sync_playwright
        title = result['title']
        content = result['content']
        tags = result.get('tags', [])
        overflow_text = result.get('overflow_text', '')

        with sync_playwright() as pw:
            ctx = create_browser_context(pw, headless=args.headless)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            if not check_login(page):
                print(json.dumps({'success': False, 'error': '未登录，请先执行 login 命令'}, ensure_ascii=False))
                ctx.close()
                sys.exit(1)

            pub_result = publish_note(
                page, title=title, content=content, tags=tags,
                dry_run=args.dry_run, auto_image=True,
                image_count=args.image_count,
                overflow_text=overflow_text,
            )
            pub_result['generated_content'] = path
            pub_result['hot_topic'] = chosen
            print(json.dumps(pub_result, ensure_ascii=False, indent=2))
            ctx.close()
            sys.exit(0 if pub_result['success'] else 1)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_stats(args):
    """发布数据统计"""
    sys.path.insert(0, str(Path(__file__).parent))
    from stats import load_reports, filter_by_date, summary, format_text

    reports = load_reports()
    reports = filter_by_date(reports, days=getattr(args, 'days', None), date_str=getattr(args, 'date', None))
    stats_data = summary(reports)

    if getattr(args, 'json', False):
        print(json.dumps(stats_data, ensure_ascii=False, indent=2))
    else:
        print(format_text(stats_data))


def cmd_comments(args):
    """评论自动互动"""
    sys.path.insert(0, str(Path(__file__).parent))
    from comments import fetch_comments, auto_reply, get_reply_stats, format_reply_results

    if args.comments_action == 'stats':
        print(json.dumps(get_reply_stats(), ensure_ascii=False, indent=2))
        return

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        ctx = create_browser_context(pw, headless=getattr(args, 'headless', False))
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        if not check_login(page):
            print(json.dumps({"success": False, "error": "未登录，请先执行 login 命令"}, ensure_ascii=False))
            ctx.close()
            sys.exit(1)

        if args.comments_action == 'fetch':
            comments = fetch_comments(page, limit=args.limit)
            print(json.dumps(comments, ensure_ascii=False, indent=2))
        elif args.comments_action == 'reply':
            results = auto_reply(
                page,
                limit=args.limit,
                style=args.style,
                dry_run=getattr(args, 'dry_run', False),
            )
            print(format_reply_results(results))
            print("\n" + json.dumps(results, ensure_ascii=False, indent=2))

        ctx.close()


def cmd_engagement(args):
    """笔记互动数据"""
    sys.path.insert(0, str(Path(__file__).parent))
    from engagement import fetch_note_engagement, generate_daily_report, format_daily_report, _load_engagement_db

    if args.engagement_action == 'cached':
        db = _load_engagement_db()
        if db.get('snapshots'):
            print(json.dumps(db['snapshots'][-1], ensure_ascii=False, indent=2))
        else:
            print(json.dumps({"message": "暂无缓存数据"}, ensure_ascii=False))
        return

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        ctx = create_browser_context(pw, headless=getattr(args, 'headless', False))
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        if not check_login(page):
            print(json.dumps({"success": False, "error": "未登录"}, ensure_ascii=False))
            ctx.close()
            sys.exit(1)

        if args.engagement_action == 'fetch':
            notes = fetch_note_engagement(page, limit=args.limit)
            print(json.dumps(notes, ensure_ascii=False, indent=2))
        elif args.engagement_action == 'report':
            no_eng = getattr(args, 'no_engagement', False)
            report = generate_daily_report(
                include_engagement=not no_eng,
                page=page if not no_eng else None,
            )
            if getattr(args, 'json', False):
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print(format_daily_report(report))

        ctx.close()


def delete_notes(page, max_count=100):
    """删除笔记管理页面上的所有笔记

    Args:
        page: Playwright page 对象（已登录状态）
        max_count: 最多删除数量（防止无限循环）

    Returns:
        dict: {deleted: int, errors: list}
    """
    deleted = 0
    errors = []

    for round_num in range(max_count):
        # 找包含"发布于"的元素（每个笔记卡片都有）
        time_els = page.get_by_text('发布于', exact=False)
        if time_els.count() == 0:
            break

        log.info(f'第 {round_num + 1} 轮，剩余 {time_els.count()} 篇笔记')

        try:
            # hover 第一个笔记卡片的父容器，让操作按钮显示
            first = time_els.first
            parent = first.evaluate_handle('el => { let p = el; for(let i=0;i<5;i++) p = p.parentElement; return p; }')
            parent.as_element().hover()
            time.sleep(1)

            # 点击删除按钮
            delete_btns = page.get_by_text('删除', exact=True)
            visible = [delete_btns.nth(i) for i in range(delete_btns.count()) if delete_btns.nth(i).is_visible()]
            if not visible:
                log.warning('没有可见的删除按钮')
                break

            visible[0].click()
            time.sleep(2)

            # 点击确认弹窗
            confirm = None
            for text in ['确认删除', '确认', '确定']:
                loc = page.get_by_text(text, exact=True)
                for i in range(loc.count()):
                    if loc.nth(i).is_visible():
                        confirm = loc.nth(i)
                        break
                if confirm:
                    break

            # 也找 role=button 的确认
            if not confirm:
                btns = page.locator('button')
                for i in range(btns.count()):
                    t = btns.nth(i).text_content().strip()
                    if t in ['确认删除', '确认', '确定'] and btns.nth(i).is_visible():
                        confirm = btns.nth(i)
                        break

            if confirm:
                confirm.click()
                time.sleep(3)
                deleted += 1
                log.info(f'已删除第 {deleted} 篇')
            else:
                log.warning('未找到确认按钮，跳过')
                # 按 Escape 关闭弹窗
                page.keyboard.press('Escape')
                time.sleep(1)
                errors.append(f'第 {round_num + 1} 轮未找到确认按钮')
                break

        except Exception as e:
            log.error(f'删除第 {round_num + 1} 篇时出错: {e}')
            errors.append(str(e))
            page.keyboard.press('Escape')
            time.sleep(1)

        # 滚动加载更多
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        time.sleep(2)

    return {'deleted': deleted, 'errors': errors}


def cmd_delete(args):
    """删除已发布的笔记"""
    from playwright.sync_api import sync_playwright

    headless = getattr(args, 'headless', True)
    confirm = getattr(args, 'yes', False)
    tab = getattr(args, 'tab', 'all')

    with sync_playwright() as pw:
        ctx = create_browser_context(pw, headless=headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # 进入笔记管理
        page.goto('https://creator.xiaohongshu.com/new/note-manager',
                   wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(5000)

        # 切换 tab（全部/已发布/审核中/未通过）
        tab_map = {'all': '全部笔记', 'published': '已发布', 'review': '审核中', 'failed': '未通过'}
        tab_text = tab_map.get(tab, '全部笔记')
        tab_loc = page.get_by_text(tab_text, exact=False)
        if tab_loc.count() > 0:
            tab_loc.first.click()
            page.wait_for_timeout(3000)

        # 统计笔记数
        note_count = page.get_by_text('发布于', exact=False).count()
        log.info(f'[{tab_text}] 找到 {note_count} 篇笔记')

        if note_count == 0:
            print(json.dumps({'deleted': 0, 'message': '没有笔记需要删除'}, ensure_ascii=False, indent=2))
            ctx.close()
            return

        if not confirm:
            print(f'即将删除 [{tab_text}] 下的 {note_count} 篇笔记（可能更多需滚动加载）')
            print('使用 --yes 跳过确认，或按 Ctrl+C 取消')
            try:
                input('按 Enter 继续...')
            except (KeyboardInterrupt, EOFError):
                print('\n已取消')
                ctx.close()
                return

        # 执行删除
        result = delete_notes(page, max_count=getattr(args, 'max', 100))

        # 截图确认
        shot = SCREENSHOTS_DIR / f'after_delete_{datetime.now():%Y%m%d_%H%M%S}.png'
        page.screenshot(path=str(shot))

        result['screenshot'] = str(shot)
        result['tab'] = tab_text
        print(json.dumps(result, ensure_ascii=False, indent=2))

        ctx.close()


def cmd_keystore(args):
    """API Key 加密管理"""
    sys.path.insert(0, str(Path(__file__).parent))
    from keystore import encrypt_keys, decrypt_keys, get_api_key, migrate_to_encrypted, KEYS_FILE, SALT_FILE
    import os

    password = os.environ.get('XHS_KEY_PASSWORD', '')
    action = args.key_action

    if action == 'status':
        try:
            from cryptography.fernet import Fernet
            has_crypto = True
        except ImportError:
            has_crypto = False
        print(json.dumps({
            'encrypted_file_exists': KEYS_FILE.exists(),
            'encrypted_file': str(KEYS_FILE),
            'has_cryptography': has_crypto,
            'salt_exists': SALT_FILE.exists(),
        }, ensure_ascii=False, indent=2))

    elif action == 'migrate':
        result = migrate_to_encrypted(password)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif action == 'list':
        if not KEYS_FILE.exists():
            print(json.dumps({'keys': [], 'message': '尚未创建加密存储'}, ensure_ascii=False))
            return
        try:
            keys = decrypt_keys(password)
            masked = {k: v[:4] + '***' + v[-4:] if len(v) > 8 else '***' for k, v in keys.items()}
            print(json.dumps({'keys': masked}, ensure_ascii=False, indent=2))
        except Exception as e:
            print(json.dumps({'error': str(e)}, ensure_ascii=False))

    elif action == 'set':
        if not args.key_name or not args.key_value:
            print(json.dumps({'success': False, 'error': '必须提供 --key-name 和 --key-value'}, ensure_ascii=False))
            sys.exit(1)
        existing = {}
        if KEYS_FILE.exists():
            try:
                existing = decrypt_keys(password)
            except Exception:
                pass
        existing[args.key_name] = args.key_value
        path = encrypt_keys(existing, password)
        print(json.dumps({'success': True, 'key': args.key_name, 'file': path}, ensure_ascii=False))

    elif action == 'get':
        if not args.key_name:
            print(json.dumps({'success': False, 'error': '必须提供 --key-name'}, ensure_ascii=False))
            sys.exit(1)
        val = get_api_key(args.key_name, password)
        if val:
            print(json.dumps({'key': args.key_name, 'found': True, 'preview': val[:4] + '***'}, ensure_ascii=False))
        else:
            print(json.dumps({'key': args.key_name, 'found': False}, ensure_ascii=False))


def cmd_generate_and_publish(args):
    """AI 生成内容 + 自动发布（一键流程）"""
    from playwright.sync_api import sync_playwright
    sys.path.insert(0, str(Path(__file__).parent))
    from content_gen import generate_content, save_content

    # 1. 生成内容
    log.info(f'一键生成发布: 主题={args.topic}, 风格={args.style}')
    try:
        content_data = generate_content(
            topic=args.topic,
            style=args.style,
            extra_instructions=args.extra or '',
        )
        path = save_content(content_data)
        log.info(f'内容已生成: {content_data["title"]}')
    except Exception as e:
        print(json.dumps({'success': False, 'phase': 'generate', 'error': str(e)}, ensure_ascii=False))
        sys.exit(1)

    title = content_data['title']
    content = content_data['content']
    tags = content_data.get('tags', [])
    overflow_text = content_data.get('overflow_text', '')

    if args.dry_run:
        print(json.dumps({
            'success': True,
            'dry_run': True,
            'title': title,
            'content': content,
            'tags': tags,
            'saved_to': path,
        }, ensure_ascii=False, indent=2))
        return

    # 2. 发布
    with sync_playwright() as pw:
        ctx = create_browser_context(pw, headless=args.headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        if not check_login(page):
            print(json.dumps({'success': False, 'error': '未登录，请先执行 login 命令'}, ensure_ascii=False))
            ctx.close()
            sys.exit(1)

        result = publish_note(
            page,
            title=title,
            content=content,
            tags=tags,
            dry_run=False,
            auto_image=not args.no_auto_image,
            image_count=args.image_count,
            overflow_text=overflow_text,
        )
        result['generated_content'] = path
        print(json.dumps(result, ensure_ascii=False, indent=2))
        ctx.close()
        sys.exit(0 if result['success'] else 1)


def main():
    parser = argparse.ArgumentParser(description='小红书自动化发布工具')
    sub = parser.add_subparsers(dest='command', help='可用命令')

    # login
    p_login = sub.add_parser('login', help='扫码登录小红书')
    p_login.add_argument('--timeout', type=int, default=300, help='登录超时秒数（默认300）')

    # publish
    p_pub = sub.add_parser('publish', help='发布笔记')
    p_pub.add_argument('--title', help='笔记标题')
    p_pub.add_argument('--content', help='笔记正文')
    p_pub.add_argument('--tags', help='标签，逗号分隔')
    p_pub.add_argument('--images', help='图片路径，逗号分隔')
    p_pub.add_argument('--file', help='从 JSON 文件读取内容')
    p_pub.add_argument('--dry-run', action='store_true', help='试运行，不实际发布')
    p_pub.add_argument('--headless', action='store_true', help='无头模式运行')
    p_pub.add_argument('--no-auto-image', action='store_true', help='禁用自动 AI 配图')
    p_pub.add_argument('--image-count', type=int, default=1, help='自动生成图片数量（1-9，默认1）')

    # status
    p_status = sub.add_parser('status', help='检查登录状态')

    # generate - AI 生成内容
    p_gen = sub.add_parser('generate', help='AI 生成小红书内容')
    p_gen.add_argument('--topic', '-t', help='主题/关键词')
    p_gen.add_argument('--style', '-s', default='default',
                       help='文案风格: default/review/tutorial/daily')
    p_gen.add_argument('--extra', '-e', help='额外指令')
    p_gen.add_argument('--list-styles', action='store_true', help='列出可用风格')

    # auto - 一键生成+发布
    p_auto = sub.add_parser('auto', help='AI 生成内容并自动发布')
    p_auto.add_argument('--topic', '-t', required=True, help='主题/关键词')
    p_auto.add_argument('--style', '-s', default='default',
                        help='文案风格: default/review/tutorial/daily')
    p_auto.add_argument('--extra', '-e', help='额外指令')
    p_auto.add_argument('--dry-run', action='store_true', help='只生成不发布')
    p_auto.add_argument('--headless', action='store_true', help='无头模式')
    p_auto.add_argument('--no-auto-image', action='store_true', help='禁用自动配图')
    p_auto.add_argument('--image-count', type=int, default=3, help='自动生成图片数量（1-9，默认3）')

    # schedule - 定时发布管理
    p_sched = sub.add_parser('schedule', help='定时发布管理')
    p_sched.add_argument('schedule_action',
                         choices=['list', 'add', 'remove', 'enable', 'disable', 'link'],
                         help='操作: list/add/remove/enable/disable/link')
    p_sched.add_argument('--topic', '-t', help='发布主题')
    p_sched.add_argument('--style', '-s', default='default', help='文案风格')
    p_sched.add_argument('--extra', '-e', help='额外指令')
    p_sched.add_argument('--cron', dest='cron_expr', help='cron 表达式 (如 "0 8 * * *")')
    p_sched.add_argument('--at', dest='at_time', help='一次性发布时间 ISO 格式 (如 "2026-02-13T10:00:00")')
    p_sched.add_argument('--every', dest='every_minutes', help='每隔 N 分钟发布')
    p_sched.add_argument('--tz', default='Asia/Shanghai', help='时区 (默认 Asia/Shanghai)')
    p_sched.add_argument('--name', help='任务名称')
    p_sched.add_argument('--task-id', dest='task_id', help='任务 ID')
    p_sched.add_argument('--cron-job-id', dest='cron_job_id', help='OpenClaw cron job ID (link 操作用)')

    # trending - 热点数据采集
    p_trend = sub.add_parser('trending', help='热点数据采集')
    p_trend.add_argument('trending_action', choices=['fetch', 'topics', 'sources'],
                         help='操作: fetch=采集热榜, topics=提取话题, sources=列出数据源')
    p_trend.add_argument('--source', '-s', action='append', dest='sources',
                         help='数据源 (可多次指定): baidu/toutiao/bilibili')
    p_trend.add_argument('--limit', '-n', type=int, default=20, help='每源返回条数 (默认20)')
    p_trend.add_argument('--no-cache', action='store_true', help='跳过缓存')
    p_trend.add_argument('--text', action='store_true', help='输出可读文本（默认 JSON）')

    # hot - 根据热点一键生成内容
    p_hot = sub.add_parser('hot', help='根据热点话题生成内容')
    p_hot.add_argument('--pick', '-p', type=int, help='选择第 N 个热点（从1开始）')
    p_hot.add_argument('--keyword', '-k', help='按关键词匹配热点')
    p_hot.add_argument('--style', '-s', default='default', help='文案风格')
    p_hot.add_argument('--extra', '-e', help='额外指令')
    p_hot.add_argument('--publish', action='store_true', help='生成后直接发布')
    p_hot.add_argument('--dry-run', action='store_true', help='试运行')
    p_hot.add_argument('--headless', action='store_true', help='无头模式')
    p_hot.add_argument('--image-count', type=int, default=3, help='自动生成图片数量（1-9，默认3）')

    # stats - 发布数据统计
    p_stats2 = sub.add_parser('stats', help='发布数据统计')
    p_stats2.add_argument('--days', type=int, help='最近 N 天')
    p_stats2.add_argument('--date', type=str, help='指定日期 (YYYY-MM-DD)')
    p_stats2.add_argument('--json', action='store_true', help='JSON 输出')

    # comments - 评论自动互动
    p_comments = sub.add_parser('comments', help='评论自动互动')
    p_comments.add_argument('comments_action', choices=['fetch', 'reply', 'stats'],
                            help='操作: fetch=抓取评论, reply=自动回复, stats=回复统计')
    p_comments.add_argument('--limit', type=int, default=10, help='评论数量（默认10）')
    p_comments.add_argument('--style', choices=['friendly', 'professional', 'humorous', 'brief'],
                            default='friendly', help='回复风格')
    p_comments.add_argument('--dry-run', action='store_true', help='只生成回复不实际发送')
    p_comments.add_argument('--headless', action='store_true', help='无头模式')

    # engagement - 笔记互动数据
    p_eng = sub.add_parser('engagement', help='笔记互动数据（阅读/点赞/收藏/评论）')
    p_eng.add_argument('engagement_action', choices=['fetch', 'report', 'cached'],
                       help='操作: fetch=抓取数据, report=每日报告, cached=查看缓存')
    p_eng.add_argument('--limit', type=int, default=20, help='笔记数量（默认20）')
    p_eng.add_argument('--headless', action='store_true', help='无头模式')
    p_eng.add_argument('--no-engagement', action='store_true', help='报告中不抓取互动数据')
    p_eng.add_argument('--json', action='store_true', help='JSON 输出')

    # keystore - API Key 加密管理
    p_key = sub.add_parser('keystore', help='API Key 加密管理')
    p_key.add_argument('key_action', choices=['status', 'migrate', 'list', 'set', 'get'],
                       help='操作: status/migrate/list/set/get')
    p_key.add_argument('--key-name', help='Key 名称')
    p_key.add_argument('--key-value', help='Key 值（set 操作用）')

    # delete - 删除已发布笔记
    p_del = sub.add_parser('delete', help='删除已发布的笔记')
    p_del.add_argument('--tab', choices=['all', 'published', 'review', 'failed'],
                       default='all', help='筛选: all/published/review/failed（默认 all）')
    p_del.add_argument('--max', type=int, default=100, help='最多删除数量（默认100）')
    p_del.add_argument('--yes', '-y', action='store_true', help='跳过确认直接删除')
    p_del.add_argument('--headless', action='store_true', help='无头模式')

    args = parser.parse_args()

    if args.command == 'login':
        cmd_login(args)
    elif args.command == 'publish':
        cmd_publish(args)
    elif args.command == 'status':
        cmd_status(args)
    elif args.command == 'generate':
        cmd_generate(args)
    elif args.command == 'auto':
        cmd_generate_and_publish(args)
    elif args.command == 'schedule':
        cmd_schedule(args)
    elif args.command == 'trending':
        cmd_trending(args)
    elif args.command == 'hot':
        cmd_hot(args)
    elif args.command == 'stats':
        cmd_stats(args)
    elif args.command == 'comments':
        cmd_comments(args)
    elif args.command == 'engagement':
        cmd_engagement(args)
    elif args.command == 'keystore':
        cmd_keystore(args)
    elif args.command == 'delete':
        cmd_delete(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
