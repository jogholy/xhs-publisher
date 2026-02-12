#!/usr/bin/env python3
"""
评论自动互动模块
通过 Playwright 抓取小红书笔记评论，用 AI 生成个性化回复
"""

import json
import time
import logging
import re
import sys
from pathlib import Path
from datetime import datetime

log = logging.getLogger(__name__)

SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / 'data'
DATA_DIR.mkdir(exist_ok=True)

COMMENTS_DB = DATA_DIR / 'comments.json'
XHS_CREATOR = 'https://creator.xiaohongshu.com'
XHS_COMMENTS = 'https://creator.xiaohongshu.com/comment'


def _load_db():
    """加载评论数据库"""
    if COMMENTS_DB.exists():
        try:
            with open(COMMENTS_DB, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"replied": [], "stats": {"total_fetched": 0, "total_replied": 0}}


def _save_db(db):
    """保存评论数据库"""
    with open(COMMENTS_DB, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def _already_replied(db, comment_id):
    """检查是否已回复过"""
    return comment_id in db.get('replied', [])


def _mark_replied(db, comment_id):
    """标记为已回复"""
    if comment_id not in db['replied']:
        db['replied'].append(comment_id)
        # 只保留最近 2000 条记录，防止文件过大
        if len(db['replied']) > 2000:
            db['replied'] = db['replied'][-2000:]
    db['stats']['total_replied'] = db['stats'].get('total_replied', 0) + 1
    _save_db(db)


def fetch_comments(page, limit=20):
    """
    从创作者中心评论管理页抓取评论
    返回: [{"id", "author", "content", "note_title", "time", "reply_btn_selector"}]
    """
    log.info(f'正在抓取评论（最多 {limit} 条）...')
    page.goto(XHS_COMMENTS, wait_until='domcontentloaded', timeout=15000)
    time.sleep(3)

    # 点击"未回复"筛选（如果有的话）
    try:
        unreplied_tab = page.locator('text=未回复').first
        if unreplied_tab.is_visible(timeout=3000):
            unreplied_tab.click()
            time.sleep(2)
            log.info('已切换到"未回复"评论列表')
    except Exception:
        log.info('未找到"未回复"筛选，使用默认列表')

    comments = []
    seen_ids = set()

    # 滚动加载更多评论
    max_scrolls = min(limit // 5 + 1, 10)
    for scroll_i in range(max_scrolls):
        # 抓取当前可见的评论项
        items = page.locator('.comment-item, [class*="comment-item"], [class*="CommentItem"]').all()
        if not items:
            # 尝试备用选择器
            items = page.locator('.comment-container > div, .comment-list > div').all()

        for item in items:
            try:
                # 提取评论文本
                content_el = item.locator('[class*="content"], .comment-content, .note-comment').first
                content = content_el.inner_text(timeout=2000).strip() if content_el.is_visible(timeout=1000) else ''
                if not content:
                    continue

                # 生成唯一 ID（基于内容哈希）
                comment_id = str(hash(content))[:12]
                if comment_id in seen_ids:
                    continue
                seen_ids.add(comment_id)

                # 提取作者
                author = ''
                try:
                    author_el = item.locator('[class*="author"], [class*="nickname"], [class*="user-name"]').first
                    author = author_el.inner_text(timeout=1000).strip()
                except Exception:
                    pass

                # 提取关联笔记标题
                note_title = ''
                try:
                    title_el = item.locator('[class*="note-title"], [class*="title"]').first
                    note_title = title_el.inner_text(timeout=1000).strip()
                except Exception:
                    pass

                # 提取时间
                comment_time = ''
                try:
                    time_el = item.locator('[class*="time"], time, [class*="date"]').first
                    comment_time = time_el.inner_text(timeout=1000).strip()
                except Exception:
                    pass

                comments.append({
                    "id": comment_id,
                    "author": author,
                    "content": content,
                    "note_title": note_title,
                    "time": comment_time,
                    "_item_index": len(comments),
                })

                if len(comments) >= limit:
                    break
            except Exception as e:
                log.debug(f'解析评论项失败: {e}')
                continue

        if len(comments) >= limit:
            break

        # 滚动加载更多
        page.evaluate('window.scrollBy(0, 800)')
        time.sleep(1.5)

    log.info(f'共抓取到 {len(comments)} 条评论')
    return comments[:limit]


def generate_reply(comment_content, note_title='', author='', style='friendly'):
    """
    用 AI 生成评论回复
    style: friendly(友好), professional(专业), humorous(幽默), brief(简短)
    """
    sys.path.insert(0, str(Path(__file__).parent))

    # 复用 content_gen 的 LLM 调用
    from content_gen import _call_llm

    style_prompts = {
        'friendly': '友好亲切、有温度，像朋友聊天一样',
        'professional': '专业有深度，体现知识储备',
        'humorous': '幽默风趣，适当用网络流行语和 emoji',
        'brief': '简短精炼，一两句话回复',
    }
    style_desc = style_prompts.get(style, style_prompts['friendly'])

    prompt = f"""你是一个小红书博主，需要回复粉丝的评论。

笔记标题：{note_title or '(未知)'}
粉丝昵称：{author or '(匿名)'}
评论内容：{comment_content}

回复风格要求：{style_desc}

规则：
1. 回复要自然、真诚，不要太官方
2. 长度控制在 10-80 字
3. 可以适当用 emoji，但不要过多（1-2个）
4. 如果评论是提问，认真回答
5. 如果评论是夸赞，真诚感谢
6. 如果评论是负面的，礼貌回应不要对抗
7. 不要用"亲"、"宝"等过于商业化的称呼
8. 直接输出回复内容，不要加引号或前缀

回复："""

    try:
        reply = _call_llm(prompt, max_tokens=200)
        reply = reply.strip().strip('"').strip("'")
        # 限制长度
        if len(reply) > 100:
            reply = reply[:97] + '...'
        return reply
    except Exception as e:
        log.error(f'AI 生成回复失败: {e}')
        return None


def reply_to_comment(page, comment_index, reply_text):
    """
    在页面上回复指定评论
    comment_index: 评论在页面上的索引
    reply_text: 回复内容
    """
    try:
        items = page.locator('.comment-item, [class*="comment-item"], [class*="CommentItem"]').all()
        if not items:
            items = page.locator('.comment-container > div, .comment-list > div').all()

        if comment_index >= len(items):
            log.error(f'评论索引 {comment_index} 超出范围（共 {len(items)} 条）')
            return False

        item = items[comment_index]

        # 点击回复按钮
        reply_btn = item.locator('text=回复').first
        if not reply_btn.is_visible(timeout=3000):
            # 尝试 hover 触发回复按钮
            item.hover()
            time.sleep(0.5)
            reply_btn = item.locator('text=回复').first

        reply_btn.click(timeout=3000)
        time.sleep(0.5)

        # 找到输入框并输入
        input_box = page.locator('[contenteditable="true"], textarea[placeholder*="回复"], input[placeholder*="回复"]').last
        input_box.click()
        time.sleep(0.3)

        # 逐字输入避免触发反作弊
        for char in reply_text:
            input_box.type(char, delay=50)
        time.sleep(0.5)

        # 点击发送
        send_btn = page.locator('text=发送').last
        if send_btn.is_visible(timeout=2000):
            send_btn.click()
        else:
            # 尝试按回车发送
            input_box.press('Enter')

        time.sleep(1)
        log.info(f'已回复评论 #{comment_index + 1}')
        return True

    except Exception as e:
        log.error(f'回复评论 #{comment_index + 1} 失败: {e}')
        return False


def auto_reply(page, limit=10, style='friendly', dry_run=False):
    """
    自动回复未回复的评论
    返回: {"total", "replied", "skipped", "failed", "details"}
    """
    db = _load_db()
    comments = fetch_comments(page, limit=limit)
    db['stats']['total_fetched'] = db['stats'].get('total_fetched', 0) + len(comments)

    results = {
        "total": len(comments),
        "replied": 0,
        "skipped": 0,
        "failed": 0,
        "details": []
    }

    for comment in comments:
        cid = comment['id']

        # 跳过已回复的
        if _already_replied(db, cid):
            results['skipped'] += 1
            continue

        # 生成回复
        reply = generate_reply(
            comment_content=comment['content'],
            note_title=comment.get('note_title', ''),
            author=comment.get('author', ''),
            style=style,
        )

        if not reply:
            results['failed'] += 1
            results['details'].append({
                "comment": comment['content'][:50],
                "status": "ai_failed"
            })
            continue

        detail = {
            "author": comment.get('author', ''),
            "comment": comment['content'][:80],
            "reply": reply,
            "status": "dry_run" if dry_run else "pending"
        }

        if dry_run:
            results['replied'] += 1
            detail['status'] = 'dry_run'
        else:
            # 实际回复
            success = reply_to_comment(page, comment['_item_index'], reply)
            if success:
                _mark_replied(db, cid)
                results['replied'] += 1
                detail['status'] = 'sent'
                # 间隔 3-5 秒，避免频率过高
                time.sleep(3)
            else:
                results['failed'] += 1
                detail['status'] = 'send_failed'

        results['details'].append(detail)

    _save_db(db)
    return results


def get_reply_stats():
    """获取回复统计"""
    db = _load_db()
    return {
        "total_replied": db['stats'].get('total_replied', 0),
        "total_fetched": db['stats'].get('total_fetched', 0),
        "tracked_comments": len(db.get('replied', [])),
    }


def format_reply_results(results):
    """格式化回复结果为可读文本"""
    lines = [
        f"💬 评论互动结果",
        f"",
        f"总计: {results['total']} 条 | 已回复: {results['replied']} | 跳过: {results['skipped']} | 失败: {results['failed']}",
        f"",
    ]

    if results.get('details'):
        for i, d in enumerate(results['details'], 1):
            status_icon = {"sent": "✅", "dry_run": "👀", "ai_failed": "⚠️", "send_failed": "❌"}.get(d['status'], "?")
            lines.append(f"{status_icon} [{d.get('author', '匿名')}] {d['comment'][:40]}")
            if d.get('reply'):
                lines.append(f"   ↳ {d['reply']}")
            lines.append("")

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='评论自动互动')
    sub = parser.add_subparsers(dest='action')

    p_fetch = sub.add_parser('fetch', help='抓取评论')
    p_fetch.add_argument('--limit', type=int, default=10)

    p_reply = sub.add_parser('reply', help='自动回复评论')
    p_reply.add_argument('--limit', type=int, default=10)
    p_reply.add_argument('--style', choices=['friendly', 'professional', 'humorous', 'brief'], default='friendly')
    p_reply.add_argument('--dry-run', action='store_true', help='只生成回复不实际发送')
    p_reply.add_argument('--headless', action='store_true')

    p_stats = sub.add_parser('stats', help='回复统计')

    args = parser.parse_args()

    if args.action == 'stats':
        print(json.dumps(get_reply_stats(), ensure_ascii=False, indent=2))
        return

    if args.action in ('fetch', 'reply'):
        from playwright.sync_api import sync_playwright
        sys.path.insert(0, str(Path(__file__).parent))

        with sync_playwright() as pw:
            # 复用主模块的浏览器创建
            from xhs_auto import create_browser_context, check_login
            headless = getattr(args, 'headless', False)
            ctx = create_browser_context(pw, headless=headless)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            if not check_login(page):
                print(json.dumps({"success": False, "error": "未登录，请先执行 login 命令"}, ensure_ascii=False))
                ctx.close()
                sys.exit(1)

            if args.action == 'fetch':
                comments = fetch_comments(page, limit=args.limit)
                print(json.dumps(comments, ensure_ascii=False, indent=2))
            elif args.action == 'reply':
                results = auto_reply(page, limit=args.limit, style=args.style, dry_run=args.dry_run)
                print(format_reply_results(results))
                print("\n" + json.dumps(results, ensure_ascii=False, indent=2))

            ctx.close()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
