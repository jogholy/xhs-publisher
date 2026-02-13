#!/usr/bin/env python3
"""
小红书封面模板系统
使用 Pillow 本地渲染封面图，支持多种风格模板
"""

import os
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from datetime import datetime

# 中文字体路径
FONT_PATH = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'

# 模板定义
TEMPLATES = {
    'minimal': {
        'name': '简约风格',
        'bg_color': '#F8F9FA',
        'title_color': '#2D3748',
        'subtitle_color': '#718096',
        'title_size': 72,
        'subtitle_size': 36,
        'title_pos': (0.5, 0.4),  # 相对位置 (x, y)
        'subtitle_pos': (0.5, 0.55),
        'decorations': [
            {'type': 'line', 'pos': (0.2, 0.3), 'size': (0.6, 2), 'color': '#E2E8F0'}
        ]
    },
    'gradient': {
        'name': '渐变风格',
        'bg_gradient': ['#667eea', '#764ba2'],
        'title_color': '#FFFFFF',
        'subtitle_color': '#F7FAFC',
        'title_size': 68,
        'subtitle_size': 34,
        'title_pos': (0.5, 0.35),
        'subtitle_pos': (0.5, 0.5),
        'decorations': [
            {'type': 'circle', 'pos': (0.15, 0.2), 'size': 80, 'color': '#FFFFFF', 'alpha': 30},
            {'type': 'circle', 'pos': (0.85, 0.8), 'size': 120, 'color': '#FFFFFF', 'alpha': 20}
        ]
    },
    'magazine': {
        'name': '杂志风格',
        'bg_color': '#1A202C',
        'title_color': '#F7FAFC',
        'subtitle_color': '#FED7D7',
        'title_size': 64,
        'subtitle_size': 32,
        'title_pos': (0.5, 0.25),
        'subtitle_pos': (0.5, 0.4),
        'decorations': [
            {'type': 'rect', 'pos': (0.1, 0.15), 'size': (0.8, 4), 'color': '#F56565'},
            {'type': 'rect', 'pos': (0.1, 0.6), 'size': (0.3, 80), 'color': '#F56565', 'alpha': 80}
        ]
    },
    'education': {
        'name': '教育风格',
        'bg_color': '#EDF2F7',
        'title_color': '#2D3748',
        'subtitle_color': '#4A5568',
        'title_size': 70,
        'subtitle_size': 36,
        'title_pos': (0.5, 0.3),
        'subtitle_pos': (0.5, 0.45),
        'decorations': [
            {'type': 'rect', 'pos': (0.05, 0.05), 'size': (0.9, 0.9), 'color': '#CBD5E0', 'fill': False, 'width': 3},
            {'type': 'circle', 'pos': (0.2, 0.7), 'size': 40, 'color': '#4299E1'},
            {'type': 'circle', 'pos': (0.8, 0.75), 'size': 30, 'color': '#48BB78'}
        ]
    },
    'tech': {
        'name': '科技风格',
        'bg_gradient': ['#0F2027', '#203A43', '#2C5364'],
        'title_color': '#00F5FF',
        'subtitle_color': '#B0E0E6',
        'title_size': 66,
        'subtitle_size': 34,
        'title_pos': (0.5, 0.35),
        'subtitle_pos': (0.5, 0.5),
        'decorations': [
            {'type': 'line', 'pos': (0.1, 0.25), 'size': (0.8, 1), 'color': '#00F5FF', 'alpha': 150},
            {'type': 'rect', 'pos': (0.05, 0.65), 'size': (0.2, 0.2), 'color': '#00F5FF', 'alpha': 50},
            {'type': 'rect', 'pos': (0.75, 0.7), 'size': (0.15, 0.15), 'color': '#32CD32', 'alpha': 60}
        ]
    },
    'food': {
        'name': '美食风格',
        'bg_gradient': ['#FFF8DC', '#FFEFD5'],
        'title_color': '#8B4513',
        'subtitle_color': '#A0522D',
        'title_size': 68,
        'subtitle_size': 36,
        'title_pos': (0.5, 0.4),
        'subtitle_pos': (0.5, 0.55),
        'decorations': [
            {'type': 'circle', 'pos': (0.2, 0.2), 'size': 60, 'color': '#FF6347', 'alpha': 100},
            {'type': 'circle', 'pos': (0.8, 0.8), 'size': 80, 'color': '#FFD700', 'alpha': 120},
            {'type': 'circle', 'pos': (0.15, 0.75), 'size': 40, 'color': '#32CD32', 'alpha': 90}
        ]
    },
    'travel': {
        'name': '旅行风格',
        'bg_gradient': ['#87CEEB', '#98FB98'],
        'title_color': '#FFFFFF',
        'subtitle_color': '#F0F8FF',
        'title_size': 70,
        'subtitle_size': 38,
        'title_pos': (0.5, 0.3),
        'subtitle_pos': (0.5, 0.45),
        'decorations': [
            {'type': 'circle', 'pos': (0.85, 0.15), 'size': 100, 'color': '#FFFF00', 'alpha': 150},  # 太阳
            {'type': 'rect', 'pos': (0.1, 0.7), 'size': (0.8, 0.15), 'color': '#FFFFFF', 'alpha': 80}  # 云朵效果
        ]
    },
    'business': {
        'name': '商务风格',
        'bg_color': '#2D3748',
        'title_color': '#F7FAFC',
        'subtitle_color': '#CBD5E0',
        'title_size': 64,
        'subtitle_size': 32,
        'title_pos': (0.5, 0.35),
        'subtitle_pos': (0.5, 0.5),
        'decorations': [
            {'type': 'line', 'pos': (0.15, 0.25), 'size': (0.7, 3), 'color': '#4299E1'},
            {'type': 'rect', 'pos': (0.7, 0.6), 'size': (0.25, 0.25), 'color': '#4299E1', 'alpha': 40},
            {'type': 'line', 'pos': (0.15, 0.65), 'size': (0.4, 2), 'color': '#48BB78'}
        ]
    }
}


