#!/usr/bin/env python3
"""小红书配图生成器 - 使用 media-generator skill"""
import sys
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

MEDIA_GEN = str(Path.home() / '.openclaw/skills/media-generator/scripts/generate.py')

def generate_image(prompt, output, model='fal-ai/bytedance/seedream/v4.5/text-to-image'):
    result = subprocess.run([
        sys.executable, MEDIA_GEN, 'image', prompt,
        '--provider', 'xskill', '--model', model
    ], capture_output=True, text=True, timeout=120)
    
    if result.returncode != 0:
        raise RuntimeError(f"生成失败: {result.stderr}")
    
    for line in result.stdout.split('\n'):
        if line.startswith('图片 1:'):
            url = line.split(':', 1)[1].strip()
            import urllib.request
            urllib.request.urlretrieve(url, output)
            return output
    
    raise RuntimeError("未找到图片 URL")

def add_watermark(path):
    img = Image.open(path)
    w, h = img.size
    size = max(int(min(w, h) * 0.05), 16)
    
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', size)
    except:
        font = ImageFont.load_default()
    
    text = 'AI生成'
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    
    x, y = w - tw - 10, h - th - 10
    draw.rectangle([x-5, y-5, x+tw+5, y+th+5], fill=(0,0,0,128))
    draw.text((x, y), text, fill='white', font=font)
    img.save(path)

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('prompt')
    p.add_argument('--output', '-o', required=True)
    p.add_argument('--model', default='fal-ai/bytedance/seedream/v4.5/text-to-image')
    args = p.parse_args()
    
    generate_image(args.prompt, args.output, args.model)
    add_watermark(args.output)
    print(f"✅ {args.output}")
