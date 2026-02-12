#!/usr/bin/env python3
"""
小红书 AI 内容生成器
使用 OpenClaw 已配置的 LLM（百炼 Qwen）生成小红书风格的标题、正文和标签。
支持多种文案风格模板。
"""

import os
import sys
import json
import argparse
import re
from pathlib import Path
from datetime import datetime

# 路径常量
SKILL_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = SKILL_DIR / 'templates'
CONTENT_DIR = SKILL_DIR / 'content'
OPENCLAW_CONFIG = Path.home() / '.openclaw' / 'openclaw.json'

CONTENT_DIR.mkdir(exist_ok=True)


def load_config():
    """加载 OpenClaw 配置，获取 API 信息"""
    try:
        with open(OPENCLAW_CONFIG, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def get_llm_config():
    """获取 LLM API 配置（优先加密存储的 Key，fallback 明文配置）"""
    cfg = load_config()
    providers = cfg.get('models', {}).get('providers', {})

    # 尝试从加密存储获取 API Key
    encrypted_key = None
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from keystore import get_api_key
        encrypted_key = get_api_key('bailian_api_key')
    except Exception:
        pass

    # 优先用百炼（国内直连，快）
    if 'bailian' in providers:
        p = providers['bailian']
        model_id = p.get('models', [{}])[0].get('id', 'qwen-plus') if p.get('models') else 'qwen-plus'
        return {
            'base_url': p.get('baseUrl', ''),
            'api_key': encrypted_key or p.get('apiKey', ''),
            'model': model_id,
            'api_type': p.get('api', 'openai-completions'),
        }

    # 降级 generic
    if 'generic' in providers:
        p = providers['generic']
        model_id = p.get('models', [{}])[0].get('id', '') if p.get('models') else ''
        return {
            'base_url': p.get('baseUrl', ''),
            'api_key': p.get('apiKey', ''),
            'model': model_id,
            'api_type': p.get('api', 'openai-completions'),
        }

    return None


def list_templates():
    """列出所有可用模板"""
    templates = []
    if not TEMPLATES_DIR.exists():
        return templates
    for f in sorted(TEMPLATES_DIR.glob('*.json')):
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                t = json.load(fh)
            templates.append({
                'id': t.get('id', f.stem),
                'name': t.get('name', f.stem),
                'description': t.get('description', ''),
            })
        except Exception:
            pass
    return templates


def load_template(style):
    """加载指定风格的模板"""
    path = TEMPLATES_DIR / f'{style}.json'
    if not path.exists():
        # 尝试按 id 匹配
        for f in TEMPLATES_DIR.glob('*.json'):
            try:
                with open(f, 'r', encoding='utf-8') as fh:
                    t = json.load(fh)
                if t.get('id') == style:
                    return t
            except Exception:
                pass
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def call_llm(system_prompt, user_prompt, llm_cfg):
    """调用 LLM API 生成内容"""
    import urllib.request
    import urllib.error

    api_type = llm_cfg.get('api_type', 'openai-completions')
    base_url = llm_cfg['base_url'].rstrip('/')
    api_key = llm_cfg['api_key']
    model = llm_cfg['model']

    if 'anthropic' in api_type:
        # Anthropic Messages API
        url = f"{base_url}/v1/messages"
        headers = {
            'Content-Type': 'application/json',
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
        }
        body = {
            'model': model,
            'max_tokens': 4096,
            'system': system_prompt,
            'messages': [{'role': 'user', 'content': user_prompt}],
        }
    else:
        # OpenAI-compatible API
        url = f"{base_url}/chat/completions"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        }
        body = {
            'model': model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'temperature': 0.8,
            'max_tokens': 4096,
        }

    data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8', errors='replace')
        raise RuntimeError(f"LLM API 错误 ({e.code}): {err_body}")

    # 提取文本
    if 'anthropic' in api_type:
        text = result.get('content', [{}])[0].get('text', '')
    else:
        text = result.get('choices', [{}])[0].get('message', {}).get('content', '')

    return text


