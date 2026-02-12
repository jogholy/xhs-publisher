#!/usr/bin/env python3
"""
小红书交互式登录 - 分步执行
用法:
  step1: python3 xhs_login_interactive.py qr        # 生成二维码
  step2: python3 xhs_login_interactive.py check      # 检查扫码后状态
  step3: python3 xhs_login_interactive.py verify CODE # 输入短信验证码
  step4: python3 xhs_login_interactive.py status     # 确认登录成功
"""
import sys, os, json, time
sys.stdout.reconfigure(line_buffering=True)

from playwright.sync_api import sync_playwright
from pathlib import Path
from datetime import datetime

SKILL_DIR = Path(__file__).parent.parent
BROWSER_DATA = SKILL_DIR / 'browser_data'
SCREENSHOTS = SKILL_DIR / 'screenshots'
for d in [BROWSER_DATA, SCREENSHOTS]:
    d.mkdir(exist_ok=True)

XHS_LOGIN = 'https://creator.xiaohongshu.com/login'
XHS_CREATOR = 'https://creator.xiaohongshu.com'


def get_context(pw, headless=True):
    return pw.chromium.launch_persistent_context(
        user_data_dir=str(BROWSER_DATA),
        headless=headless,
        viewport={'width': 1280, 'height': 900},
        device_scale_factor=2,
        locale='zh-CN',
        timezone_id='Asia/Shanghai',
        args=['--disable-blink-features=AutomationControlled', '--no-sandbox'],
        ignore_default_args=['--enable-automation'],
    )


def cmd_qr():
    """生成扫码登录二维码"""
    with sync_playwright() as pw:
        ctx = get_context(pw)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(XHS_LOGIN, wait_until='domcontentloaded', timeout=15000)
        time.sleep(5)

        # 切换到扫码模式
        qr_icon = page.locator('img.css-wemwzq').first
        if qr_icon.is_visible():
            qr_icon.click()
            time.sleep(3)

        # 截图
        shot = SCREENSHOTS / f'qr_{datetime.now():%Y%m%d_%H%M%S}.png'
        login_box = page.locator('.login-box-container').first
        if login_box.is_visible():
            login_box.screenshot(path=str(shot))
        else:
            page.screenshot(path=str(shot))

        print(json.dumps({
            'step': 'qr',
            'success': True,
            'screenshot': str(shot),
            'message': '请用小红书APP扫码'
        }, ensure_ascii=False))
        ctx.close()


def cmd_check():
    """扫码后检查页面状态"""
    with sync_playwright() as pw:
        ctx = get_context(pw)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(XHS_LOGIN, wait_until='domcontentloaded', timeout=15000)
        time.sleep(5)

        url = page.url
        shot = SCREENSHOTS / f'check_{datetime.now():%Y%m%d_%H%M%S}.png'
        page.screenshot(path=str(shot), full_page=True)

        if '/login' not in url:
            print(json.dumps({
                'step': 'check',
                'success': True,
                'status': 'logged_in',
                'url': url,
                'screenshot': str(shot)
            }, ensure_ascii=False))
            ctx.close()
            return

        # 分析页面内容
        body = page.text_content('body') or ''

        # 查找所有 input 元素
        inputs_info = []
        inputs = page.locator('input')
        for i in range(inputs.count()):
            inp = inputs.nth(i)
            try:
                ph = inp.get_attribute('placeholder') or ''
                tp = inp.get_attribute('type') or ''
                cls = inp.get_attribute('class') or ''
                vis = inp.is_visible()
                inputs_info.append({
                    'index': i,
                    'placeholder': ph,
                    'type': tp,
                    'class': cls[:60],
                    'visible': vis
                })
            except:
                pass

        # 查找按钮
        buttons_info = []
        buttons = page.locator('button')
        for i in range(buttons.count()):
            btn = buttons.nth(i)
            try:
                text = btn.text_content().strip()
                vis = btn.is_visible()
                if text and vis:
                    buttons_info.append({'index': i, 'text': text})
            except:
                pass

        print(json.dumps({
            'step': 'check',
            'success': True,
            'status': 'need_action',
            'url': url,
            'body_preview': body[:300],
            'inputs': inputs_info,
            'buttons': buttons_info,
            'screenshot': str(shot)
        }, ensure_ascii=False))
        ctx.close()


