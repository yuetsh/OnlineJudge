"""成就系统部署后自检。

只读，不修改任何数据，可以反复跑。

这套系统开发全程没有数据库可用，所有后端逻辑都只经过纸面审查。本命令覆盖
那些"错了也不报错、只是悄悄发错奖杯"的地方——每一项都对应一个已知的、
静态审查抓不到的失败模式。

    python manage.py check_achievement_deploy
"""

from django.core.management.base import BaseCommand
from django.db.models import IntegerField
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast

from account.models import User
from achievement.metrics import META_METRICS, METRIC_REGISTRY
from achievement.models import Achievement, Operator, UserAchievement, UserStat

# on_submission 依赖的辅助键 -> 它应该与哪个顶层指标保持一致
STATE_PAIRS = {
    "_active_dates": "active_days",
    "_languages": "languages_used",
}


class Command(BaseCommand):
    help = "成就系统部署后自检（只读）"

    def handle(self, *args, **options):
        self.failures = 0
        self.warnings = 0

        self._check_migration()
        self._check_registry()
        self._check_min_metric_absent()
        self._check_jsonb_cast()
        self._check_recompute_state()
        self._check_unlock_count()
        self._check_dead_achievements()

        self.stdout.write("")
        if self.failures:
            self.stdout.write(self.style.ERROR(f"{self.failures} 项未通过，先别配成就。"))
        elif self.warnings:
            self.stdout.write(self.style.WARNING(f"全部通过，{self.warnings} 项提醒。"))
        else:
            self.stdout.write(self.style.SUCCESS("全部通过。"))

    # ---------- 输出 ----------

    def _ok(self, title, detail=""):
        self.stdout.write(self.style.SUCCESS(f"[PASS] {title}") + (f"  {detail}" if detail else ""))

    def _fail(self, title, detail):
        self.failures += 1
        self.stdout.write(self.style.ERROR(f"[FAIL] {title}"))
        self.stdout.write(f"       {detail}")

    def _skip(self, title, detail):
        self.stdout.write(self.style.WARNING(f"[SKIP] {title}") + f"  {detail}")

    def _warn(self, title, detail):
        self.warnings += 1
        self.stdout.write(self.style.WARNING(f"[WARN] {title}"))
        self.stdout.write(f"       {detail}")

    # ---------- 检查项 ----------

    def _check_migration(self):
        title = "迁移已应用"
        try:
            Achievement.objects.count()
            UserStat.objects.count()
            UserAchievement.objects.count()
        except Exception as e:
            self._fail(title, f"三张表至少有一张不存在：{e}\n       跑 python manage.py migrate achievement")
            return
        self._ok(title)

    def _check_registry(self):
        title = "指标注册表已加载"
        count = len(METRIC_REGISTRY)
        if count == 0:
            self._fail(title, "METRIC_REGISTRY 是空的，AppConfig.ready() 没有导入 metrics")
            return
        self._ok(title, f"{count} 个指标，元指标 {sorted(META_METRICS)}")

    def _check_min_metric_absent(self):
        """lte 类成就用的指标，对没有 AC 记录的用户必须返回 None。

        返回 0 的话，"最短 AC 代码 ≤ 50 字符"这类成就会白送给每一个从没做出过题的新生。
        线上目前没有 lte 成就（min_ac_code_chars 已删），本项因此会 SKIP；
        将来配了任何 lte 成就，它会自动开始检查对应的指标。
        """
        title = "极小值指标对零 AC 用户返回 None"
        metric_keys = sorted(set(Achievement.objects.filter(operator=Operator.LTE, visible=True).values_list("metric", flat=True)))
        metrics = [(k, METRIC_REGISTRY[k]) for k in metric_keys if k in METRIC_REGISTRY]
        if not metrics:
            self._skip(title, "没有上架的 lte 类成就")
            return

        user = User.objects.filter(is_disabled=False, userprofile__accepted_number=0).first()
        if user is None:
            self._skip(title, "找不到 accepted_number=0 的用户，无法验证")
            return

        bad = [(key, value) for key, m in metrics if (value := m.recompute(user)) is not None]
        if bad:
            detail = "、".join(f"{key} 得到 {value!r}" for key, value in bad)
            self._fail(
                title,
                f"用户 {user.username}：{detail}，都应为 None。\n       这些 lte 成就正在白送给全部零 AC 用户。",
            )
        else:
            self._ok(title, f"用户 {user.username}，检查了 {len(metrics)} 个指标")

    def _check_jsonb_cast(self):
        """JSONB 数字必须按整数比较，不能按字符串序。

        没有显式 Cast 时 Postgres 会认为 "9" > "50"，后台调低阈值触发的补发
        会发给错误的人群，且不报任何错。
        """
        title = "JSONB 阈值比较按整数而非字符串序"
        key = "submission_count"
        rows = list(UserStat.objects.filter(metrics__has_key=key).values_list("id", "metrics"))
        if len(rows) < 2:
            self._skip(title, f"有 {key} 的 UserStat 少于 2 条，无法验证")
            return

        values = [(rid, m.get(key)) for rid, m in rows if isinstance(m.get(key), int)]
        if not values:
            self._skip(title, f"{key} 没有整数值")
            return

        # 挑一个能区分整数序和字符串序的阈值：字符串比较下 "9" > "50"
        threshold = 9
        expected = {rid for rid, v in values if v >= threshold}

        actual = set(
            UserStat.objects.filter(metrics__has_key=key).annotate(v=Cast(KeyTextTransform(key, "metrics"), IntegerField())).filter(v__gte=threshold).values_list("id", flat=True)
        )

        if actual == expected:
            self._ok(title, f"阈值 {threshold} 命中 {len(actual)} 人，与 Python 侧一致")
        else:
            missing = len(expected - actual)
            extra = len(actual - expected)
            self._fail(
                title,
                f"数据库筛出 {len(actual)} 人，正确答案是 {len(expected)} 人（少 {missing}、多 {extra}）。\n       rescan_achievement 会把成就补发给错误的人群。",
            )

    def _check_recompute_state(self):
        """重算必须一并重建 on_submission 依赖的辅助键。

        辅助键缺失时，用户的下一次提交会把 active_days / languages_used
        打回 1，且要等到下一次重算才恢复。
        """
        title = "重算重建了增量辅助键"
        stat = UserStat.objects.filter(metrics__has_key="active_days").exclude(metrics__active_days=0).first()
        if stat is None:
            self._skip(title, "还没有任何用户的 active_days，先跑 recompute_achievements --user <id>")
            return

        problems = []
        for state_key, top_key in STATE_PAIRS.items():
            top = stat.metrics.get(top_key)
            state = stat.metrics.get(state_key)
            if top is None:
                continue
            if state is None:
                problems.append(f"{state_key} 缺失（{top_key}={top}）")
            elif len(state) != top:
                problems.append(f"len({state_key})={len(state)} != {top_key}={top}")

        if problems:
            self._fail(
                title,
                "；".join(problems) + f"\n       用户 id={stat.user_id} 的下一次提交会让这些指标回退。",
            )
        else:
            self._ok(title, f"用户 id={stat.user_id} 的辅助键与顶层值一致")

    def _check_unlock_count(self):
        """unlock_count 是独立计数器，必须与实际解锁人数相等。

        并发解锁重复累加、或删过 UserAchievement 但没重置计数器，
        都会让获得率虚高。
        """
        title = "unlock_count 与实际解锁人数一致"
        if not Achievement.objects.exists():
            self._skip(title, "还没有配置任何成就")
            return

        drifted = []
        for a in Achievement.objects.all():
            real = UserAchievement.objects.filter(achievement=a).count()
            if a.unlock_count != real:
                drifted.append(f"「{a.name}」计数器 {a.unlock_count} vs 实际 {real}")

        if drifted:
            self._fail(
                title,
                "；".join(drifted[:5]) + ("…" if len(drifted) > 5 else "") + "\n       获得率显示会不准。修：Achievement.objects.update(unlock_count=0) 后重跑重算。",
            )
        else:
            self._ok(title, f"{Achievement.objects.count()} 条成就全部一致")

    def _check_dead_achievements(self):
        """长期零解锁的成就多半是阈值配错了。"""
        title = "没有疑似配错阈值的成就"
        if not Achievement.objects.exists():
            self._skip(title, "还没有配置任何成就")
            return

        dead = list(Achievement.objects.filter(visible=True, unlock_count=0, hidden=False).values_list("name", "metric", "operator", "threshold"))
        if dead:
            self._warn(
                title,
                f"{len(dead)} 条公开成就零解锁："
                + "；".join(f"「{n}」{m} {o} {t}" for n, m, o, t in dead[:5])
                + ("…" if len(dead) > 5 else "")
                + "\n       刚上线属正常；配置一周后仍为 0 就要怀疑阈值。",
            )
        else:
            self._ok(title)
