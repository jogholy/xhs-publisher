#!/usr/bin/env python3
"""
小红书登录 - 长驻进程版
通过 stdin 接收命令，保持浏览器实例不关闭

命令:
  qr       - 生成/刷新二维码
  check    - 检查当前页面状态并截图
  verify XXXXXX - 输入短信验证码
  sms      - 走短信登录：输入手机号并发送验证码（需先 smsphone PHONE）
  smsphone 138XXXXXXXX - 设置手机号
  smslogin XXXXXX - 短信登录：输入验证码并点击登录
  quit     - 退出
"""
import sys, json, time
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

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

print('STARTING browser...', flush=True)

pw = sync_playwright().start()
ctx = pw.chromium.launch_persistent_context(
    user_data_dir=str(BROWSER_DATA),
    headless=True,
    viewport={'width': 1280, 'height': 900},
    device_scale_factor=2,
    locale='zh-CN',
    timezone_id='Asia/Shanghai',
    args=['--disable-blink-features=AutomationControlled', '--no-sandbox'],
    ignore_default_args=['--enable-automation'],
)
page = ctx.pages[0] if ctx.pages else ctx.new_page()

print('BROWSER_READY', flush=True)

phone_number = None

def do_qr():
    """导航到登录页并切换到扫码模式"""
    page.goto(XHS_LOGIN, wait_until='domcontentloaded', timeout=15000)
    time.sleep(5)

    # 检查是否已登录
    if '/login' not in page.url:
        shot = SCREENSHOTS / f'already_logged_{datetime.now():%Y%m%d_%H%M%S}.png'
        page.screenshot(path=str(shot))
        print(json.dumps({'action': 'qr', 'status': 'already_logged_in', 'screenshot': str(shot)}), flush=True)
        return

    # 切换到扫码模式
    qr_icon = page.locator('img.css-wemwzq').first
    if qr_icon.is_visible():
        qr_icon.click()
        time.sleep(3)

    shot = SCREENSHOTS / f'qr_{datetime.now():%Y%m%d_%H%M%S}.png'
    login_box = page.locator('.login-box-container').first
    if login_box.is_visible():
        login_box.screenshot(path=str(shot))
    else:
        page.screenshot(path=str(shot))

    print(json.dumps({'action': 'qr', 'status': 'qr_ready', 'screenshot': str(shot)}), flush=True)


def do_check():
    """检查当前页面状态"""
    time.sleep(1)
    url = page.url
    shot = SCREENSHOTS / f'check_{datetime.now():%Y%m%d_%H%M%S}.png'
    page.screenshot(path=str(shot), full_page=True)

    if '/login' not in url:
        print(json.dumps({'action': 'check', 'status': 'logged_in', 'url': url, 'screenshot': str(shot)}), flush=True)
        return

    body = page.text_content('body') or ''

    # 收集页面信息
    inputs_info = []
    inputs = page.locator('input')
    for i in range(inputs.count()):
        inp = inputs.nth(i)
        try:
            if inp.is_visible():
                ph = inp.get_attribute('placeholder') or ''
                inputs_info.append({'index': i, 'placeholder': ph})
        except:
            pass

    buttons_info = []
    buttons = page.locator('button')
    for i in range(buttons.count()):
        btn = buttons.nth(i)
        try:
            text = btn.text_content().strip()
            if btn.is_visible() and text:
                buttons_info.append({'index': i, 'text': text})
        except:
            pass

    print(json.dumps({
        'action': 'check',
        'status': 'on_login_page',
        'url': url,
        'body_preview': body[:300],
        'inputs': inputs_info,
        'buttons': buttons_info,
        'screenshot': str(shot)
    }), flush=True)