def cmd_verify(code):
    """输入短信验证码"""
    with sync_playwright() as pw:
        ctx = get_context(pw)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(XHS_LOGIN, wait_until='domcontentloaded', timeout=15000)
        time.sleep(5)

        url = page.url
        shot_before = SCREENSHOTS / f'verify_before_{datetime.now():%Y%m%d_%H%M%S}.png'
        page.screenshot(path=str(shot_before), full_page=True)

        if '/login' not in url:
            print(json.dumps({
                'step': 'verify',
                'success': True,
                'status': 'already_logged_in',
                'url': url
            }, ensure_ascii=False))
            ctx.close()
            return

        # 查找验证码输入框
        code_filled = False

        # 方式1: 查找 placeholder 包含"验证码"的 input
        inputs = page.locator('input')
        for i in range(inputs.count()):
            inp = inputs.nth(i)
            try:
                ph = inp.get_attribute('placeholder') or ''
                if '验证码' in ph or 'code' in ph.lower():
                    inp.click()
                    inp.fill(code)
                    code_filled = True
                    print(f'已在 input[{i}] placeholder="{ph}" 中填入验证码')
                    break
            except:
                pass

        # 方式2: 如果是分格输入框（每个数字一个格子）
        if not code_filled:
            # 有些验证码是6个独立的input
            visible_inputs = []
            for i in range(inputs.count()):
                inp = inputs.nth(i)
                try:
                    if inp.is_visible():
                        tp = inp.get_attribute('type') or ''
                        ph = inp.get_attribute('placeholder') or ''
                        if tp in ('text', 'number', 'tel', '') and not ph.startswith('+'):
                            visible_inputs.append(inp)
                except:
                    pass

            if len(visible_inputs) >= 4:
                # 可能是分格验证码
                for j, ch in enumerate(code):
                    if j < len(visible_inputs):
                        visible_inputs[j].click()
                        visible_inputs[j].fill(ch)
                        time.sleep(0.1)
                code_filled = True
                print(f'已在 {len(code)} 个分格输入框中填入验证码')

        # 方式3: 直接键盘输入
        if not code_filled:
            page.keyboard.type(code, delay=100)
            code_filled = True
            print('已通过键盘输入验证码')

        time.sleep(2)

        # 尝试点击确认/登录按钮
        buttons = page.locator('button')
        for i in range(buttons.count()):
            btn = buttons.nth(i)
            try:
                text = btn.text_content().strip()
                if btn.is_visible() and any(kw in text for kw in ['登', '确认', '验证', '提交', '确定']):
                    btn.click()
                    print(f'已点击按钮: {text}')
                    break
            except:
                pass

        time.sleep(5)

        shot_after = SCREENSHOTS / f'verify_after_{datetime.now():%Y%m%d_%H%M%S}.png'
        page.screenshot(path=str(shot_after), full_page=True)

        final_url = page.url
        logged_in = '/login' not in final_url

        print(json.dumps({
            'step': 'verify',
            'success': logged_in,
            'status': 'logged_in' if logged_in else 'still_on_login',
            'url': final_url,
            'code_filled': code_filled,
            'screenshot_before': str(shot_before),
            'screenshot_after': str(shot_after)
        }, ensure_ascii=False))
        ctx.close()


def cmd_status():
    """检查登录状态"""
    with sync_playwright() as pw:
        ctx = get_context(pw)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(XHS_CREATOR, wait_until='domcontentloaded', timeout=15000)
        time.sleep(3)

        url = page.url
        logged_in = '/login' not in url

        shot = SCREENSHOTS / f'status_{datetime.now():%Y%m%d_%H%M%S}.png'
        page.screenshot(path=str(shot))

        print(json.dumps({
            'step': 'status',
            'logged_in': logged_in,
            'url': url,
            'screenshot': str(shot)
        }, ensure_ascii=False))
        ctx.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python3 xhs_login_interactive.py [qr|check|verify CODE|status]')
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == 'qr':
        cmd_qr()
    elif cmd == 'check':
        cmd_check()
    elif cmd == 'verify':
        if len(sys.argv) < 3:
            print('请提供验证码: python3 xhs_login_interactive.py verify 123456')
            sys.exit(1)
        cmd_verify(sys.argv[2])
    elif cmd == 'status':
        cmd_status()
    else:
        print(f'未知命令: {cmd}')
        sys.exit(1)
