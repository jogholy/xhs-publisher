#!/usr/bin/env python3
"""
热点数据采集模块
支持百度热搜、头条热榜、B站热搜，无需 API Key。
"""

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
CACHE_DIR = SKILL_DIR / 'content' / 'trending'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
TIMEOUT = 15

# ─── 数据源 ────────────────────────────────────────────────

SOURCES = {
    'baidu': {'name': '百度热搜', 'emoji': '🔍'},
    'toutiao': {'name': '头条热榜', 'emoji': '📰'},
    'bilibili': {'name': 'B站热搜', 'emoji': '📺'},
}


def _fetch_json(url, headers=None):
    """通用 JSON 请求"""
    hdrs = {'User-Agent': UA}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode('utf-8'))


def fetch_baidu():
    """百度热搜"""
    url = 'https://top.baidu.com/api/board?platform=wise&tab=realtime'
    data = _fetch_json(url)
    cards = data.get('data', {}).get('cards', [])
    if not cards:
        return []
    # 百度接口嵌套两层 content: cards[0].content[0].content[]
    top_content = cards[0].get('content', [])
    items = []
    for entry in top_content:
        if isinstance(entry, dict) and 'content' in entry:
            # 嵌套结构: entry.content 是实际列表
            items = entry.get('content', [])
            break
        else:
            items = top_content
            break
    results = []
    for i, item in enumerate(items):
        word = item.get('word', item.get('query', ''))
        if not word:
            continue
        rank = i + 1
        if item.get('isTop'):
            rank = 0  # 置顶
        elif item.get('index') is not None:
            rank = item['index'] + 1
        results.append({
            'rank': rank,
            'title': word,
            'url': item.get('url', ''),
            'hot': item.get('hotScore', ''),
            'is_top': item.get('isTop', False),
        })
    return results


def fetch_toutiao():
    """头条热榜"""
    url = 'https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc'
    data = _fetch_json(url)
    items = data.get('data', [])
    results = []
    for i, item in enumerate(items):
        results.append({
            'rank': i + 1,
            'title': item.get('Title', ''),
            'url': item.get('Url', ''),
            'hot': item.get('HotValue', ''),
            'label': item.get('Label', ''),
        })
    return results


def fetch_bilibili():
    """B站热搜"""
    url = 'https://app.bilibili.com/x/v2/search/trending/ranking'
    data = _fetch_json(url)
    items = data.get('data', {}).get('list', [])
    results = []
    for i, item in enumerate(items):
        results.append({
            'rank': i + 1,
            'title': item.get('keyword', ''),
            'show_name': item.get('show_name', ''),
            'icon': item.get('icon', ''),
        })
    return results


FETCHERS = {
    'baidu': fetch_baidu,
    'toutiao': fetch_toutiao,
    'bilibili': fetch_bilibili,
}


# ─── 聚合 ──────────────────────────────────────────────────

def fetch_trending(sources=None, limit=20):
    """
    采集热点数据

    Args:
        sources: 数据源列表 (默认全部)，可选 baidu/toutiao/bilibili
        limit: 每个源返回条数

    Returns:
        dict: {source: {name, emoji, items, fetched_at, error?}}
    """
    if sources is None:
        sources = list(FETCHERS.keys())

    result = {}
    for src in sources:
        if src not in FETCHERS:
            result[src] = {'error': f'不支持的数据源: {src}'}
            continue

        info = SOURCES[src]
        try:
            items = FETCHERS[src]()
            result[src] = {
                'name': info['name'],
                'emoji': info['emoji'],
                'items': items[:limit],
                'total': len(items),
                'fetched_at': datetime.now().isoformat(),
            }
        except Exception as e:
            result[src] = {
                'name': info['name'],
                'emoji': info['emoji'],
                'items': [],
                'error': str(e),
                'fetched_at': datetime.now().isoformat(),
            }

    return result


def fetch_all_trending(limit=20):
    """采集所有源的热点，带缓存（5分钟内不重复请求）"""
    cache_file = CACHE_DIR / 'latest.json'

    # 检查缓存
    if cache_file.exists():
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached = json.load(f)
            cached_at = cached.get('_cached_at', 0)
            if time.time() - cached_at < 300:  # 5 分钟缓存
                return cached
        except Exception:
            pass

    # 采集
    data = fetch_trending(limit=limit)
    data['_cached_at'] = time.time()

    # 写缓存
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return data


def get_top_topics(limit=10):
    """
    从所有热榜中提取去重后的热门话题（用于内容创作灵感）

    Returns:
        list[dict]: [{title, source, rank}]
    """
    data = fetch_all_trending(limit=50)
    seen = set()
    topics = []

    for src in ['baidu', 'toutiao', 'bilibili']:
        info = data.get(src, {})
        if info.get('error'):
            continue
        for item in info.get('items', []):
            title = item.get('title', '').strip()
            if not title or title in seen:
                continue
            seen.add(title)
            topics.append({
                'title': title,
                'source': SOURCES[src]['name'],
                'source_key': src,
                'rank': item.get('rank', 0),
            })

    return topics[:limit]


def format_trending_text(data, limit=10):
    """格式化热点数据为可读文本"""
    lines = []
    for src in ['baidu', 'toutiao', 'bilibili']:
        info = data.get(src)
        if not info or info.get('error'):
            if info:
                lines.append(f"{SOURCES[src]['emoji']} {SOURCES[src]['name']}：获取失败 ({info.get('error', '未知')})")
            continue

        lines.append(f"\n{info['emoji']} {info['name']}（共 {info['total']} 条）")
        for item in info['items'][:limit]:
            rank = item.get('rank', '')
            title = item.get('title', '')
            hot = item.get('hot', '')
            hot_str = f'  🔥{hot}' if hot else ''
            prefix = '  📌' if item.get('is_top') else f'  {rank}.'
            lines.append(f"{prefix} {title}{hot_str}")

    return '\n'.join(lines)


# ─── CLI ────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description='热点数据采集')
    parser.add_argument('action', choices=['fetch', 'topics', 'sources'],
                        help='操作: fetch=采集热榜, topics=提取话题, sources=列出数据源')
    parser.add_argument('--source', '-s', action='append', dest='sources',
                        help='数据源 (可多次指定): baidu/toutiao/bilibili')
    parser.add_argument('--limit', '-n', type=int, default=20, help='每源返回条数 (默认20)')
    parser.add_argument('--no-cache', action='store_true', help='跳过缓存')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')

    args = parser.parse_args()

    if args.action == 'sources':
        for key, info in SOURCES.items():
            print(f"  {info['emoji']} {key} — {info['name']}")
        return

    if args.action == 'topics':
        topics = get_top_topics(limit=args.limit)
        if args.json:
            print(json.dumps(topics, ensure_ascii=False, indent=2))
        else:
            print(f"🔥 热门话题 Top {len(topics)}:\n")
            for i, t in enumerate(topics, 1):
                print(f"  {i}. {t['title']}  ({t['source']})")
        return

    # fetch
    if args.no_cache:
        data = fetch_trending(sources=args.sources, limit=args.limit)
    else:
        data = fetch_all_trending(limit=args.limit)
        if args.sources:
            data = {k: v for k, v in data.items() if k in args.sources or k.startswith('_')}

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(format_trending_text(data, limit=args.limit))


if __name__ == '__main__':
    main()
