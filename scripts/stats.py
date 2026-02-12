#!/usr/bin/env python3
"""
发布数据统计模块
基于 logs/report_*.json 汇总发布历史、成功率、标签分布等
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

LOGS_DIR = Path(__file__).parent.parent / 'logs'


def load_reports():
    """加载所有发布报告"""
    reports = []
    for f in sorted(LOGS_DIR.glob('report_*.json')):
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
                data['_file'] = f.name
                reports.append(data)
        except (json.JSONDecodeError, IOError):
            continue
    return reports


def filter_by_date(reports, days=None, date_str=None):
    """按日期过滤报告"""
    if date_str:
        target = datetime.strptime(date_str, '%Y-%m-%d').date()
        return [r for r in reports if _parse_time(r).date() == target]
    if days:
        cutoff = datetime.now() - timedelta(days=days)
        return [r for r in reports if _parse_time(r) >= cutoff]
    return reports


def _parse_time(report):
    """解析报告时间"""
    t = report.get('time', '')
    for fmt in ('%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(t, fmt)
        except ValueError:
            continue
    return datetime.min


def summary(reports):
    """生成统计摘要"""
    if not reports:
        return {"total": 0, "message": "暂无发布记录"}

    total = len(reports)
    success = sum(1 for r in reports if r.get('result', {}).get('success'))
    failed = total - success
    rate = round(success / total * 100, 1) if total else 0

    # 标签统计
    all_tags = []
    for r in reports:
        all_tags.extend(r.get('tags', []))
    top_tags = Counter(all_tags).most_common(10)

    # 内容长度统计
    lengths = [r.get('content_length', 0) for r in reports]
    avg_len = round(sum(lengths) / len(lengths)) if lengths else 0

    # 按日期分组
    daily = Counter()
    for r in reports:
        day = _parse_time(r).strftime('%Y-%m-%d')
        daily[day] += 1

    # 最近发布
    latest = sorted(reports, key=_parse_time, reverse=True)[:5]
    recent = []
    for r in latest:
        recent.append({
            "time": r.get('time', ''),
            "title": r.get('title', ''),
            "success": r.get('result', {}).get('success', False)
        })

    # 错误汇总
    errors = []
    for r in reports:
        err = r.get('result', {}).get('error')
        if err:
            errors.append({"time": r.get('time', ''), "title": r.get('title', ''), "error": err})

    return {
        "total": total,
        "success": success,
        "failed": failed,
        "success_rate": f"{rate}%",
        "avg_content_length": avg_len,
        "top_tags": [{"tag": t, "count": c} for t, c in top_tags],
        "daily_count": dict(sorted(daily.items())),
        "recent": recent,
        "errors": errors if errors else None
    }


def format_text(stats):
    """格式化为可读文本"""
    if stats.get('total', 0) == 0:
        return "📊 暂无发布记录"

    lines = [
        f"📊 发布数据统计",
        f"",
        f"总计: {stats['total']} 篇 | 成功: {stats['success']} | 失败: {stats['failed']} | 成功率: {stats['success_rate']}",
        f"平均正文长度: {stats['avg_content_length']} 字",
        f"",
    ]

    if stats.get('daily_count'):
        lines.append("📅 每日发布:")
        for day, count in stats['daily_count'].items():
            lines.append(f"  {day}: {count} 篇")
        lines.append("")

    if stats.get('top_tags'):
        lines.append("🏷️ 热门标签 Top 10:")
        for item in stats['top_tags']:
            lines.append(f"  #{item['tag']} ({item['count']}次)")
        lines.append("")

    if stats.get('recent'):
        lines.append("📝 最近发布:")
        for r in stats['recent']:
            status = "✅" if r['success'] else "❌"
            t = r['time'][:16].replace('T', ' ') if r['time'] else '?'
            lines.append(f"  {status} [{t}] {r['title']}")
        lines.append("")

    if stats.get('errors'):
        lines.append("⚠️ 失败记录:")
        for e in stats['errors']:
            t = e['time'][:16].replace('T', ' ') if e['time'] else '?'
            lines.append(f"  ❌ [{t}] {e['title']}: {e['error']}")

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='发布数据统计')
    parser.add_argument('--days', type=int, help='最近 N 天')
    parser.add_argument('--date', type=str, help='指定日期 (YYYY-MM-DD)')
    parser.add_argument('--json', action='store_true', help='JSON 输出')
    args = parser.parse_args()

    reports = load_reports()
    reports = filter_by_date(reports, days=args.days, date_str=args.date)
    stats = summary(reports)

    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        print(format_text(stats))


if __name__ == '__main__':
    main()
