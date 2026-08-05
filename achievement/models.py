from django.db import models

from account.models import User
from utils.models import JSONField


class Rarity(models.TextChoices):
    BRONZE = "bronze", "青铜"
    SILVER = "silver", "白银"
    GOLD = "gold", "黄金"
    PLATINUM = "platinum", "白金"


class Operator(models.TextChoices):
    GTE = "gte", "大于等于"
    LTE = "lte", "小于等于"


class Achievement(models.Model):
    name = models.TextField(verbose_name="成就名称")
    description = models.TextField(verbose_name="成就描述")
    # iconify 图标名（如 noto:owl），不是 emoji 字符：
    # 机房的老浏览器缺 emoji 字体会渲染成方块，前端统一渲染成 SVG
    icon = models.TextField(verbose_name="图标")
    rarity = models.TextField(default=Rarity.BRONZE, choices=Rarity.choices, verbose_name="稀有度")
    hidden = models.BooleanField(default=False, db_default=False, verbose_name="是否隐藏")
    metric = models.TextField(verbose_name="指标名")
    operator = models.TextField(default=Operator.GTE, choices=Operator.choices, verbose_name="比较符")
    threshold = models.IntegerField(verbose_name="阈值")
    visible = models.BooleanField(default=True, db_default=True, verbose_name="是否上架")
    unlock_count = models.IntegerField(default=0, db_default=0, verbose_name="已解锁人数")
    order = models.IntegerField(default=0, db_default=0, verbose_name="排序")
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "achievement"
        ordering = ("order", "id")
        verbose_name = "成就"
        verbose_name_plural = "成就"


class UserStat(models.Model):
    """成就系统唯一的指标源，不复用 UserProfile 的计数器，避免两处口径漂移。

    metrics 为 {指标名: 数值}；指标从未产生过有效值时 key 不存在（而非置 0），
    否则 min_ac_code_chars 这类极小值指标会对新用户恒成立。
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="achievement_stat")
    metrics = JSONField(default=dict, db_default=models.Value({}, output_field=models.JSONField()))
    update_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_stat"


class UserAchievement(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="achievements")
    achievement = models.ForeignKey(Achievement, on_delete=models.CASCADE)
    unlock_time = models.DateTimeField(auto_now_add=True)
    # 上线补发的记录：前端不显示具体日期，只显示"已获得"
    backfilled = models.BooleanField(default=False, db_default=False)
    # 是否已向用户弹过奖杯，pending 端点据此查询
    notified = models.BooleanField(default=False, db_default=False)

    class Meta:
        db_table = "user_achievement"
        ordering = ("-unlock_time",)
        constraints = [
            models.UniqueConstraint(fields=["user", "achievement"], name="unique_user_achievement"),
        ]
        indexes = [
            models.Index(fields=["user", "-unlock_time"], name="user_achv_time_idx"),
            models.Index(fields=["user", "notified"], name="user_achv_notified_idx"),
        ]
