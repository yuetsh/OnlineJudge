from django.core.cache import cache
from rest_framework import serializers

from account.models import User
from achievement.models import Achievement, UserAchievement


def get_active_user_count():
    """获得率的分母：未禁用用户总数，缓存 1 小时。

    不用"有过提交的用户数"这类动态口径：分母波动会让同一个成就的获得率
    忽高忽低，学生会当成 bug。
    """
    count = cache.get("achievement_active_user_count")
    if count is None:
        count = User.objects.filter(is_disabled=False).count()
        cache.set("achievement_active_user_count", count, 3600)
    return count


class AchievementSerializer(serializers.ModelSerializer):
    unlocked = serializers.BooleanField(read_only=True)
    unlock_time = serializers.DateTimeField(read_only=True, allow_null=True)
    backfilled = serializers.BooleanField(read_only=True)
    progress = serializers.IntegerField(read_only=True, allow_null=True)
    unlock_rate = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    icon = serializers.SerializerMethodField()
    # 条件三件套也必须跟着遮掉：只遮名称和描述、却明文下发
    # metric/operator/threshold，学生打开 DevTools 就知道"凌晨提交 10 次"，
    # 隐藏成就的意义全部作废
    metric = serializers.SerializerMethodField()
    operator = serializers.SerializerMethodField()
    threshold = serializers.SerializerMethodField()

    class Meta:
        model = Achievement
        fields = (
            "id",
            "name",
            "description",
            "icon",
            "rarity",
            "hidden",
            "metric",
            "operator",
            "threshold",
            "unlocked",
            "unlock_time",
            "backfilled",
            "progress",
            "unlock_rate",
        )

    def _masked(self, obj):
        return obj.hidden and not getattr(obj, "unlocked", False)

    def get_name(self, obj):
        return "???" if self._masked(obj) else obj.name

    def get_description(self, obj):
        return "达成条件保密" if self._masked(obj) else obj.description

    def get_icon(self, obj):
        return "❓" if self._masked(obj) else obj.icon

    def get_metric(self, obj):
        return None if self._masked(obj) else obj.metric

    def get_operator(self, obj):
        return None if self._masked(obj) else obj.operator

    def get_threshold(self, obj):
        return None if self._masked(obj) else obj.threshold

    def get_unlock_rate(self, obj):
        total = get_active_user_count()
        if not total:
            return 0.0
        return round(obj.unlock_count / total * 100, 1)


class PendingAchievementSerializer(serializers.ModelSerializer):
    """待弹窗的解锁记录，无需打码（已解锁）。"""

    id = serializers.IntegerField(source="achievement_id", read_only=True)
    name = serializers.CharField(source="achievement.name", read_only=True)
    description = serializers.CharField(source="achievement.description", read_only=True)
    icon = serializers.CharField(source="achievement.icon", read_only=True)
    rarity = serializers.CharField(source="achievement.rarity", read_only=True)

    class Meta:
        model = UserAchievement
        fields = ("id", "name", "description", "icon", "rarity")