def load_font(size):
    """加载中文字体"""
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def create_gradient_background(width, height, colors):
    """创建渐变背景"""
    if len(colors) < 2:
        colors = colors + colors  # 重复颜色
    
    img = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(img)
    
    # 简单的线性渐变（从上到下）
    for y in range(height):
        ratio = y / height
        # 在两个颜色之间插值
        r1, g1, b1 = tuple(int(colors[0][i:i+2], 16) for i in (1, 3, 5))
        r2, g2, b2 = tuple(int(colors[1][i:i+2], 16) for i in (1, 3, 5))
        
        r = int(r1 + (r2 - r1) * ratio)
        g = int(g1 + (g2 - g1) * ratio)
        b = int(b1 + (b2 - b1) * ratio)
        
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    
    return img


def draw_decorations(draw, decorations, width, height):
    """绘制装饰元素"""
    for deco in decorations:
        deco_type = deco['type']
        pos = deco['pos']
        color = deco['color']
        alpha = deco.get('alpha', 255)
        
        # 转换相对位置为绝对位置
        if isinstance(pos, tuple) and len(pos) == 2:
            x = int(pos[0] * width)
            y = int(pos[1] * height)
        else:
            x, y = pos
        
        if deco_type == 'circle':
            size = deco['size']
            radius = size // 2
            # 创建带透明度的圆形
            circle_img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            circle_draw = ImageDraw.Draw(circle_img)
            
            # 解析颜色
            if color.startswith('#'):
                r, g, b = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
            else:
                r, g, b = 255, 255, 255
            
            circle_draw.ellipse([0, 0, size, size], fill=(r, g, b, alpha))
            
            # 粘贴到主图像
            temp_img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            temp_img.paste(circle_img, (x - radius, y - radius))
            
        elif deco_type == 'rect':
            size = deco['size']
            if isinstance(size, tuple):
                w = int(size[0] * width) if size[0] <= 1 else size[0]
                h = int(size[1] * height) if size[1] <= 1 else size[1]
            else:
                w = h = size
            
            # 解析颜色
            if color.startswith('#'):
                r, g, b = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
            else:
                r, g, b = 255, 255, 255
            
            if deco.get('fill', True):
                draw.rectangle([x, y, x + w, y + h], fill=(r, g, b))
            else:
                width_px = deco.get('width', 1)
                for i in range(width_px):
                    draw.rectangle([x + i, y + i, x + w - i, y + h - i], outline=(r, g, b))
        
        elif deco_type == 'line':
            size = deco['size']
            if isinstance(size, tuple):
                w = int(size[0] * width) if size[0] <= 1 else size[0]
                h = size[1]
            else:
                w, h = size, 1
            
            # 解析颜色
            if color.startswith('#'):
                r, g, b = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
            else:
                r, g, b = 255, 255, 255
            
            draw.rectangle([x, y, x + w, y + h], fill=(r, g, b))


def wrap_text(text, font, max_width):
    """文本自动换行"""
    lines = []
    words = text.split()
    current_line = ""
    
    for word in words:
        test_line = current_line + (" " if current_line else "") + word
        bbox = font.getbbox(test_line) if hasattr(font, 'getbbox') else (0, 0, len(test_line) * 20, 20)
        if bbox[2] - bbox[0] <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    
    if current_line:
        lines.append(current_line)
    
    return lines


