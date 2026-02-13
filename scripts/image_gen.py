#!/usr/bin/env python3
"""
小红书配图生成器
优先使用 nano-banana-pro (Gemini 3 Pro Image)，代理不通时降级到 qwen-image (通义万相)
"""

import os
import sys
import json
import subprocess
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# 配置
PROXY = 'http://127.0.0.1:7897'
NANO_BANANA_SCRIPT = '/home/admin/.npm/_cacache/tmp/git-clonerhDFuv/node_modules/openclaw/skills/nano-banana-pro/scripts/generate_image.py'
QWEN_IMAGE_SCRIPT = '/home/admin/.openclaw/skills/qwen-image/scripts/generate_image.py'
OPENCLAW_CONFIG = Path.home() / '.openclaw' / 'openclaw.json'


def _load_config():
    """加载 openclaw 配置"""
    try:
        with open(OPENCLAW_CONFIG, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def _get_gemini_key():
    """获取 Gemini API Key"""
    cfg = _load_config()
    key = None
    try:
        key = cfg['skills']['entries']['nano-banana-pro']['apiKey']
    except (KeyError, TypeError):
        pass
    if not key:
        try:
            key = cfg['skills']['entries']['nano-banana-pro']['env']['GEMINI_API_KEY']
        except (KeyError, TypeError):
            pass
    if not key:
        key = os.environ.get('GEMINI_API_KEY', '')
    return key


def _get_qwen_key():
    """获取通义万相 API Key"""
    cfg = _load_config()
    key = None
    try:
        key = cfg['models']['providers']['bailian']['apiKey']
    except (KeyError, TypeError):
        pass
    if not key:
        try:
            key = cfg['skills']['entries']['qwen-image']['apiKey']
        except (KeyError, TypeError):
            pass
    if not key:
        key = os.environ.get('DASHSCOPE_API_KEY', '')
    return key


def _test_proxy():
    """测试代理是否能连通 Google"""
    try:
        import urllib.request
        import urllib.error
        proxy_handler = urllib.request.ProxyHandler({
            'https': PROXY,
            'http': PROXY
        })
        opener = urllib.request.build_opener(proxy_handler)
        req = urllib.request.Request(
            'https://generativelanguage.googleapis.com/',
            method='HEAD'
        )
        opener.open(req, timeout=8)
        return True
    except urllib.error.HTTPError:
        # 404/403 等 HTTP 错误说明网络是通的
        return True
    except Exception:
        return False


def _add_ai_watermark(image_path):
    """给图片右下角添加 'AI生成' 水印（合规要求：高度 ≥ 最短边 5%）"""
    try:
        img = Image.open(image_path)
        w, h = img.size
        min_side = min(w, h)
        font_size = max(int(min_side * 0.05), 16)

        draw = ImageDraw.Draw(img)

        # 尝试加载中文字体
        font = None
        font_paths = [
            '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
            '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
            '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        ]
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    font = ImageFont.truetype(fp, font_size)
                    break
                except Exception:
                    continue
        if not font:
            font = ImageFont.load_default()

        text = 'AI生成'
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

        # 右下角，留 10px 边距
        margin = 10
        x = w - tw - margin
        y = h - th - margin

        # 半透明背景
        bg_padding = 4
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle(
            [x - bg_padding, y - bg_padding, x + tw + bg_padding, y + th + bg_padding],
            fill=(0, 0, 0, 128)
        )
        overlay_draw.text((x, y), text, fill=(255, 255, 255, 220), font=font)

        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        img = Image.alpha_composite(img, overlay)
        img = img.convert('RGB')
        img.save(image_path)
        print(f'[图片生成] 已添加 AI 水印: {image_path}', file=sys.stderr)
    except Exception as e:
        print(f'[图片生成] AI 水印添加失败（不影响发布）: {e}', file=sys.stderr)


def generate_image(prompt, output_path, resolution='1K'):
    """
    生成图片，优先 nano-banana-pro，降级 qwen-image

    Args:
        prompt: 图片描述
        output_path: 输出文件路径
        resolution: 分辨率 1K/2K/4K（仅 nano-banana-pro 支持）

    Returns:
        dict: {'success': bool, 'path': str, 'engine': str, 'error': str}
    """
    output_path = str(output_path)

    # 尝试 nano-banana-pro
    gemini_key = _get_gemini_key()
    if gemini_key:
        print(f'[图片生成] 测试代理连通性...', file=sys.stderr)
        if _test_proxy():
            print(f'[图片生成] 代理可用，使用 nano-banana-pro (Gemini)', file=sys.stderr)
            result = _run_nano_banana(prompt, output_path, resolution, gemini_key)
            if result['success']:
                _add_ai_watermark(result['path'])
                return result
            print(f'[图片生成] nano-banana-pro 失败: {result.get("error", "未知错误")}', file=sys.stderr)
        else:
            print(f'[图片生成] 代理不通，跳过 nano-banana-pro', file=sys.stderr)

    # 降级到 qwen-image
    qwen_key = _get_qwen_key()
    if qwen_key:
        print(f'[图片生成] 降级使用 qwen-image (通义万相)', file=sys.stderr)
        result = _run_qwen_image(prompt, output_path, qwen_key)
        if result['success']:
            _add_ai_watermark(result['path'])
            return result
        print(f'[图片生成] qwen-image 也失败: {result.get("error", "未知错误")}', file=sys.stderr)

    return {
        'success': False,
        'path': '',
        'engine': 'none',
        'error': '所有图片生成引擎均不可用'
    }


def _run_nano_banana(prompt, output_path, resolution, api_key):
    """调用 nano-banana-pro 生成图片"""
    env = os.environ.copy()
    env['HTTPS_PROXY'] = PROXY
    env['HTTP_PROXY'] = PROXY
    env['GEMINI_API_KEY'] = api_key

    cmd = [
        'uv', 'run', NANO_BANANA_SCRIPT,
        '--prompt', prompt,
        '--filename', output_path,
        '--resolution', resolution
    ]

    try:
        proc = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=120
        )
        if proc.returncode == 0 and Path(output_path).exists():
            return {
                'success': True,
                'path': output_path,
                'engine': 'nano-banana-pro',
                'error': None
            }
        return {
            'success': False,
            'path': '',
            'engine': 'nano-banana-pro',
            'error': proc.stderr or proc.stdout or '生成失败'
        }
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'path': '',
            'engine': 'nano-banana-pro',
            'error': '生成超时（120秒）'
        }
    except Exception as e:
        return {
            'success': False,
            'path': '',
            'engine': 'nano-banana-pro',
            'error': str(e)
        }