def extract_json(text):
    """从 LLM 输出中提取 JSON（兼容 markdown code block 包裹）"""
    # 去掉 markdown code block
    text = re.sub(r'^```(?:json)?\s*\n?', '', text.strip())
    text = re.sub(r'\n?```\s*$', '', text.strip())

    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试找第一个 { ... } 块
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法从 LLM 输出中提取 JSON:\n{text[:500]}")


def generate_content(topic, style='default', extra_instructions=''):
    """
    根据主题和风格生成小红书内容

    Args:
        topic: 主题/关键词
        style: 文案风格 (default/review/tutorial/daily/listicle/story/debate/comparison)
        extra_instructions: 额外指令

    Returns:
        dict: {title, content, tags, call_to_action, style, topic}
    """
    # 加载 LLM 配置
    llm_cfg = get_llm_config()
    if not llm_cfg:
        raise RuntimeError("未找到可用的 LLM 配置，请检查 ~/.openclaw/openclaw.json")

    # 加载模板
    template = load_template(style)
    if not template:
        print(f"[内容生成] 未找到模板 '{style}'，使用默认模板", file=sys.stderr)
        template = load_template('default')
    if not template:
        raise RuntimeError(f"模板加载失败: {style}")

    system_prompt = template.get('system', '你是一位资深小红书内容创作者。')
    user_prompt = template['user_template'].replace('{topic}', topic)

    if extra_instructions:
        user_prompt += f"\n\n额外要求：{extra_instructions}"

    print(f"[内容生成] 主题: {topic} | 风格: {template['name']} | 模型: {llm_cfg['model']}", file=sys.stderr)

    # 调用 LLM
    raw_text = call_llm(system_prompt, user_prompt, llm_cfg)

    # 解析 JSON
    result = extract_json(raw_text)

    # 标准化输出
    output = {
        'title': result.get('title', ''),
        'content': result.get('content', result.get('full_content', '')),
        'tags': result.get('tags', result.get('hashtags', [])),
        'call_to_action': result.get('call_to_action', ''),
        'style': template.get('id', style),
        'topic': topic,
        'generated_at': datetime.now().isoformat(),
        'model': llm_cfg['model'],
    }

    # 清理标签格式（确保不带 #）
    output['tags'] = [t.lstrip('#').strip() for t in output['tags'] if t.strip()]

    return output


def save_content(content_data, filename=None):
    """保存生成的内容到 JSON 文件"""
    if not filename:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"gen_{ts}.json"
    path = CONTENT_DIR / filename
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(content_data, f, ensure_ascii=False, indent=2)
    return str(path)


# ─── CLI ────────────────────────────────────────────────────

def cmd_generate(args):
    """生成内容"""
    try:
        result = generate_content(
            topic=args.topic,
            style=args.style,
            extra_instructions=args.extra or '',
        )

        # 保存到文件
        if args.save:
            path = save_content(result)
            result['saved_to'] = path
            print(f"[内容生成] 已保存到: {path}", file=sys.stderr)

        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as e:
        print(json.dumps({
            'success': False,
            'error': str(e),
        }, ensure_ascii=False, indent=2))
        sys.exit(1)


def cmd_list_styles(args):
    """列出可用风格"""
    templates = list_templates()
    if not templates:
        print("暂无可用模板")
        return
    print(json.dumps(templates, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description='小红书 AI 内容生成器')
    sub = parser.add_subparsers(dest='command', help='可用命令')

    # generate
    p_gen = sub.add_parser('generate', help='生成小红书内容')
    p_gen.add_argument('topic', help='主题/关键词')
    p_gen.add_argument('--style', '-s', default='default',
                       help='文案风格: default/review/tutorial/daily/listicle/story/debate/comparison')
    p_gen.add_argument('--extra', '-e', help='额外指令')
    p_gen.add_argument('--save', action='store_true', help='保存到文件')

    # styles
    sub.add_parser('styles', help='列出可用文案风格')

    args = parser.parse_args()

    if args.command == 'generate':
        cmd_generate(args)
    elif args.command == 'styles':
        cmd_list_styles(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
