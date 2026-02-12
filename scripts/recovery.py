#!/usr/bin/env python3
"""
错误恢复模块
提供自动重试、超时恢复、现场截图保存等能力。
"""

import time
import logging
import functools
from datetime import datetime
from pathlib import Path

log = logging.getLogger('xhs')

SKILL_DIR = Path(__file__).parent.parent
SCREENSHOTS_DIR = SKILL_DIR / 'screenshots'
SCREENSHOTS_DIR.mkdir(exist_ok=True)


def save_error_snapshot(page, label='error'):
    """保存错误现场截图，返回路径"""
    try:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = SCREENSHOTS_DIR / f'{label}_{ts}.png'
        page.screenshot(path=str(path), full_page=True)
        log.info(f'错误现场截图: {path}')
        return str(path)
    except Exception as e:
        log.warning(f'截图失败: {e}')
        return None


def retry(max_retries=3, delay=5, backoff=2, recoverable_errors=None):
    """
    重试装饰器

    Args:
        max_retries: 最大重试次数
        delay: 初始延迟秒数
        backoff: 延迟倍增系数
        recoverable_errors: 可恢复的异常类型元组（默认全部）
    """
    if recoverable_errors is None:
        recoverable_errors = (Exception,)

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            current_delay = delay

            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except recoverable_errors as e:
                    last_error = e
                    if attempt < max_retries:
                        log.warning(
                            f'[重试 {attempt}/{max_retries}] {func.__name__} 失败: {e}，'
                            f'{current_delay}秒后重试...'
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        log.error(f'[重试耗尽] {func.__name__} 在 {max_retries} 次尝试后仍失败: {e}')

            raise last_error
        return wrapper
    return decorator


def safe_navigate(page, url, timeout=15000, retries=3):
    """
    安全导航：带重试的页面跳转

    Args:
        page: Playwright page
        url: 目标 URL
        timeout: 超时毫秒
        retries: 重试次数
    """
    for attempt in range(1, retries + 1):
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=timeout)
            return True
        except Exception as e:
            log.warning(f'导航失败 (第{attempt}次): {url} - {e}')
            if attempt < retries:
                time.sleep(3)
                # 尝试刷新或重新导航
                try:
                    page.reload(timeout=timeout)
                except Exception:
                    pass
            else:
                save_error_snapshot(page, 'nav_fail')
                raise


def safe_click(page, selector, timeout=5000, retries=2, label='元素'):
    """
    安全点击：带重试和 fallback 的元素点击

    Args:
        page: Playwright page
        selector: CSS 选择器
        timeout: 等待超时毫秒
        retries: 重试次数
        label: 元素描述（用于日志）
    """
    for attempt in range(1, retries + 1):
        try:
            el = page.locator(selector).first
            el.wait_for(state='visible', timeout=timeout)
            el.click()
            return True
        except Exception as e:
            if attempt < retries:
                log.warning(f'点击{label}失败 (第{attempt}次): {e}，重试...')
                time.sleep(2)
            else:
                log.warning(f'点击{label}失败: {e}')
                return False


def safe_fill(page, selector, text, timeout=5000, retries=2, label='输入框'):
    """
    安全填写：带重试的文本输入

    Args:
        page: Playwright page
        selector: CSS 选择器
        text: 要填写的文本
        timeout: 等待超时毫秒
        retries: 重试次数
        label: 元素描述
    """
    for attempt in range(1, retries + 1):
        try:
            el = page.locator(selector).first
            el.wait_for(state='visible', timeout=timeout)
            el.click()
            el.fill(text)
            return True
        except Exception as e:
            if attempt < retries:
                log.warning(f'填写{label}失败 (第{attempt}次): {e}，重试...')
                time.sleep(2)
            else:
                log.warning(f'填写{label}失败: {e}')
                return False


def check_page_health(page):
    """
    检查页面健康状态

    Returns:
        dict: {ok: bool, url: str, error: str?}
    """
    try:
        url = page.url
        # 检查是否在错误页面
        if 'error' in url or 'about:blank' in url:
            return {'ok': False, 'url': url, 'error': '页面异常'}
        # 检查页面是否可交互
        page.evaluate('() => document.readyState')
        return {'ok': True, 'url': url}
    except Exception as e:
        return {'ok': False, 'url': '', 'error': str(e)}


def recover_page(page, target_url):
    """
    尝试恢复页面到目标 URL

    Returns:
        bool: 是否恢复成功
    """
    health = check_page_health(page)
    if health['ok'] and target_url in health.get('url', ''):
        return True

    log.info(f'页面需要恢复，当前: {health.get("url", "unknown")}，目标: {target_url}')
    try:
        safe_navigate(page, target_url)
        time.sleep(3)
        return True
    except Exception as e:
        log.error(f'页面恢复失败: {e}')
        return False
