#!/usr/bin/env python3
"""
浏览器反检测模块
提供 UA 随机化、viewport 随机化、指纹伪装、webdriver 属性隐藏等能力。
"""

import random

# ─── UA 池 ──────────────────────────────────────────────────

_CHROME_VERSIONS = [
    '120.0.6099.109', '120.0.6099.199', '121.0.6167.85',
    '122.0.6261.94', '123.0.6312.58', '124.0.6367.91',
    '125.0.6422.76', '126.0.6478.114', '127.0.6533.72',
    '128.0.6613.84', '129.0.6668.58', '130.0.6723.91',
    '131.0.6778.85',
]

_PLATFORMS = [
    ('Windows NT 10.0; Win64; x64', 'Windows'),
    ('Macintosh; Intel Mac OS X 10_15_7', 'macOS'),
    ('X11; Linux x86_64', 'Linux'),
]


def random_user_agent():
    """生成随机但合理的 Chrome UA"""
    chrome_ver = random.choice(_CHROME_VERSIONS)
    platform, _ = random.choice(_PLATFORMS)
    return (
        f'Mozilla/5.0 ({platform}) AppleWebKit/537.36 '
        f'(KHTML, like Gecko) Chrome/{chrome_ver} Safari/537.36'
    )


# ─── Viewport 随机化 ────────────────────────────────────────

_VIEWPORTS = [
    (1366, 768), (1440, 900), (1536, 864), (1600, 900),
    (1920, 1080), (1280, 800), (1280, 720), (1360, 768),
    (1680, 1050), (1280, 1024),
]


def random_viewport():
    """返回随机的常见屏幕分辨率"""
    w, h = random.choice(_VIEWPORTS)
    # 微调 ±几个像素，避免精确匹配指纹库
    w += random.randint(-10, 10)
    h += random.randint(-5, 5)
    return {'width': w, 'height': h}


# ─── 指纹伪装注入脚本 ──────────────────────────────────────

STEALTH_JS = '''
// 1. 隐藏 webdriver 属性
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
});

// 2. 伪装 plugins（正常浏览器有插件）
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
            { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
        ];
        plugins.length = 3;
        return plugins;
    },
});

// 3. 伪装 languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['zh-CN', 'zh', 'en-US', 'en'],
});

// 4. 修复 chrome.runtime（Playwright 缺失）
if (!window.chrome) window.chrome = {};
if (!window.chrome.runtime) {
    window.chrome.runtime = {
        connect: function() {},
        sendMessage: function() {},
    };
}

// 5. 伪装 permissions query
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);

// 6. WebGL 渲染器伪装
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    // UNMASKED_VENDOR_WEBGL
    if (parameter === 37445) return 'Google Inc. (NVIDIA)';
    // UNMASKED_RENDERER_WEBGL
    if (parameter === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)';
    return getParameter.call(this, parameter);
};

// 7. 修复 iframe contentWindow
const originalAttachShadow = Element.prototype.attachShadow;
Element.prototype.attachShadow = function() {
    return originalAttachShadow.apply(this, arguments);
};

// 8. 隐藏 Playwright 特征
delete window.__playwright;
delete window.__pw_manual;
'''


def get_stealth_args():
    """返回 Chromium 启动参数（反检测）"""
    return [
        '--disable-blink-features=AutomationControlled',
        '--no-sandbox',
        '--disable-infobars',
        '--disable-dev-shm-usage',
        '--disable-extensions',
        '--disable-gpu',
        '--lang=zh-CN',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-popup-blocking',
    ]


def get_stealth_ignore_args():
    """返回需要忽略的默认参数"""
    return [
        '--enable-automation',
        '--enable-blink-features=IdleDetection',
    ]


def apply_stealth(context):
    """
    对浏览器上下文注入反检测脚本。
    在每个新页面创建时自动执行。
    """
    context.add_init_script(STEALTH_JS)
    return context
