#!/usr/bin/env python3
"""
笔记数据抓取模块
从小红书创作者中心抓取笔记的阅读、点赞、收藏、评论等互动数据
"""

import json
import time
import logging
import sys
from pathlib import Path
from datetime import datetime

log = logging.getLogger(__name__)

SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / 'data'
DATA_DIR.mkdir(exist_ok=True)

ENGAGEMENT_DB = DATA_DIR / 'engagement.json'
XHS_CONTENT_MANAGE = 'https://creator.xiaohongshu.com/publish/manage'


def _load_engagement_db():
    """加载互动数据库"""
    if ENGAGEMENT_DB.exists():
        try:
            with open(ENGAGEMENT_DB, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"notes": {}, "snapshots": []}


def _save_engagement_db(db):
    """保存互动数据库"""
    with open(ENGAGEMENT_DB, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def fetch_note_engagement(page, limit=20):
    """
    从创作者中心「内容管理」页抓取笔记互动数据
    返回: [{"title", "status", "views", "likes", "collects", "comments", "shares", "publish_time"}]
    """
    log.info(f'正在抓取笔记互动数据（最多 {limit} 条）...')
    page.goto(XHS_CONTENT_MANAGE, wait_until='domcontentloaded', timeout=15000)
    time.sleep(3)

    notes = []
    seen_titles = set()

    max_scrolls = min(limit // 5 + 2, 15)
    for scroll_i in range(max_scrolls):
        # 尝试多种选择器匹配笔记列表项
        rows = page.locator(
            '.note-item, [class*="note-item"], [class*="NoteItem"], '
            'table tbody tr, .content-item, [class*="content-item"], '
            '[class*="ManageNote"], .manage-note-item'
        ).all()

        if not rows:
            # 备用：尝试表格行
            rows = page.locator('.ant-table-row, [class*="table"] tr').all()

        for row in rows:
            try:
                # 提取标题
                title = ''
                for sel in ['[class*="title"]', '.note-title', 'a', '[class*="name"]']:
                    try:
                        el = row.locator(sel).first
                        t = el.inner_text(timeout=1000).strip()
                        if t and len(t) > 2:
                            title = t[:50]
                            break
                    except Exception:
                        continue

                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)

                # 提取数值数据 — 尝试从行内所有数字元素中提取
                numbers = []
                try:
                    # 获取行内所有文本，提取数字
                    row_text = row.inner_text(timeout=2000)
                    import re
                    # 匹配数字（包括带万/w的）
                    raw_nums = re.findall(r'([\d.]+[万w]?)', row_text)
                    for n in raw_nums:
                        numbers.append(_parse_number(n))
                except Exception:
                    pass

                # 提取状态
                status = '已发布'
                try:
                    for kw in ['审核中', '未通过', '已隐藏', '草稿', '已发布', '公开']:
                        if kw in row_text:
                            status = kw
                            break
                except Exception:
                    pass

                # 尝试从特定 class 提取各项数据
                data = {
                    "title": title,
                    "status": status,
                    "views": 0,
                    "likes": 0,
                    "collects": 0,
                    "comments": 0,
                    "shares": 0,
                }

                # 尝试按列名匹配
                for field, keywords in [
                    ('views', ['阅读', '观看', '浏览', 'view', 'read', '曝光']),
                    ('likes', ['点赞', '赞', 'like', '❤']),
                    ('collects', ['收藏', 'collect', 'star', '⭐']),
                    ('comments', ['评论', 'comment', '💬']),
                    ('shares', ['分享', 'share', '转发']),
                ]:
                    for kw in keywords:
                        try:
                            el = row.locator(f'[class*="{kw}"], [title*="{kw}"]').first
                            val = el.inner_text(timeout=500).strip()
                            data[field] = _parse_number(val)
                            break
                        except Exception:
                            continue

                # 如果特定匹配没拿到数据，用位置推断
                # 创作者中心通常列顺序：标题 | 状态 | 阅读 | 点赞 | 收藏 | 评论 | 分享
                if all(data[k] == 0 for k in ['views', 'likes', 'collects', 'comments']) and len(numbers) >= 3:
                    fields = ['views', 'likes', 'collects', 'comments', 'shares']
                    for i, num in enumerate(numbers[:len(fields)]):
                        data[fields[i]] = num

                notes.append(data)

                if len(notes) >= limit:
                    break
            except Exception as e:
                log.debug(f'解析笔记行失败: {e}')
                continue

        if len(notes) >= limit:
            break

        page.evaluate('window.scrollBy(0, 600)')
        time.sleep(1.5)

    log.info(f'共抓取到 {len(notes)} 条笔记数据')

    # 保存快照
    db = _load_engagement_db()
    snapshot = {
        "time": datetime.now().isoformat(),
        "count": len(notes),
        "notes": notes,
    }
    db['snapshots'].append(snapshot)
    # 只保留最近 60 个快照
    if len(db['snapshots']) > 60:
        db['snapshots'] = db['snapshots'][-60:]

    # 更新每篇笔记的最新数据
    for note in notes:
        db['notes'][note['title']] = {
            **note,
            "last_updated": datetime.now().isoformat(),
        }
    _save_engagement_db(db)

    return notes


def _parse_number(text):
    """解析数字文本，支持 '1.2万'、'1.2w' 等格式"""
    if not text:
        return 0
    text = text.strip()
    import re
    m = re.match(r'^([\d.]+)\s*[万w]', text)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.match(r'^[\d.]+', text)
    if m:
        try:
            return int(float(m.group()))
        except ValueError:
            return 0
    return 0


def generate_daily_report(include_engagement=True, page=None):
    """
    生成每日数据报告
    如果提供 page 且 include_engagement=True，会先抓取最新互动数据
    """
    sys.path.insert(0, str(Path(__file__).parent))
    from stats import load_reports, filter_by_date, summary

    # 发布统计
    reports = load_reports()
    today_reports = filter_by_date(reports, days=1)
    all_stats = summary(reports)
    today_stats = summary(today_reports)

    report = {
        "generated_at": datetime.now().isoformat(),
        "publish_stats": {
            "today": {
                "total": today_stats.get('total', 0),
                "success": today_stats.get('success', 0),
                "failed": today_stats.get('failed', 0),
            },
            "all_time": {
                "total": all_stats.get('total', 0),
                "success": all_stats.get('success', 0),
                "success_rate": all_stats.get('success_rate', '0%'),
            },
            "top_tags": all_stats.get('top_tags', [])[:5],
        },
        "engagement": None,
    }

    # 互动数据
    if include_engagement and page:
        notes = fetch_note_engagement(page, limit=20)
        total_views = sum(n.get('views', 0) for n in notes)
        total_likes = sum(n.get('likes', 0) for n in notes)
        total_collects = sum(n.get('collects', 0) for n in notes)
        total_comments = sum(n.get('comments', 0) for n in notes)
        total_shares = sum(n.get('shares', 0) for n in notes)

        # 找出表现最好的笔记
        best_note = max(notes, key=lambda n: n.get('likes', 0) + n.get('collects', 0), default=None)

        report['engagement'] = {
            "notes_count": len(notes),
            "total_views": total_views,
            "total_likes": total_likes,
            "total_collects": total_collects,
            "total_comments": total_comments,
            "total_shares": total_shares,
            "best_note": {
                "title": best_note['title'],
                "likes": best_note.get('likes', 0),
                "collects": best_note.get('collects', 0),
                "comments": best_note.get('comments', 0),
            } if best_note else None,
            "notes_detail": notes[:10],
        }
    elif include_engagement:
        # 从缓存读取
        db = _load_engagement_db()
        if db.get('snapshots'):
            latest = db['snapshots'][-1]
            notes = latest.get('notes', [])
            total_views = sum(n.get('views', 0) for n in notes)
            total_likes = sum(n.get('likes', 0) for n in notes)
            total_collects = sum(n.get('collects', 0) for n in notes)
            total_comments = sum(n.get('comments', 0) for n in notes)
            total_shares = sum(n.get('shares', 0) for n in notes)
            best_note = max(notes, key=lambda n: n.get('likes', 0) + n.get('collects', 0), default=None)

            report['engagement'] = {
                "notes_count": len(notes),
                "total_views": total_views,
                "total_likes": total_likes,
                "total_collects": total_collects,
                "total_comments": total_comments,
                "total_shares": total_shares,
                "best_note": {
                    "title": best_note['title'],
                    "likes": best_note.get('likes', 0),
                    "collects": best_note.get('collects', 0),
                    "comments": best_note.get('comments', 0),
                } if best_note else None,
                "cached": True,
                "snapshot_time": latest.get('time', ''),
            }

    return report


def format_daily_report(report):
    """格式化每日报告为可读文本"""
    lines = [
        f"📊 小红书每日数据报告",
        f"📅 {report['generated_at'][:10]}",
        f"",
        f"📝 发布统计",
        f"  今日发布: {report['publish_stats']['today']['total']} 篇"
        f"（成功 {report['publish_stats']['today']['success']}，"
        f"失败 {report['publish_stats']['today']['failed']}）",
        f"  累计发布: {report['publish_stats']['all_time']['total']} 篇"
        f"（成功率 {report['publish_stats']['all_time']['success_rate']}）",
    ]

    tags = report['publish_stats'].get('top_tags', [])
    if tags:
        tag_str = ' '.join(f"#{t['tag']}" for t in tags[:5])
        lines.append(f"  热门标签: {tag_str}")

    eng = report.get('engagement')
    if eng:
        lines.extend([
            f"",
            f"💬 互动数据（{eng.get('notes_count', 0)} 篇笔记）",
            f"  👀 阅读: {eng.get('total_views', 0)}",
            f"  ❤️ 点赞: {eng.get('total_likes', 0)}",
            f"  ⭐ 收藏: {eng.get('total_collects', 0)}",
            f"  💬 评论: {eng.get('total_comments', 0)}",
            f"  🔗 分享: {eng.get('total_shares', 0)}",
        ])
        best = eng.get('best_note')
        if best:
            lines.extend([
                f"",
                f"🏆 最佳笔记: {best['title']}",
                f"   ❤️{best.get('likes', 0)} ⭐{best.get('collects', 0)} 💬{best.get('comments', 0)}",
            ])
        if eng.get('cached'):
            lines.append(f"\n  ⚠️ 互动数据来自缓存（{eng.get('snapshot_time', '')[:16]}）")
    else:
        lines.extend(["", "💬 互动数据: 暂无（需要先抓取）"])

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='笔记互动数据')
    sub = parser.add_subparsers(dest='action')

    p_fetch = sub.add_parser('fetch', help='抓取笔记互动数据')
    p_fetch.add_argument('--limit', type=int, default=20)
    p_fetch.add_argument('--headless', action='store_true')

    p_report = sub.add_parser('report', help='生成每日报告')
    p_report.add_argument('--headless', action='store_true')
    p_report.add_argument('--no-engagement', action='store_true', help='不抓取互动数据')
    p_report.add_argument('--json', action='store_true')

    p_cached = sub.add_parser('cached', help='查看缓存的互动数据')

    args = parser.parse_args()

    if args.action == 'cached':
        db = _load_engagement_db()
        if db.get('snapshots'):
            latest = db['snapshots'][-1]
            print(json.dumps(latest, ensure_ascii=False, indent=2))
        else:
            print(json.dumps({"message": "暂无缓存数据"}, ensure_ascii=False))
        return

    if args.action in ('fetch', 'report'):
        from playwright.sync_api import sync_playwright
        sys.path.insert(0, str(Path(__file__).parent))

        with sync_playwright() as pw:
            from xhs_auto import create_browser_context, check_login
            headless = getattr(args, 'headless', False)
            ctx = create_browser_context(pw, headless=headless)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            if not check_login(page):
                print(json.dumps({"success": False, "error": "未登录"}, ensure_ascii=False))
                ctx.close()
                sys.exit(1)

            if args.action == 'fetch':
                notes = fetch_note_engagement(page, limit=args.limit)
                print(json.dumps(notes, ensure_ascii=False, indent=2))
            elif args.action == 'report':
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
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