def _run_qwen_image(prompt, output_path, api_key):
    """调用 qwen-image 生成图片"""
    # qwen-image 输出的是 URL，需要下载
    cmd = [
        'uv', 'run', QWEN_IMAGE_SCRIPT,
        '--prompt', prompt,
        '--size', '1024*1024',
        '--api-key', api_key
    ]

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
        if proc.returncode != 0:
            return {
                'success': False,
                'path': '',
                'engine': 'qwen-image',
                'error': proc.stderr or proc.stdout or '生成失败'
            }

        # 从输出中提取 MEDIA_URL
        media_url = None
        for line in proc.stdout.splitlines():
            if line.startswith('MEDIA_URL:'):
                media_url = line.split('MEDIA_URL:', 1)[1].strip()
                break

        if not media_url:
            return {
                'success': False,
                'path': '',
                'engine': 'qwen-image',
                'error': '未找到生成的图片 URL'
            }

        # 下载图片
        import urllib.request
        urllib.request.urlretrieve(media_url, output_path)

        if Path(output_path).exists():
            return {
                'success': True,
                'path': output_path,
                'engine': 'qwen-image',
                'error': None
            }
        return {
            'success': False,
            'path': '',
            'engine': 'qwen-image',
            'error': '图片下载失败'
        }

    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'path': '',
            'engine': 'qwen-image',
            'error': '生成超时（120秒）'
        }
    except Exception as e:
        return {
            'success': False,
            'path': '',
            'engine': 'qwen-image',
            'error': str(e)
        }


