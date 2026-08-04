"""成就指标注册表。

这里定义"能测量什么"，后台定义"多少算达成"。管理员在后台看到的指标下拉框
就是 METRIC_REGISTRY 的 key 列表。加一个新维度必须改本文件并部署，
之后在该维度上加任意多条成就都是纯配置。

约定：指标从未产生过有效值时，recompute 返回 None，调用方删除该 key。
metrics 字典里 key 不存在 == 未达标，判定时直接跳过。
"""

import logging

from django.db.models import Count, Q
from django.utils import timezone

from submission.models import JudgeStatus, Submission

logger = logging.getLogger(__name__)

METRIC_REGISTRY = {}
META_METRICS = set()


class BaseMetric:
    key = ""
    name = ""
    help_text = ""

    def on_submission(self, metrics, sub, ctx):
        """判题完成后增量更新 metrics（原地修改）。"""
        raise NotImplementedError

    def recompute(self, user):
        """全量重算。返回 None 表示该用户此指标无有效值。"""
        raise NotImplementedError


def metric(key, name, help_text="", meta=False):
    def deco(cls):
        cls.key = key
        cls.name = name
        cls.help_text = help_text
        METRIC_REGISTRY[key] = cls()
        if meta:
            META_METRICS.add(key)
        return cls

    return deco


def _practice_submissions(user_id):
    """成就只统计平时练习的提交，比赛提交不计入。"""
    return Submission.objects.filter(user_id=user_id, contest_id__isnull=True)


def build_ctx(user_id, sub):
    """判题后预查一次，所有指标复用，避免每个指标各自查库。

    比赛提交不参与成就统计，此时返回 skip=True，调用方直接跳过整轮判定。
    """
    if sub.contest_id is not None:
        return {"skip": True}

    prior = _practice_submissions(user_id).filter(problem_id=sub.problem_id).exclude(id=sub.id)
    prior_stats = prior.aggregate(
        total=Count("id"),
        accepted=Count("id", filter=Q(result=JudgeStatus.ACCEPTED)),
    )
    local_now = timezone.localtime(sub.create_time)
    return {
        "skip": False,
        "is_accepted": sub.result == JudgeStatus.ACCEPTED,
        # 该题此前的提交次数与 AC 次数
        "prior_count": prior_stats["total"],
        "prior_accepted": prior_stats["accepted"],
        # 首次 AC 这道题（此前从未 AC 过）
        "is_first_ac_of_problem": sub.result == JudgeStatus.ACCEPTED and prior_stats["accepted"] == 0,
        # 一发入魂：此前无任何提交且本次 AC
        "is_first_try_ac": sub.result == JudgeStatus.ACCEPTED and prior_stats["total"] == 0,
        "local_date": local_now.date().isoformat(),
        "local_hour": local_now.hour,
    }


@metric("accepted_count", "AC 题目数", "去重后通过的题目数量（不含比赛）")
class AcceptedCount(BaseMetric):
    def on_submission(self, metrics, sub, ctx):
        if ctx["is_first_ac_of_problem"]:
            metrics["accepted_count"] = metrics.get("accepted_count", 0) + 1

    def recompute(self, user):
        return _practice_submissions(user.id).filter(result=JudgeStatus.ACCEPTED).values("problem_id").distinct().count()


@metric("submission_count", "提交总数", "提交次数（不含比赛）")
class SubmissionCount(BaseMetric):
    def on_submission(self, metrics, sub, ctx):
        metrics["submission_count"] = metrics.get("submission_count", 0) + 1

    def recompute(self, user):
        return _practice_submissions(user.id).count()


@metric("active_days", "活跃天数", "有过提交的累计天数")
class ActiveDays(BaseMetric):
    def on_submission(self, metrics, sub, ctx):
        seen = metrics.get("_active_dates", [])
        if ctx["local_date"] not in seen:
            seen.append(ctx["local_date"])
            metrics["_active_dates"] = seen
            metrics["active_days"] = len(seen)

    def recompute(self, user):
        dates = {timezone.localtime(t).date().isoformat() for t in _practice_submissions(user.id).values_list("create_time", flat=True)}
        return len(dates)


