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
