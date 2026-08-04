"""全量重算指标并补发成就。

用途：
1. 系统首次上线，给存量用户补发（用 --silent，否则学生一登录被 30 个奖杯糊脸）
2. 新增指标或改了口径后重算（不带 --silent，新解锁会正常弹出）

这也是增量逻辑的安全网：怀疑 UserStat 漂移时跑一遍即可。
"""

from django.core.management.base import BaseCommand

from account.models import User
from achievement import checker
from achievement.metrics import META_METRICS, METRIC_REGISTRY
from achievement.models import UserStat


class Command(BaseCommand):
    help = "重算全部用户的成就指标并补发成就"

    def add_arguments(self, parser):
        parser.add_argument("--user", type=int, default=None, help="只处理指定用户 id")
        parser.add_argument("--silent", action="store_true", help="补发的成就标记为已通知，不弹窗")

    def handle(self, *args, **options):
        users = User.objects.filter(is_disabled=False)
        if options["user"]:
            users = users.filter(id=options["user"])

        silent = options["silent"]
        total_users = users.count()
        total_unlocked = 0

        for index, user in enumerate(users.iterator(), start=1):
            stat, _ = UserStat.objects.get_or_create(user=user)
            metrics = {}
            for key, m in METRIC_REGISTRY.items():
                if key in META_METRICS:
                    continue
                value = m.recompute(user)
                # None 表示该指标无有效值，key 必须缺席而不是置 0
                if value is not None:
                    metrics[key] = value
                # 一并重建增量辅助键，否则重算后的第一次判题会把
                # active_days / languages_used / max_ac_in_one_day 打回 1
                metrics.update(m.recompute_state(user))
            stat.metrics = metrics
            stat.save(update_fields=["metrics", "update_time"])

            records = checker.unlock(user, checker.evaluate(user, metrics), backfilled=True, notified=silent)

            # 元指标第二轮
            for key in META_METRICS:
                value = METRIC_REGISTRY[key].recompute(user)
                if value is not None:
                    metrics[key] = value
            stat.metrics = metrics
            stat.save(update_fields=["metrics", "update_time"])
            records += checker.unlock(user, checker.evaluate(user, metrics, only_metrics=META_METRICS), backfilled=True, notified=silent)

            total_unlocked += len(records)
            if index % 50 == 0:
                self.stdout.write(f"processed {index}/{total_users}")

        self.stdout.write(self.style.SUCCESS(f"完成：{total_users} 个用户，新解锁 {total_unlocked} 条"))
