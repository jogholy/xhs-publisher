#!/usr/bin/env python3
"""
小红书多账号管理系统
支持添加、切换、删除多个小红书账号，每个账号独立的浏览器数据目录
"""

import os
import json
import argparse
from pathlib import Path
from datetime import datetime

# 路径常量
SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / 'data'
ACCOUNTS_FILE = DATA_DIR / 'accounts.json'
BROWSER_DATA_DIR = SKILL_DIR / 'browser_data'

# 确保目录存在
DATA_DIR.mkdir(exist_ok=True)
BROWSER_DATA_DIR.mkdir(exist_ok=True)


def load_accounts():
    """加载账号数据"""
    if not ACCOUNTS_FILE.exists():
        return {'accounts': {}, 'current': None}
    
    try:
        with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {'accounts': {}, 'current': None}


def save_accounts(data):
    """保存账号数据"""
    with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_account(account_id, name):
    """
    添加新账号
    
    Args:
        account_id: 账号ID（唯一标识）
        name: 账号显示名称
    
    Returns:
        dict: 操作结果
    """
    data = load_accounts()
    
    if account_id in data['accounts']:
        return {
            'success': False,
            'error': f'账号 {account_id} 已存在'
        }
    
    # 创建账号记录
    account = {
        'id': account_id,
        'name': name,
        'browser_data_dir': str(BROWSER_DATA_DIR / account_id),
        'created_at': datetime.now().isoformat(),
        'last_used_at': None
    }
    
    # 创建独立的浏览器数据目录
    account_browser_dir = Path(account['browser_data_dir'])
    account_browser_dir.mkdir(parents=True, exist_ok=True)
    
    data['accounts'][account_id] = account
    
    # 如果是第一个账号，设为当前账号
    if not data['current']:
        data['current'] = account_id
    
    save_accounts(data)
    
    return {
        'success': True,
        'account': account,
        'message': f'账号 {name} ({account_id}) 添加成功'
    }


def list_accounts():
    """列出所有账号"""
    data = load_accounts()
    accounts = []
    
    for account_id, account in data['accounts'].items():
        account_info = account.copy()
        account_info['is_current'] = (account_id == data['current'])
        accounts.append(account_info)
    
    return {
        'accounts': accounts,
        'current': data['current'],
        'count': len(accounts)
    }


def switch_account(account_id):
    """
    切换当前账号
    
    Args:
        account_id: 要切换到的账号ID
    
    Returns:
        dict: 操作结果
    """
    data = load_accounts()
    
    if account_id not in data['accounts']:
        return {
            'success': False,
            'error': f'账号 {account_id} 不存在'
        }
    
    # 更新当前账号
    old_current = data['current']
    data['current'] = account_id
    
    # 更新最后使用时间
    data['accounts'][account_id]['last_used_at'] = datetime.now().isoformat()
    
    save_accounts(data)
    
    return {
        'success': True,
        'old_current': old_current,
        'new_current': account_id,
        'account': data['accounts'][account_id],
        'message': f'已切换到账号: {data["accounts"][account_id]["name"]} ({account_id})'
    }


def remove_account(account_id, keep_data=False):
    """
    删除账号
    
    Args:
        account_id: 要删除的账号ID
        keep_data: 是否保留浏览器数据目录
    
    Returns:
        dict: 操作结果
    """
    data = load_accounts()
    
    if account_id not in data['accounts']:
        return {
            'success': False,
            'error': f'账号 {account_id} 不存在'
        }
    
    account = data['accounts'][account_id]
    
    # 删除浏览器数据目录（如果不保留）
    if not keep_data:
        browser_dir = Path(account['browser_data_dir'])
        if browser_dir.exists():
            import shutil
            try:
                shutil.rmtree(browser_dir)
            except Exception as e:
                print(f"警告：删除浏览器数据目录失败: {e}")
    
    # 从账号列表中删除
    del data['accounts'][account_id]
    
    # 如果删除的是当前账号，切换到其他账号
    if data['current'] == account_id:
        if data['accounts']:
            # 切换到第一个可用账号
            data['current'] = list(data['accounts'].keys())[0]
        else:
            data['current'] = None
    
    save_accounts(data)
    
    return {
        'success': True,
        'removed_account': account,
        'new_current': data['current'],
        'data_kept': keep_data,
        'message': f'账号 {account["name"]} ({account_id}) 已删除'
    }


def get_current_account():
    """获取当前账号信息"""
    data = load_accounts()
    
    if not data['current']:
        return {
            'current': None,
            'message': '未设置当前账号'
        }
    
    if data['current'] not in data['accounts']:
        # 当前账号不存在，重置
        data['current'] = None
        save_accounts(data)
        return {
            'current': None,
            'message': '当前账号已失效，已重置'
        }
    
    account = data['accounts'][data['current']]
    return {
        'current': data['current'],
        'account': account,
        'message': f'当前账号: {account["name"]} ({data["current"]})'
    }


def get_account_browser_dir(account_id=None):
    """
    获取指定账号的浏览器数据目录
    
    Args:
        account_id: 账号ID，不指定则使用当前账号
    
    Returns:
        str: 浏览器数据目录路径
    """
    data = load_accounts()
    
    if not account_id:
        account_id = data['current']
    
    if not account_id:
        # 没有当前账号，使用默认目录
        return str(BROWSER_DATA_DIR / 'default')
    
    if account_id not in data['accounts']:
        # 账号不存在，使用默认目录
        return str(BROWSER_DATA_DIR / 'default')
    
    return data['accounts'][account_id]['browser_data_dir']


# ─── CLI ────────────────────────────────────────────────────

def cmd_add(args):
    """添加账号命令"""
    result = add_account(args.account_id, args.name)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['success'] else 1


def cmd_list(args):
    """列出账号命令"""
    result = list_accounts()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_switch(args):
    """切换账号命令"""
    result = switch_account(args.account_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['success'] else 1


def cmd_remove(args):
    """删除账号命令"""
    result = remove_account(args.account_id, keep_data=args.keep_data)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['success'] else 1


def cmd_current(args):
    """查看当前账号命令"""
    result = get_current_account()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(description='小红书多账号管理')
    sub = parser.add_subparsers(dest='command', help='可用命令')

    # add
    p_add = sub.add_parser('add', help='添加账号')
    p_add.add_argument('account_id', help='账号ID（唯一标识）')
    p_add.add_argument('name', help='账号显示名称')

    # list
    sub.add_parser('list', help='列出所有账号')

    # switch
    p_switch = sub.add_parser('switch', help='切换当前账号')
    p_switch.add_argument('account_id', help='要切换到的账号ID')

    # remove
    p_remove = sub.add_parser('remove', help='删除账号')
    p_remove.add_argument('account_id', help='要删除的账号ID')
    p_remove.add_argument('--keep-data', action='store_true', help='保留浏览器数据目录')

    # current
    sub.add_parser('current', help='查看当前账号')

    args = parser.parse_args()

    if args.command == 'add':
        return cmd_add(args)
    elif args.command == 'list':
        return cmd_list(args)
    elif args.command == 'switch':
        return cmd_switch(args)
    elif args.command == 'remove':
        return cmd_remove(args)
    elif args.command == 'current':
        return cmd_current(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main())