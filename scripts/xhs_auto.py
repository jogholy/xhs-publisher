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
    """创建持久化浏览器上下文"""
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(BROWSER_DATA),
        headless=headless,
        viewport={'width': 1280, 'height': 900},
        locale='zh-CN',
        timezone_id='Asia/Shanghai',
        args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
        ],
        ignore_default_args=['--enable-automation'],
    )
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


def publish_note(page, title, content, tags=None, images=None, dry_run=False, auto_image=True):
    """
    发布小红书笔记

    Args:
        page: Playwright page 对象
        title: 笔记标题（不超过20字）
        content: 笔记正文（不超过1000字）
        tags: 标签列表（可选）
        images: 图片路径列表（可选，不传则自动生成配图）
        dry_run: 试运行，不实际点击发布
        auto_image: 没有图片时是否自动用 AI 生成配图（默认 True）
    """
    log.info(f'开始发布笔记: {title}')

    # 1. 导航到发布页
    page.goto(XHS_PUBLISH, wait_until='domcontentloaded', timeout=15000)
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
        log.info('未提供图片，自动生成 AI 配图...')
        generated = _auto_generate_image(title, content)
        if generated:
            image_paths = [generated]
            log.info(f'AI 配图生成成功: {generated}')
        else:
            log.warning('AI 配图生成失败，使用默认封面')
            default_cover = CONTENT_DIR / 'default_cover.png'
            if not default_cover.exists():
                _generate_default_cover(default_cover, title)
            image_paths = [str(default_cover)]
    elif not image_paths:
        default_cover = CONTENT_DIR / 'default_cover.png'
        if not default_cover.exists():
            _generate_default_cover(default_cover, title)
        image_paths = [str(default_cover)]

    try:
        upload_input = page.locator('input[type="file"]').first
        upload_input.set_input_files(image_paths)
        log.info(f'已上传 {len(image_paths)} 张图片')
        time.sleep(8)  # 等待上传和页面渲染
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

    try:
        publish_btn = page.locator('button:has-text("发布")').last
        publish_btn.click()
        log.info('已点击发布按钮')
        time.sleep(8)

        # 发布后截图
        post_shot = SCREENSHOTS_DIR / f'published_{datetime.now():%Y%m%d_%H%M%S}.png'
        page.screenshot(path=str(post_shot))
        log.info(f'发布完成！截图: {post_shot}')

        # 保存发布记录
        _save_report(title, content, tags, True)

        return {
            'success': True,
            'title': title,
            'screenshot': str(post_shot)
        }

    except Exception as e:
        log.error(f'发布失败: {e}')
        err_shot = SCREENSHOTS_DIR / f'error_{datetime.now():%Y%m%d_%H%M%S}.png'
        page.screenshot(path=str(err_shot))
        _save_report(title, content, tags, False, str(e))
        return {
            'success': False,
            'error': str(e),
            'screenshot': str(err_shot)
        }


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
            auto_image=not args.no_auto_image
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

    # status
    p_status = sub.add_parser('status', help='检查登录状态')

    args = parser.parse_args()

    if args.command == 'login':
        cmd_login(args)
    elif args.command == 'publish':
        cmd_publish(args)
    elif args.command == 'status':
        cmd_status(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
