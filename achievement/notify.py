"""解锁通知。

通知走推拉结合，UserAchievement.notified 是唯一的真相来源：
- 拉（主）：前端在布局层拉 /api/achievements/pending，覆盖全部场景
- 推（增强）：WebSocket 只负责把"当场那一下"的延迟压到几百毫秒

必须推拉结合的原因：前端 WebSocket 不是常驻连接，useSubmissionWebSocket
只在问题页且有提交监听时建连，纯推会丢消息。
"""

import logging

from utils.websocket import push_to_user

logger = logging.getLogger(__name__)


def notify_achievements(user_id, records):
    """records: list[UserAchievement]，已带 select_related('achievement')。"""
    if not records:
        return
    payload = [
        {
            "id": r.achievement_id,
            "name": r.achievement.name,
            "description": r.achievement.description,
            "icon": r.achievement.icon,
            "rarity": r.achievement.rarity,
            "kind": "achievement",
        }
        for r in records
    ]
    _push(user_id, payload)


def notify_badges(user_id, badges):
    """badges: list[ProblemSetBadge]。题单奖章复用同一个弹窗组件。"""
    if not badges:
        return
    payload = [
        {
            "id": b.id,
            "name": b.name,
            "description": b.description,
            "icon": b.icon,
            "rarity": "bronze",
            "kind": "badge",
        }
        for b in badges
    ]
    _push(user_id, payload)


def _push(user_id, payload):
    # 推送失败不影响已入库的解锁记录，前端下次拉 pending 时仍会补弹
    try:
        push_to_user(user_id, "achievement_unlocked", {"achievements": payload})
    except Exception as e:
        logger.error(f"Failed to push achievement notification: user_id={user_id}, error={e}")