@metric("max_ac_streak_days", "最长连续 AC 天数", "连续每天至少 AC 一题的最长天数")
class MaxAcStreakDays(BaseMetric):
    def on_submission(self, metrics, sub, ctx):
        if not ctx["is_accepted"]:
            return
        today = ctx["local_date"]
        last = metrics.get("_last_ac_date")
        if last == today:
            return
        current = metrics.get("_current_ac_streak", 0)
        if last and (timezone.datetime.fromisoformat(today) - timezone.datetime.fromisoformat(last)).days == 1:
            current += 1
        else:
            current = 1
        metrics["_last_ac_date"] = today
        metrics["_current_ac_streak"] = current
        metrics["max_ac_streak_days"] = max(metrics.get("max_ac_streak_days", 0), current)

    def recompute(self, user):
        dates = sorted({timezone.localtime(t).date() for t in _practice_submissions(user.id).filter(result=JudgeStatus.ACCEPTED).values_list("create_time", flat=True)})
        if not dates:
            return None
        best = current = 1
        for prev, cur in zip(dates, dates[1:]):
            current = current + 1 if (cur - prev).days == 1 else 1
            best = max(best, current)
        return best


@metric("languages_used", "使用语言数", "用过多少种编程语言")
class LanguagesUsed(BaseMetric):
    def on_submission(self, metrics, sub, ctx):
        seen = metrics.get("_languages", [])
        if sub.language not in seen:
            seen.append(sub.language)
            metrics["_languages"] = seen
            metrics["languages_used"] = len(seen)

    def recompute(self, user):
        return _practice_submissions(user.id).values("language").distinct().count()


@metric("contest_joined", "参赛场次", "参加过的比赛数量（本指标是比赛维度，不受比赛提交不计入的限制）")
class ContestJoined(BaseMetric):
    def on_submission(self, metrics, sub, ctx):
        # 比赛提交在 build_ctx 就被跳过，本指标只走 recompute
        return

    def recompute(self, user):
        return Submission.objects.filter(user_id=user.id, contest_id__isnull=False).values("contest_id").distinct().count()


@metric("badge_count", "题单奖章数", "获得的题单奖章数量")
class BadgeCount(BaseMetric):
    def on_submission(self, metrics, sub, ctx):
        # 奖章由题单流程颁发，本指标只走 recompute，见 Task 7
        return

    def recompute(self, user):
        from problemset.models import UserBadge

        return UserBadge.objects.filter(user=user).count()


@metric("problemset_completed", "完成题单数", "完成的题单数量")
class ProblemSetCompleted(BaseMetric):
    def on_submission(self, metrics, sub, ctx):
        return

    def recompute(self, user):
        from problemset.models import ProblemSetProgress

        return ProblemSetProgress.objects.filter(user=user, complete_time__isnull=False).count()


@metric("first_try_ac_count", "一发入魂次数", "首次提交即通过的次数")
class FirstTryAcCount(BaseMetric):
    def on_submission(self, metrics, sub, ctx):
        if ctx["is_first_try_ac"]:
            metrics["first_try_ac_count"] = metrics.get("first_try_ac_count", 0) + 1

    def recompute(self, user):
        count = 0
        seen = set()
        for s in _practice_submissions(user.id).order_by("create_time").values("problem_id", "result"):
            if s["problem_id"] in seen:
                continue
            seen.add(s["problem_id"])
            if s["result"] == JudgeStatus.ACCEPTED:
                count += 1
        return count


@metric("midnight_submissions", "凌晨提交次数", "0:00–5:00 之间的提交次数")
class MidnightSubmissions(BaseMetric):
    def on_submission(self, metrics, sub, ctx):
        if 0 <= ctx["local_hour"] < 5:
            metrics["midnight_submissions"] = metrics.get("midnight_submissions", 0) + 1

    def recompute(self, user):
        return sum(1 for t in _practice_submissions(user.id).values_list("create_time", flat=True) if 0 <= timezone.localtime(t).hour < 5)


