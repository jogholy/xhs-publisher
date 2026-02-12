#!/usr/bin/env python3
"""
小红书定时发布管理器
基于 OpenClaw cron 能力，封装定时发布任务的增删查改。
任务数据持久化到本地 JSON，同时通过 OpenClaw cron API 管理实际调度。
"""

import json
import sys
import time
import hashlib
from pathlib import Path
from datetime import datetime

SKILL_DIR = Path(__file__).parent.parent
SCHEDULE_FILE = SKILL_DIR / 'content' / 'schedules.json'
SCHEDULE_FILE.parent.mkdir(exist_ok=True)


def _load_schedules():
    """加载本地定时任务列表"""
    if not SCHEDULE_FILE.exists():
        return {}
    try:
        with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_schedules(data):
    """保存定时任务列表"""
    with open(SCHEDULE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _gen_id(topic, style):
    text = f"{topic}_{style}_{time.time()}"
    return 'xhs_' + hashlib.md5(text.encode()).hexdigest()[:8]


def _build_cron_message(topic, style='default', extra='', headless=True):
    """构建 cron agentTurn 的 message 文本"""
    parts = [f'发布一篇小红书笔记，主题是「{topic}」']
    if style != 'default':
        style_names = {
            'review': '测评种草',
            'tutorial': '干货教程',
            'daily': '日常分享',
        }
        parts.append(f'使用{style_names.get(style, style)}风格')
    if extra:
        parts.append(f'额外要求：{extra}')
    if headless:
        parts.append('使用 headless 模式')
    return '，'.join(parts)


def build_cron_job(task_id, topic, style='default', extra='',
                   schedule_kind='cron', cron_expr=None, at_ms=None,
                   every_ms=None, tz='Asia/Shanghai', headless=True, name=None):
    """
    构建 OpenClaw cron job 对象

    Args:
        task_id: 任务 ID
        topic: 发布主题
        style: 文案风格
        extra: 额外指令
        schedule_kind: 调度类型 (cron/at/every)
        cron_expr: cron 表达式 (schedule_kind=cron 时必填)
        at_ms: 一次性触发时间戳毫秒 (schedule_kind=at)
        every_ms: 循环间隔毫秒 (schedule_kind=every)
        tz: 时区
        headless: 是否无头模式
        name: 任务名称

    Returns:
        dict: OpenClaw cron job 对象
    """
    message = _build_cron_message(topic, style, extra, headless)

    # 构建 schedule
    if schedule_kind == 'cron':
        schedule = {'kind': 'cron', 'expr': cron_expr, 'tz': tz}
    elif schedule_kind == 'at':
        schedule = {'kind': 'at', 'atMs': at_ms}
    elif schedule_kind == 'every':
        schedule = {'kind': 'every', 'everyMs': every_ms}
    else:
        raise ValueError(f"不支持的调度类型: {schedule_kind}")

    return {
        'name': name or f'小红书定时发布: {topic}',
        'schedule': schedule,
        'payload': {
            'kind': 'agentTurn',
            'message': message,
        },
        'sessionTarget': 'isolated',
        'enabled': True,
    }


def add_task(topic, style='default', extra='', cron_expr=None,
             at_time=None, every_minutes=None, tz='Asia/Shanghai',
             headless=True, name=None):
    """
    添加定时发布任务

    Args:
        topic: 主题
        style: 风格
        extra: 额外指令
        cron_expr: cron 表达式 (如 "0 8 * * *")
        at_time: 一次性发布时间 ISO 格式 (如 "2026-02-13T10:00:00")
        every_minutes: 每隔 N 分钟发布一次
        tz: 时区
        headless: 无头模式
        name: 任务名称

    Returns:
        dict: 任务信息（含 task_id 和 cron_job）
    """
    task_id = _gen_id(topic, style)

    # 确定调度类型
    if cron_expr:
        schedule_kind = 'cron'
        at_ms = None
        every_ms = None
    elif at_time:
        schedule_kind = 'at'
        dt = datetime.fromisoformat(at_time)
        at_ms = int(dt.timestamp() * 1000)
        cron_expr = None
        every_ms = None
    elif every_minutes:
        schedule_kind = 'every'
        every_ms = every_minutes * 60 * 1000
        cron_expr = None
        at_ms = None
    else:
        raise ValueError("必须指定 cron_expr、at_time 或 every_minutes 之一")

    cron_job = build_cron_job(
        task_id=task_id,
        topic=topic,
        style=style,
        extra=extra,
        schedule_kind=schedule_kind,
        cron_expr=cron_expr,
        at_ms=at_ms,
        every_ms=every_ms,
        tz=tz,
        headless=headless,
        name=name,
    )

    # 保存本地记录
    schedules = _load_schedules()
    schedules[task_id] = {
        'task_id': task_id,
        'topic': topic,
        'style': style,
        'extra': extra,
        'schedule_kind': schedule_kind,
        'cron_expr': cron_expr,
        'at_time': at_time,
        'every_minutes': every_minutes,
        'tz': tz,
        'headless': headless,
        'name': name or f'小红书定时发布: {topic}',
        'cron_job_id': None,  # 由调用方填入 OpenClaw 返回的 jobId
        'created_at': datetime.now().isoformat(),
        'enabled': True,
    }
    _save_schedules(schedules)

    return {
        'task_id': task_id,
        'cron_job': cron_job,
        'local_record': schedules[task_id],
    }


def update_cron_job_id(task_id, cron_job_id):
    """更新任务的 cron job ID（OpenClaw 创建后回填）"""
    schedules = _load_schedules()
    if task_id in schedules:
        schedules[task_id]['cron_job_id'] = cron_job_id
        _save_schedules(schedules)
        return True
    return False


def remove_task(task_id):
    """删除本地任务记录，返回 cron_job_id 供调用方删除 OpenClaw cron"""
    schedules = _load_schedules()
    if task_id not in schedules:
        return None
    task = schedules.pop(task_id)
    _save_schedules(schedules)
    return task.get('cron_job_id')


def list_tasks():
    """列出所有定时任务"""
    return _load_schedules()


def get_task(task_id):
    """获取单个任务"""
    schedules = _load_schedules()
    return schedules.get(task_id)


def toggle_task(task_id, enabled):
    """启用/禁用任务"""
    schedules = _load_schedules()
    if task_id not in schedules:
        return None
    schedules[task_id]['enabled'] = enabled
    _save_schedules(schedules)
    return schedules[task_id]


def format_task_summary(task):
    """格式化任务摘要（用于展示）"""
    sched = ''
    if task.get('cron_expr'):
        sched = f"cron: {task['cron_expr']}"
    elif task.get('at_time'):
        sched = f"一次性: {task['at_time']}"
    elif task.get('every_minutes'):
        sched = f"每 {task['every_minutes']} 分钟"

    status = '✅ 启用' if task.get('enabled', True) else '⏸️ 暂停'
    style_names = {
        'default': '通用', 'review': '测评种草',
        'tutorial': '干货教程', 'daily': '日常分享',
    }
    style_label = style_names.get(task.get('style', 'default'), task.get('style', ''))

    return (
        f"[{task['task_id']}] {status} | {task.get('name', task['topic'])}\n"
        f"  主题: {task['topic']} | 风格: {style_label}\n"
        f"  调度: {sched} ({task.get('tz', 'Asia/Shanghai')})\n"
        f"  创建: {task.get('created_at', '?')}"
    )