def do_verify(code):
    """输入短信验证码"""
    url = page.url

    if '/login' not in url:
        print(json.dumps({'action': 'verify', 'status': 'already_logged_in'}), flush=True)
        return

    # 查找验证码输入框
    code_filled = False
    inputs = page.locator('input')
    for i in range(inputs.count()):
        inp = inputs.nth(i)
        try:
            ph = inp.get_attribute('placeholder') or ''
            if '验证码' in ph and inp.is_visible():
                inp.click()
                inp.fill(code)
                code_filled = True
                break
        except:
            pass

    if not code_filled:
        # 尝试分格输入框
        visible_inputs = []
        for i in range(inputs.count()):
            inp = inputs.nth(i)
            try:
                if inp.is_visible():
                    ph = inp.get_attribute('placeholder') or ''
                    tp = inp.get_attribute('type') or ''
                    if tp in ('text', 'number', 'tel', '') and '手机' not in ph and '邮箱' not in ph and '选择' not in ph:
                        visible_inputs.append(inp)
            except:
                pass
        if visible_inputs:
            visible_inputs[0].click()
            visible_inputs[0].fill(code)
            code_filled = True

    time.sleep(1)

    # 点击登录/确认按钮
    clicked = False
    buttons = page.locator('button')
    for i in range(buttons.count()):
        btn = buttons.nth(i)
        try:
            text = btn.text_content().strip()
            if btn.is_visible() and any(kw in text for kw in ['登', '确认', '验证', '提交', '确定']):
                btn.click()
                clicked = True
                break
        except:
            pass

    time.sleep(5)

    shot = SCREENSHOTS / f'verify_{datetime.now():%Y%m%d_%H%M%S}.png'
    page.screenshot(path=str(shot), full_page=True)

    final_url = page.url
    logged_in = '/login' not in final_url

    print(json.dumps({
        'action': 'verify',
        'status': 'logged_in' if logged_in else 'still_on_login',
        'code_filled': code_filled,
        'button_clicked': clicked,
        'url': final_url,
        'screenshot': str(shot)
    }), flush=True)


def do_smsphone(phone):
    """设置手机号并发送验证码（短信登录方式）"""
    global phone_number
    phone_number = phone

    url = page.url
    if '/login' not in url:
        page.goto(XHS_LOGIN, wait_until='domcontentloaded', timeout=15000)
        time.sleep(5)

    # 确保在短信登录模式（默认就是）
    # 填入手机号
    phone_input = page.locator('input[placeholder="手机号"]').first
    if phone_input.is_visible():
        phone_input.click()
        phone_input.fill(phone)
        time.sleep(0.5)

        # 点击发送验证码
        send_btn = page.locator('text=发送验证码').first
        if send_btn.is_visible():
            send_btn.click()
            time.sleep(2)

    shot = SCREENSHOTS / f'sms_{datetime.now():%Y%m%d_%H%M%S}.png'
    page.screenshot(path=str(shot), full_page=True)

    print(json.dumps({
        'action': 'smsphone',
        'status': 'sms_sent',
        'phone': phone[:3] + '****' + phone[-4:] if len(phone) >= 7 else '***',
        'screenshot': str(shot)
    }), flush=True)


def do_smslogin(code):
    """短信登录：输入验证码并点击登录"""
    # 填入验证码
    code_input = page.locator('input[placeholder="验证码"]').first
    if code_input.is_visible():
        code_input.click()
        code_input.fill(code)
        time.sleep(0.5)

    # 点击登录
    login_btn = page.locator('button:has-text("登")').first
    if login_btn.is_visible():
        login_btn.click()
        time.sleep(5)

    shot = SCREENSHOTS / f'smslogin_{datetime.now():%Y%m%d_%H%M%S}.png'
    page.screenshot(path=str(shot), full_page=True)

    final_url = page.url
    logged_in = '/login' not in final_url

    print(json.dumps({
        'action': 'smslogin',
        'status': 'logged_in' if logged_in else 'still_on_login',
        'url': final_url,
        'screenshot': str(shot)
    }), flush=True)


# 主循环：从 stdin 读取命令
print('READY - 输入命令: qr / check / verify CODE / smsphone PHONE / smslogin CODE / quit', flush=True)

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue

    parts = line.split(None, 1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ''

    try:
        if cmd == 'qr':
            do_qr()
        elif cmd == 'check':
            do_check()
        elif cmd == 'verify':
            if not arg:
                print('ERROR: verify 需要验证码参数', flush=True)
            else:
                do_verify(arg)
        elif cmd == 'smsphone':
            if not arg:
                print('ERROR: smsphone 需要手机号参数', flush=True)
            else:
                do_smsphone(arg)
        elif cmd == 'smslogin':
            if not arg:
                print('ERROR: smslogin 需要验证码参数', flush=True)
            else:
                do_smslogin(arg)
        elif cmd == 'quit':
            print('QUITTING', flush=True)
            break
        else:
            print(f'UNKNOWN_CMD: {cmd}', flush=True)
    except Exception as e:
        print(json.dumps({'action': cmd, 'error': str(e)}), flush=True)

ctx.close()
pw.stop()
print('DONE', flush=True)
