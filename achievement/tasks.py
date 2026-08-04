import logging

import dramatiq

from account.models import User
from achievement import checker
from achievement.notify import notify_achievements
from submission.models import Submission
from utils.shortcuts import DRAMATIQ_WORKER_ARGS

logger = logging.getLogger(__name__)


@dramatiq.actor(**DRAMATIQ_WORKER_ARGS())
def check_achievements(user_id, submission_id):
    """判题完成后的成就判定。

    所有异常在此吞掉：成就算错绝不能影响判题结果，这也是选异步的意义。
    """
    try:
        user = User.objects.get(id=user_id)
        submission = Submission.objects.get(id=submission_id)
        records = checker.run_for_submission(user, submission)
        notify_achievements(user_id, records)
    except Exception as e:
        logger.exception(f"check_achievements failed: user_id={user_id}, submission_id={submission_id}, error={e}")


@dramatiq.actor(**DRAMATIQ_WORKER_ARGS())
def rescan_achievement(achievement_id):
    """新建成就或调低阈值后，补发给已达标的存量用户。

    判定只在判题时发生，因此后台改了阈值不会自动补发，必须显式扫一遍。
    """
    from django.db.models import IntegerField
    from django.db.models.fields.json import KeyTextTransform
    from django.db.models.functions import Cast

    from achievement.models import Achievement, Operator, UserAchievement, UserStat

    try:
        achievement = Achievement.objects.get(id=achievement_id, visible=True)
    except Achievement.DoesNotExist:
        return

    # JSONField 的默认比较是 JSON 值比较，数字会按字符串序比（"9" > "50"），
    # 必须显式 cast 成整数，否则筛出来的用户是错的
    qs = UserStat.objects.filter(metrics__has_key=achievement.metric).annotate(v=Cast(KeyTextTransform(achievement.metric, "metrics"), IntegerField()))
    if achievement.operator == Operator.GTE:
        qs = qs.filter(v__gte=achievement.threshold)
    else:
        qs = qs.filter(v__lte=achievement.threshold)

    already = set(UserAchievement.objects.filter(achievement=achievement).values_list("user_id", flat=True))
    for stat in qs.select_related("user").iterator():
        if stat.user_id in already:
            continue
        try:
            # backfilled=True：这是补发，不是学生刚刚挣到的。
            # 前端据此只显示"已获得"而不显示具体日期——否则一次补发会给几百人
            # 盖上同一个时间戳，把"最近获得"板块彻底冲垮
            records = checker.unlock(stat.user, [achievement], backfilled=True)
            notify_achievements(stat.user_id, records)
        except Exception as e:
            logger.error(f"rescan_achievement failed for user {stat.user_id}: {e}")