@metric("compile_error_count", "编译错误次数", "累计编译错误的次数")
class CompileErrorCount(BaseMetric):
    def on_submission(self, metrics, sub, ctx):
        if sub.result == JudgeStatus.COMPILE_ERROR:
            metrics["compile_error_count"] = metrics.get("compile_error_count", 0) + 1

    def recompute(self, user):
        return _practice_submissions(user.id).filter(result=JudgeStatus.COMPILE_ERROR).count()


@metric("max_wa_before_ac", "屡败屡战", "单题失败最多多少次后终于通过")
class MaxWaBeforeAc(BaseMetric):
    def on_submission(self, metrics, sub, ctx):
        if ctx["is_first_ac_of_problem"]:
            metrics["max_wa_before_ac"] = max(metrics.get("max_wa_before_ac", 0), ctx["prior_count"])

    def recompute(self, user):
        best = None
        attempts = {}
        for s in _practice_submissions(user.id).order_by("create_time").values("problem_id", "result"):
            pid = s["problem_id"]
            if pid in attempts and attempts[pid] is None:
                continue
            if s["result"] == JudgeStatus.ACCEPTED:
                best = max(best or 0, attempts.get(pid, 0))
                attempts[pid] = None
            else:
                attempts[pid] = attempts.get(pid, 0) + 1
        return best


@metric("max_ac_in_one_day", "单日最多 AC", "一天之内最多通过多少题")
class MaxAcInOneDay(BaseMetric):
    def on_submission(self, metrics, sub, ctx):
        if not ctx["is_first_ac_of_problem"]:
            return
        counts = metrics.get("_ac_per_day", {})
        counts[ctx["local_date"]] = counts.get(ctx["local_date"], 0) + 1
        metrics["_ac_per_day"] = counts
        metrics["max_ac_in_one_day"] = max(counts.values())

    def recompute(self, user):
        counts = {}
        seen = set()
        for s in _practice_submissions(user.id).filter(result=JudgeStatus.ACCEPTED).order_by("create_time").values("problem_id", "create_time"):
            if s["problem_id"] in seen:
                continue
            seen.add(s["problem_id"])
            day = timezone.localtime(s["create_time"]).date().isoformat()
            counts[day] = counts.get(day, 0) + 1
        return max(counts.values()) if counts else None


@metric("min_ac_code_chars", "最短 AC 代码", "通过的代码里最短的字符数（配小于等于使用）")
class MinAcCodeChars(BaseMetric):
    def on_submission(self, metrics, sub, ctx):
        if not ctx["is_accepted"]:
            return
        length = len(sub.code)
        cur = metrics.get("min_ac_code_chars")
        metrics["min_ac_code_chars"] = length if cur is None else min(cur, length)

    def recompute(self, user):
        lengths = [len(c) for c in _practice_submissions(user.id).filter(result=JudgeStatus.ACCEPTED).values_list("code", flat=True)]
        return min(lengths) if lengths else None


@metric("max_code_lines", "最长代码行数", "提交过的最长代码有多少行")
class MaxCodeLines(BaseMetric):
    def on_submission(self, metrics, sub, ctx):
        lines = len(sub.code.splitlines())
        metrics["max_code_lines"] = max(metrics.get("max_code_lines", 0), lines)

    def recompute(self, user):
        counts = [len(c.splitlines()) for c in _practice_submissions(user.id).values_list("code", flat=True)]
        return max(counts) if counts else None


@metric("achievement_unlocked_count", "已解锁成就数", "已解锁的成就数量（不含白金档）", meta=True)
class AchievementUnlockedCount(BaseMetric):
    """自引用指标：解锁成就会改变它。

    因此判定流程限定为最多两轮（见 checker.py），且口径排除白金档自身，
    避免「集齐 N 个成就」这类白金奖杯把自己算进分子。
    """

    def on_submission(self, metrics, sub, ctx):
        # 由 checker 在第一轮解锁后显式重算，不参与增量更新
        return

    def recompute(self, user):
        from achievement.models import Rarity, UserAchievement

        return UserAchievement.objects.filter(user=user).exclude(achievement__rarity=Rarity.PLATINUM).count()