# ─── 文字排版图片（正文溢出时使用） ────────────────────────────

def render_text_pages(text, output_dir, prefix='text_page',
                      width=1080, height=1440,
                      bg_color='#FFF5F0', text_color='#2D2D2D',
                      font_size=36, line_spacing=1.6,
                      padding=(100, 80, 100, 80),
                      title=None, max_pages=8):
    """
    将长文本排版成多张图片（纯色底 + 文字），用于小红书正文溢出时的图片展示。

    Args:
        text: 要排版的文本
        output_dir: 输出目录
        prefix: 文件名前缀
        width/height: 图片尺寸（默认 3:4 竖版，适合小红书）
        bg_color: 背景色（默认暖白）
        text_color: 文字颜色
        font_size: 字号
        line_spacing: 行距倍数
        padding: (上, 右, 下, 左) 内边距
        title: 标题（如果提供，会在第一页顶部显示大标题）
        max_pages: 最大页数（默认8，配合1张封面刚好9张）

    Returns:
        list[str]: 生成的图片路径列表
    """
    from datetime import datetime

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 加载字体
    font = None
    font_paths = [
        '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                continue
    if not font:
        font = ImageFont.load_default()

    # 加载粗体字体（用于小标题）
    bold_font = None
    bold_paths = [
        '/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    ]
    for fp in bold_paths:
        if os.path.exists(fp):
            try:
                bold_font = ImageFont.truetype(fp, font_size + 2)
                break
            except Exception:
                continue
    if not bold_font:
        bold_font = font

    pad_top, pad_right, pad_bottom, pad_left = padding
    content_width = width - pad_left - pad_right
    content_height = height - pad_top - pad_bottom
    line_height = int(font_size * line_spacing)

    # 文本自动换行
    def wrap_text(txt, fnt):
        """将一行文本按宽度自动换行"""
        lines = []
        for raw_line in txt.split('\n'):
            if not raw_line.strip():
                lines.append('')
                continue
            current = ''
            for char in raw_line:
                test = current + char
                bbox = fnt.getbbox(test) if hasattr(fnt, 'getbbox') else (0, 0, len(test) * font_size, font_size)
                tw = bbox[2] - bbox[0]
                if tw > content_width:
                    lines.append(current)
                    current = char
                else:
                    current = test
            if current:
                lines.append(current)
        return lines

    # 判断是否是小标题行（以 emoji 或数字序号开头，或全大写短行）
    def is_heading(line):
        s = line.strip()
        if not s:
            return False
        # 数字序号开头：1. 2. ① ② 一、二、
        if len(s) < 40 and (s[0].isdigit() or s[0] in '①②③④⑤⑥⑦⑧⑨⑩'):
            return True
        # 中文序号
        if len(s) < 40 and s[0] in '一二三四五六七八九十':
            return True
        # 【】标题
        if s.startswith('【') and '】' in s[:20]:
            return True
        return False

    # 将所有文本换行并分页
    all_lines = wrap_text(text, font)
    pages = []
    current_page_lines = []
    current_y = 0

    for line in all_lines:
        needed = line_height + (8 if is_heading(line) and current_page_lines else 0)
        if current_y + needed > content_height and current_page_lines:
            pages.append(current_page_lines)
            current_page_lines = []
            current_y = 0
        if is_heading(line) and current_page_lines:
            current_y += 8  # 小标题前额外间距
        current_page_lines.append(line)
        current_y += line_height

    if current_page_lines:
        pages.append(current_page_lines)

    # 限制最大页数
    if len(pages) > max_pages:
        pages = pages[:max_pages]
        # 最后一页末尾加省略提示
        pages[-1].append('')
        pages[-1].append('...(更多内容请关注后续更新)')

    # 加载标题字体（比正文大）
    title_font = None
    if title:
        title_font_size = font_size + 12
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    title_font = ImageFont.truetype(fp, title_font_size)
                    break
                except Exception:
                    continue
        if not title_font:
            title_font = bold_font

    # 渲染每页
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_paths = []

    total_pages = len(pages)
    for i, page_lines in enumerate(pages):
        img = Image.new('RGB', (width, height), bg_color)
        draw = ImageDraw.Draw(img)

        # 页码（右上角）
        page_text = f'{i + 1}/{total_pages}'
        page_font_size = max(font_size - 8, 20)
        try:
            page_font = ImageFont.truetype(font_paths[0] if os.path.exists(font_paths[0]) else font_paths[-1], page_font_size)
        except Exception:
            page_font = font
        pbbox = draw.textbbox((0, 0), page_text, font=page_font)
        draw.text(
            (width - pad_right - (pbbox[2] - pbbox[0]), pad_top // 2 - (pbbox[3] - pbbox[1]) // 2),
            page_text, fill='#AAAAAA', font=page_font
        )

        # 渲染文本行
        y = pad_top

        # 第一页显示标题
        if i == 0 and title and title_font:
            # 标题自动换行
            title_lines = wrap_text(title, title_font)
            for tl in title_lines:
                draw.text((pad_left, y), tl, fill='#1A1A1A', font=title_font)
                y += int((font_size + 12) * line_spacing)
            # 标题下方加分隔线
            y += 8
            draw.line([(pad_left, y), (width - pad_right, y)], fill='#E0D5CF', width=2)
            y += 20

        for line in page_lines:
            if is_heading(line):
                y += 4
                draw.text((pad_left, y), line, fill=text_color, font=bold_font)
            else:
                draw.text((pad_left, y), line, fill=text_color, font=font)
            y += line_height

        # 底部装饰线
        line_y = height - pad_bottom + 20
        draw.line([(pad_left, line_y), (width - pad_right, line_y)], fill='#E0D5CF', width=1)

        # AI 水印
        _add_ai_watermark_to_draw(draw, img.size, font_paths)

        out_path = str(output_dir / f'{prefix}_{ts}_{i + 1}.png')
        img.save(out_path, quality=95)
        output_paths.append(out_path)

    print(f'[图片生成] 文字排版完成: {len(output_paths)} 页', file=sys.stderr)
    return output_paths


def _add_ai_watermark_to_draw(draw, img_size, font_paths):
    """在 ImageDraw 上直接绘制 AI 水印（用于文字排版图片，避免重复打开文件）"""
    w, h = img_size
    min_side = min(w, h)
    wm_font_size = max(int(min_side * 0.035), 14)

    wm_font = None
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                wm_font = ImageFont.truetype(fp, wm_font_size)
                break
            except Exception:
                continue

    text = 'AI生成'
    bbox = draw.textbbox((0, 0), text, font=wm_font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    margin = 10
    x, y = w - tw - margin, h - th - margin
    bg_padding = 3
    draw.rectangle(
        [x - bg_padding, y - bg_padding, x + tw + bg_padding, y + th + bg_padding],
        fill=(0, 0, 0, 80)
    )
    draw.text((x, y), text, fill=(255, 255, 255, 200), font=wm_font)


# ─── CLI ────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description='小红书配图生成器')
    parser.add_argument('--prompt', '-p', required=True, help='图片描述')
    parser.add_argument('--output', '-o', required=True, help='输出文件路径')
    parser.add_argument('--resolution', '-r', default='1K', choices=['1K', '2K', '4K'], help='分辨率')
    args = parser.parse_args()

    result = generate_image(args.prompt, args.output, args.resolution)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result['success'] else 1)


if __name__ == '__main__':
    main()
