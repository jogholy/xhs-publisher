#!/usr/bin/env python3
"""
API Key 加密存储模块
使用 Fernet 对称加密，密钥派生自机器指纹 + 用户自定义密码。
支持加密/解密/迁移明文 Key。
"""

import base64
import hashlib
import json
import os
import sys
import getpass
from pathlib import Path

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

SKILL_DIR = Path(__file__).parent.parent
KEYS_FILE = SKILL_DIR / 'keys.enc'
SALT_FILE = SKILL_DIR / '.salt'


def _get_machine_id():
    """获取机器指纹作为盐的一部分"""
    candidates = [
        '/etc/machine-id',
        '/var/lib/dbus/machine-id',
    ]
    for p in candidates:
        if os.path.exists(p):
            with open(p, 'r') as f:
                return f.read().strip()
    # fallback: hostname + user
    import socket
    return f'{socket.gethostname()}_{os.getuid()}'


def _get_salt():
    """获取或生成盐值"""
    if SALT_FILE.exists():
        return SALT_FILE.read_bytes()
    salt = os.urandom(16)
    SALT_FILE.write_bytes(salt)
    SALT_FILE.chmod(0o600)
    return salt


def _derive_key(password=''):
    """从密码 + 机器指纹派生加密密钥"""
    if not HAS_CRYPTO:
        raise RuntimeError('需要安装 cryptography: pip3 install cryptography')

    machine_id = _get_machine_id()
    combined = f'{password}:{machine_id}'.encode()
    salt = _get_salt()

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(combined))
    return Fernet(key)


def encrypt_keys(keys_dict, password=''):
    """
    加密 API Key 字典并保存到 keys.enc

    Args:
        keys_dict: {'bailian_api_key': '...', 'gemini_api_key': '...', ...}
        password: 可选密码（空则仅依赖机器指纹）
    """
    fernet = _derive_key(password)
    plaintext = json.dumps(keys_dict, ensure_ascii=False).encode()
    encrypted = fernet.encrypt(plaintext)

    KEYS_FILE.write_bytes(encrypted)
    KEYS_FILE.chmod(0o600)
    return str(KEYS_FILE)


def decrypt_keys(password=''):
    """
    解密 keys.enc 并返回 Key 字典

    Returns:
        dict: {'bailian_api_key': '...', ...}
    Raises:
        FileNotFoundError: keys.enc 不存在
        InvalidToken: 密码错误
    """
    if not KEYS_FILE.exists():
        raise FileNotFoundError(f'加密文件不存在: {KEYS_FILE}')

    fernet = _derive_key(password)
    encrypted = KEYS_FILE.read_bytes()
    plaintext = fernet.decrypt(encrypted)
    return json.loads(plaintext.decode())


def get_api_key(key_name, password=''):
    """
    获取单个 API Key（优先加密文件，fallback 到 openclaw.json 明文）

    Args:
        key_name: Key 名称 (如 'bailian_api_key', 'gemini_api_key')
        password: 解密密码

    Returns:
        str or None
    """
    # 1. 尝试从加密文件读取
    if KEYS_FILE.exists():
        try:
            keys = decrypt_keys(password)
            if key_name in keys:
                return keys[key_name]
        except Exception:
            pass

    # 2. Fallback: 从 openclaw.json 读取
    return _read_from_openclaw_config(key_name)


def _read_from_openclaw_config(key_name):
    """从 openclaw.json 读取明文 API Key"""
    config_paths = [
        Path.home() / '.openclaw' / 'openclaw.json',
        Path.home() / '.openclaw' / 'config.json',
    ]
    key_map = {
        'bailian_api_key': ['models.providers.bailian.apiKey'],
        'gemini_api_key': ['skills.entries.nano-banana-pro.apiKey'],
    }

    paths = key_map.get(key_name, [])

    for config_path in config_paths:
        if not config_path.exists():
            continue
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            for dotpath in paths:
                val = config
                for part in dotpath.split('.'):
                    val = val.get(part, {}) if isinstance(val, dict) else None
                    if val is None:
                        break
                if val and isinstance(val, str):
                    return val
        except Exception:
            continue
    return None


def migrate_to_encrypted(password=''):
    """
    将 openclaw.json 中的明文 API Key 迁移到加密存储。
    不会删除原始配置（由用户手动清理）。

    Returns:
        dict: 迁移结果
    """
    keys_to_migrate = ['bailian_api_key', 'gemini_api_key']
    migrated = {}

    for key_name in keys_to_migrate:
        val = _read_from_openclaw_config(key_name)
        if val:
            migrated[key_name] = val

    if not migrated:
        return {'success': False, 'error': '未找到可迁移的 API Key'}

    path = encrypt_keys(migrated, password)
    return {
        'success': True,
        'migrated_keys': list(migrated.keys()),
        'encrypted_file': path,
        'message': '已加密保存。建议从 openclaw.json 中移除明文 API Key。',
    }


# ─── CLI ────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description='API Key 加密管理')
    sub = parser.add_subparsers(dest='action', help='操作')

    sub.add_parser('migrate', help='从 openclaw.json 迁移明文 Key 到加密存储')
    sub.add_parser('list', help='列出已加密的 Key 名称')
    sub.add_parser('status', help='检查加密存储状态')

    p_set = sub.add_parser('set', help='设置/更新一个 Key')
    p_set.add_argument('key_name', help='Key 名称')
    p_set.add_argument('key_value', nargs='?', help='Key 值（不提供则交互输入）')

    p_get = sub.add_parser('get', help='获取一个 Key')
    p_get.add_argument('key_name', help='Key 名称')

    args = parser.parse_args()
    password = os.environ.get('XHS_KEY_PASSWORD', '')

    if args.action == 'status':
        print(json.dumps({
            'encrypted_file_exists': KEYS_FILE.exists(),
            'encrypted_file': str(KEYS_FILE),
            'has_cryptography': HAS_CRYPTO,
            'salt_exists': SALT_FILE.exists(),
        }, ensure_ascii=False, indent=2))

    elif args.action == 'migrate':
        result = migrate_to_encrypted(password)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == 'list':
        if not KEYS_FILE.exists():
            print(json.dumps({'keys': [], 'message': '尚未创建加密存储'}, ensure_ascii=False))
            return
        try:
            keys = decrypt_keys(password)
            # 只显示名称，不显示值
            masked = {k: v[:4] + '***' + v[-4:] if len(v) > 8 else '***' for k, v in keys.items()}
            print(json.dumps({'keys': masked}, ensure_ascii=False, indent=2))
        except Exception as e:
            print(json.dumps({'error': str(e)}, ensure_ascii=False))

    elif args.action == 'set':
        value = args.key_value
        if not value:
            value = getpass.getpass(f'输入 {args.key_name} 的值: ')
        # 读取现有 keys 或创建新的
        existing = {}
        if KEYS_FILE.exists():
            try:
                existing = decrypt_keys(password)
            except Exception:
                pass
        existing[args.key_name] = value
        path = encrypt_keys(existing, password)
        print(json.dumps({'success': True, 'key': args.key_name, 'file': path}, ensure_ascii=False))

    elif args.action == 'get':
        val = get_api_key(args.key_name, password)
        if val:
            print(json.dumps({'key': args.key_name, 'value': val[:4] + '***'}, ensure_ascii=False))
        else:
            print(json.dumps({'key': args.key_name, 'error': '未找到'}, ensure_ascii=False))

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
