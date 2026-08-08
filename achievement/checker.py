"""成就判定核心，被异步任务和管理命令共用。

判定刻意做成"一次查询取全部候选 + 内存比对"，与 problemset 里逐条查询的
旧写法相反：一次判题只多 3~4 条 SQL。
"""

import logging

from django.db import transaction
from django.db.models import F

from achievement.metrics import META_METRICS, METRIC_REGISTRY, build_ctx
from achievement.models import Achievement, Operator, UserAchievement, UserStat

logger = logging.getLogger(__name__)


def evaluate(user, metrics, only_metrics=None):
    """返回该用户应解锁但尚未解锁的成就列表。"""
    unlocked_ids = set(UserAchievement.objects.filter(user=user).values_list("achievement_id", flat=True))
    qs = Achievement.objects.filter(visible=True).exclude(id__in=unlocked_ids)
    if only_metrics is not None:
        qs = qs.filter(metric__in=only_metrics)

    hits = []
    for achievement in qs:
        value = metrics.get(achievement.metric)
        # 指标从未产生有效值时 key 不存在，直接跳过：
        # 否则极小值型指标（求 min、配 lte 用的那种）会对新用户恒成立
        if value is None:
            continue
        if achievement.operator == Operator.GTE and value >= achievement.threshold:
            hits.append(achievement)
        elif achievement.operator == Operator.LTE and value <= achievement.threshold:
            hits.append(achievement)
    return hits


def unlock(user, achievements, backfilled=False, notified=False):
    """写入解锁记录并累加 unlock_count，返回实际新建的记录。

    刻意逐条 get_or_create 而不是 bulk_create：unique_user_achievement 约束负责
    并发竞态，was_created 是"这一条确实是我新建的"的唯一可信判据。用
    bulk_create(ignore_conflicts=True) 则无法区分新建与已存在，并发判题时会把
    unlock_count 重复累加（获得率永久偏高），并对同一个奖杯重复推送通知。

    循环次数是"本次新解锁的成就数"，常态为 0，因此常态零查询。
    """
    created = []
    for achievement in achievements:
        record, was_created = UserAchievement.objects.get_or_create(
            user=user,
            achievement=achievement,
            defaults={"backfilled": backfilled, "notified": notified},
        )
        if was_created:
            Achievement.objects.filter(id=achievement.id).update(unlock_count=F("unlock_count") + 1)
            created.append(record)
    return created


def run_for_submission(user, submission):
    """判题后的完整流程：更新指标 → 第一轮判定 → 元指标第二轮判定。"""
    ctx = build_ctx(user.id, submission)
    if ctx["skip"]:
        # 比赛提交不计入成就
        return []

    with transaction.atomic():
        stat = UserStat.objects.select_for_update().get_or_create(user=user)[0]
        for key, m in METRIC_REGISTRY.items():
            if key in META_METRICS:
                continue
            m.on_submission(stat.metrics, submission, ctx)
        stat.save(update_fields=["metrics", "update_time"])

    first = unlock(user, evaluate(user, stat.metrics))
    if not first:
        return []

    # 第二轮：只重算元指标、只判定依赖元指标的成就，不再有第三轮
    meta_values = {key: METRIC_REGISTRY[key].recompute(user) for key in META_METRICS}

    # 必须重新取锁并重新读一次 stat：上面那个 stat 对象的 metrics 是解锁前的快照，
    # 直接 save 会把整份字典写回，覆盖掉并发判题在这期间已提交的增量
    # （同一用户两次提交并发判题时会让提交数/AC 数静默倒退，且无定期重算兜底）。
    # 这里只合并元指标那几个 key。
    with transaction.atomic():
        stat = UserStat.objects.select_for_update().get(user=user)
        for key, value in meta_values.items():
            if value is None:
                stat.metrics.pop(key, None)
            else:
                stat.metrics[key] = value
        stat.save(update_fields=["metrics", "update_time"])

    second = unlock(user, evaluate(user, stat.metrics, only_metrics=META_METRICS))

    return first + second
