from django.db.models import Count

from account.decorators import login_required
from account.models import User
from achievement.models import Achievement, Rarity, UserAchievement, UserStat
from achievement.serializers import AchievementSerializer, PendingAchievementSerializer
from utils.api import APIView


def _resolve_user(request):
    """?name=<username> 指定他人，不传则为自己。与 /api/profile 的约定一致。"""
    username = request.GET.get("name")
    if username:
        return User.objects.filter(username=username, is_disabled=False).first()
    return request.user


def _decorate(achievements, unlocked_map, metrics):
    """给成就对象挂上该用户的解锁状态与进度，供序列化器读取。"""
    for a in achievements:
        record = unlocked_map.get(a.id)
        a.unlocked = record is not None
        a.unlock_time = record.unlock_time if record else None
        a.backfilled = record.backfilled if record else False
        value = metrics.get(a.metric)
        # 隐藏且未解锁的成就不下发进度，否则能反推出条件
        a.progress = None if (a.hidden and not a.unlocked) else (value or 0)
    return achievements


class AchievementListAPI(APIView):
    @login_required
    def get(self, request):
        user = _resolve_user(request)
        if user is None:
            return self.error("用户不存在")

        achievements = list(Achievement.objects.filter(visible=True))
        unlocked_map = {r.achievement_id: r for r in UserAchievement.objects.filter(user=user)}
        stat = UserStat.objects.filter(user=user).first()
        metrics = stat.metrics if stat else {}

        _decorate(achievements, unlocked_map, metrics)
        return self.success(
            {
                "username": user.username,
                "achievements": AchievementSerializer(achievements, many=True).data,
            }
        )


class AchievementSummaryAPI(APIView):
    @login_required
    def get(self, request):
        user = _resolve_user(request)
        if user is None:
            return self.error("用户不存在")

        total_by_rarity = dict(Achievement.objects.filter(visible=True).values_list("rarity").annotate(c=Count("id")))
        unlocked_by_rarity = dict(UserAchievement.objects.filter(user=user, achievement__visible=True).values_list("achievement__rarity").annotate(c=Count("id")))
        total = sum(total_by_rarity.values())
        unlocked = sum(unlocked_by_rarity.values())

        recent = list(UserAchievement.objects.filter(user=user, achievement__visible=True).select_related("achievement").order_by("-unlock_time")[:5])

        return self.success(
            {
                "username": user.username,
                "total": total,
                "unlocked": unlocked,
                "percent": round(unlocked / total * 100, 1) if total else 0.0,
                "rarity": [
                    {
                        "rarity": value,
                        "label": label,
                        "total": total_by_rarity.get(value, 0),
                        "unlocked": unlocked_by_rarity.get(value, 0),
                    }
                    for value, label in Rarity.choices
                ],
                "recent": PendingAchievementSerializer(recent, many=True).data,
            }
        )


class AchievementPendingAPI(APIView):
    @login_required
    def get(self, request):
        """返回尚未弹过的解锁记录。前端在布局层路由切换时拉取。"""
        records = UserAchievement.objects.filter(user=request.user, notified=False, achievement__visible=True).select_related("achievement").order_by("unlock_time")
        return self.success(PendingAchievementSerializer(records, many=True).data)

    @login_required
    def post(self, request):
        """弹完后标记已读，避免下次导航重复弹。body: {"ids": [成就 id]}"""
        ids = request.data.get("ids") or []
        if not isinstance(ids, list):
            return self.error("参数错误")
        UserAchievement.objects.filter(user=request.user, achievement_id__in=ids).update(notified=True)
        return self.success("ok")