def generate_cover(title, subtitle="", template_name="minimal", output_path=None):
    """
    生成封面图
    
    Args:
        title: 标题文字
        subtitle: 副标题文字（可选）
        template_name: 模板名称，支持 'random' 随机选择
        output_path: 输出路径，不指定则自动生成
    
    Returns:
        dict: {'success': bool, 'path': str, 'template': str, 'error': str}
    """
    # 随机选择模板
    if template_name == 'random':
        template_name = random.choice(list(TEMPLATES.keys()))
    
    if template_name not in TEMPLATES:
        return {
            'success': False,
            'path': '',
            'template': template_name,
            'error': f'模板不存在: {template_name}'
        }
    
    template = TEMPLATES[template_name]
    
    # 图片尺寸 (3:4 竖版，适合小红书)
    width, height = 1080, 1440
    
    try:
        # 创建背景
        if 'bg_gradient' in template:
            img = create_gradient_background(width, height, template['bg_gradient'])
        else:
            bg_color = template.get('bg_color', '#FFFFFF')
            img = Image.new('RGB', (width, height), bg_color)
        
        draw = ImageDraw.Draw(img)
        
        # 绘制装饰元素
        if 'decorations' in template:
            draw_decorations(draw, template['decorations'], width, height)
        
        # 加载字体
        title_font = load_font(template['title_size'])
        subtitle_font = load_font(template['subtitle_size'])
        
        # 绘制标题
        title_lines = wrap_text(title, title_font, width * 0.8)
        title_pos = template['title_pos']
        title_x = int(title_pos[0] * width)
        title_y = int(title_pos[1] * height)
        
        # 计算总标题高度用于居中
        total_title_height = len(title_lines) * template['title_size'] * 1.2
        start_y = title_y - total_title_height // 2
        
        for i, line in enumerate(title_lines):
            bbox = title_font.getbbox(line) if hasattr(title_font, 'getbbox') else (0, 0, len(line) * 20, 20)
            line_width = bbox[2] - bbox[0]
            line_x = title_x - line_width // 2
            line_y = start_y + i * template['title_size'] * 1.2
            
            draw.text((line_x, line_y), line, fill=template['title_color'], font=title_font)
        
        # 绘制副标题
        if subtitle:
            subtitle_lines = wrap_text(subtitle, subtitle_font, width * 0.8)
            subtitle_pos = template['subtitle_pos']
            subtitle_x = int(subtitle_pos[0] * width)
            subtitle_y = int(subtitle_pos[1] * height)
            
            for i, line in enumerate(subtitle_lines):
                bbox = subtitle_font.getbbox(line) if hasattr(subtitle_font, 'getbbox') else (0, 0, len(line) * 15, 15)
                line_width = bbox[2] - bbox[0]
                line_x = subtitle_x - line_width // 2
                line_y = subtitle_y + i * template['subtitle_size'] * 1.2
                
                draw.text((line_x, line_y), line, fill=template['subtitle_color'], font=subtitle_font)
        
        # 生成输出路径
        if not output_path:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = f'/tmp/cover_{template_name}_{timestamp}.png'
        
        # 保存图片
        img.save(output_path, quality=95)
        
        return {
            'success': True,
            'path': output_path,
            'template': template_name,
            'template_name': template['name'],
            'error': None
        }
        
    except Exception as e:
        return {
            'success': False,
            'path': '',
            'template': template_name,
            'error': str(e)
        }


def list_templates():
    """列出所有可用模板"""
    return [
        {
            'id': tid,
            'name': template['name'],
            'description': f"{template['name']} - 适合各种内容风格"
        }
        for tid, template in TEMPLATES.items()
    ]


# ─── CLI ────────────────────────────────────────────────────

def main():
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description='小红书封面模板生成器')
    parser.add_argument('--title', '-t', required=True, help='标题文字')
    parser.add_argument('--subtitle', '-s', default='', help='副标题文字')
    parser.add_argument('--template', default='minimal', help='模板名称或 random')
    parser.add_argument('--output', '-o', help='输出文件路径')
    parser.add_argument('--list', action='store_true', help='列出所有模板')
    
    args = parser.parse_args()
    
    if args.list:
        templates = list_templates()
        print(json.dumps(templates, ensure_ascii=False, indent=2))
        return
    
    result = generate_cover(
        title=args.title,
        subtitle=args.subtitle,
        template_name=args.template,
        output_path=args.output
    )
    
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    exit(main())