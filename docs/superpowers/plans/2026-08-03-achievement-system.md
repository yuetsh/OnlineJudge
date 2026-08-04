# 成就系统实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 OJ 加一套 PlayStation 奖杯风格的全站成就系统：代码注册指标、后台配置条件、判题后异步判定、前端奖杯馆展示。

**Architecture:** 后端新建 Django app `achievement/`，三张表（成就定义 / 用户指标快照 / 解锁记录）。指标由 `metrics.py` 的注册表提供，管理员在后台把「指标 + 比较符 + 阈值」组合成成就。判题完成后投递 dramatiq 任务增量更新指标并判定解锁。通知走推拉结合：解锁记录带 `notified` 标志，前端在布局层拉取待弹列表，WebSocket 作为在线时的即时增强。前端新增奖杯馆页面与全局奖杯弹窗。

**Tech Stack:** Django 6 + DRF + PostgreSQL(JSONB) + dramatiq + channels / Vue 3 + TypeScript + Naive UI + Pinia

**Spec:** `docs/superpowers/specs/2026-08-03-achievement-system-design.md`

## Global Constraints

- **不写测试。** 项目 `CLAUDE.md` 明确规定 "Do not write tests"。本计划因此不含 TDD 循环，每个任务以可执行的验证命令（Django shell / ruff / curl / 浏览器操作）替代测试步骤。执行者不得自行添加测试文件。
- 后端仓库为 `OnlineJudge/`，前端仓库为 `ojnext/`，**两者是独立的 git 仓库**，根目录 `OJ/` 不是仓库。跨仓库的任务分别提交。
- 后端当前分支 `yuetsh`。
- 后端 lint：`ruff check .` 与 `ruff format .`（E/F/I 规则，行宽 180，双引号）。每次提交前必须通过。
- 前端格式化：`npm fmt`（Prettier）。
- 所有基于提交的指标**只统计 `contest_id IS NULL` 的提交**，比赛题不计入成就。唯一例外是 `contest_joined`。
- **判断提交是否算通过一律用 `submission.models.is_accepted()`**，即 `result in (ACCEPTED, AST_CHECK_FAILED)`，与项目其余所有 AC 统计口径一致。ORM 过滤用 `result__in=(JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED)`。（Task 2 执行期间由 reviewer 发现计划原文写成了 `result == ACCEPTED`，经人工裁决改正。）
- 成就为纯荣誉，**不发放任何可消费奖励**，不接入积分/道具/权限体系。
- 判定任务内所有异常必须捕获并记日志，绝不允许影响判题结果。
- 指标未产生过有效值时，其 key **不存在于** `metrics` 字典中（而非置 0）。判定时遇到缺失 key 直接跳过该成就。
- 前端自动导入已配置：Vue API、Vue Router、Pinia、VueUse、Naive UI 组件与 composable **无需手动 import**。
- 后端视图统一继承 `utils.api.APIView`（非 DRF 的 APIView），用 `self.success(data)` / `self.error(msg)` 返回。

---

## File Structure

### 后端（`OnlineJudge/`）

**新建：**

| 文件 | 职责 |
|---|---|
| `achievement/__init__.py` | 空 |
| `achievement/apps.py` | AppConfig，`ready()` 中导入 `metrics` 以触发注册 |
| `achievement/models.py` | `Achievement` / `UserStat` / `UserAchievement` 三张表 |
| `achievement/metrics.py` | 指标注册表与全部指标实现 |
| `achievement/checker.py` | 判定核心：更新指标 → 比对 → 解锁，被任务和管理命令共用 |
| `achievement/tasks.py` | dramatiq actor：`check_achievements`、`rescan_achievement` |
| `achievement/notify.py` | 解锁通知（写 `notified=False` 记录 + WebSocket 推送） |
| `achievement/serializers.py` | DRF 序列化器，隐藏成就的打码在此完成 |
| `achievement/views/oj.py` | 用户侧视图 |
| `achievement/views/admin.py` | 管理侧视图 |
| `achievement/urls/oj.py`、`achievement/urls/admin.py` | 路由 |
| `achievement/management/commands/recompute_achievements.py` | 全量重算命令 |
| `achievement/migrations/` | 迁移 |

**修改：**

| 文件 | 改动 |
|---|---|
| `oj/settings.py:47-64` | `LOCAL_APPS` 加 `"achievement"` |
| `oj/urls.py` | 注册两条路由 |
| `judge/tasks.py:11-19` | `judge_task` 末尾投递 `check_achievements` |
| `problemset/views/oj.py:231-247` | 重写 `_check_badges`：修 N+1、改 `get_or_create`、接通知 |

### 前端（`ojnext/`）

**新建：**

| 文件 | 职责 |
|---|---|
| `src/oj/achievement/index.vue` | 奖杯馆页面 |
| `src/oj/achievement/api.ts` | 成就相关 API |
| `src/oj/achievement/components/AchievementCard.vue` | 单个成就卡片（三种状态） |
| `src/shared/components/AchievementToast.vue` | 全局解锁弹窗 |
| `src/shared/store/achievement.ts` | Pinia store：待弹队列 |
| `src/admin/achievement/list.vue` | 管理后台成就列表 |
| `src/admin/achievement/components/AchievementModal.vue` | 新建/编辑成就弹窗 |

**修改：**

| 文件 | 改动 |
|---|---|
| `src/routes.ts` | 加奖杯馆路由与管理后台路由 |
| `src/utils/types.ts` | 成就相关类型 |
| `src/oj/problem/composables/useSubmissionMonitor.ts:85` 附近 | handler 按 `data.type` 过滤，成就消息分流 |
| `src/shared/layout/default.vue` | 挂载 `AchievementToast`，路由切换拉取 pending |
| `src/oj/user/index.vue` | 成就摘要区 |
| `src/oj/rank/list.vue` | 每行挂最稀有徽章 |

---

## Task 1: 后端 app 骨架与数据模型

**Files:**
- Create: `OnlineJudge/achievement/__init__.py`、`apps.py`、`models.py`、`migrations/__init__.py`
- Create: `OnlineJudge/achievement/views/__init__.py`、`urls/__init__.py`
- Modify: `OnlineJudge/oj/settings.py:47-64`

**Interfaces:**
- Produces: `Achievement`、`UserStat`、`UserAchievement` 三个模型；`Rarity`、`Operator` 两个 `TextChoices`。后续所有任务都从 `achievement.models` 导入这些名字。

- [ ] **Step 1: 创建包结构**

```bash
cd OnlineJudge
mkdir -p achievement/migrations achievement/views achievement/urls achievement/management/commands
touch achievement/__init__.py achievement/migrations/__init__.py
touch achievement/views/__init__.py achievement/urls/__init__.py
touch achievement/management/__init__.py achievement/management/commands/__init__.py
```

- [ ] **Step 2: 写 `achievement/apps.py`**

`metrics.py` 要到 Task 2 才存在，所以本任务的 `ready()` 先留空，Task 2 Step 6 再补上注册钩子。

```python
from django.apps import AppConfig


class AchievementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "achievement"
```

- [ ] **Step 3: 写 `achievement/models.py`**

```python
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
```

- [ ] **Step 4: 注册 app**

在 `oj/settings.py` 的 `LOCAL_APPS` 列表末尾（`"class_pk",` 之后）加一行：

```python
    "achievement",
```

- [ ] **Step 5: 生成并应用迁移**

```bash
cd OnlineJudge
python manage.py makemigrations achievement
python manage.py migrate achievement
```

Expected: 输出 `Create model Achievement / UserStat / UserAchievement`，migrate 成功无报错。

- [ ] **Step 6: 验证模型可用**

```bash
python manage.py shell -c "
from achievement.models import Achievement, UserStat, UserAchievement, Rarity, Operator
a = Achievement.objects.create(name='测试', description='d', icon='🏆', metric='accepted_count', operator=Operator.GTE, threshold=1)
print('created', a.id, a.rarity, a.visible, a.unlock_count)
a.delete()
print('ok')
"
```

Expected: 打印 `created <id> bronze True 0` 与 `ok`。

- [ ] **Step 7: Lint 并提交**

```bash
cd OnlineJudge
ruff format . && ruff check .
git add achievement oj/settings.py
git commit -m "feat(achievement): 添加成就系统数据模型"
```

---

## Task 2: 指标注册表

**Files:**
- Create: `OnlineJudge/achievement/metrics.py`
- Modify: `OnlineJudge/achievement/apps.py`

**Interfaces:**
- Consumes: `achievement.models.UserStat`
- Produces:
  - `METRIC_REGISTRY: dict[str, BaseMetric]`
  - `@metric(key, name, help_text)` 装饰器
  - `BaseMetric.on_submission(self, metrics: dict, sub: Submission, ctx: dict) -> None` — 原地修改 `metrics`
  - `BaseMetric.recompute(self, user) -> int | None` — 返回 `None` 表示该用户此指标无有效值（调用方应删除该 key）
  - `build_ctx(user_id: int, submission) -> dict` — 判题后预查一次的共享上下文
  - `META_METRICS: set[str]` — 元指标 key 集合（第二轮判定用）

- [ ] **Step 1: 写指标基类与注册表**

创建 `achievement/metrics.py`，先写骨架：

```python
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
```

- [ ] **Step 2: 写共享上下文构建函数**

追加到 `metrics.py`：

```python
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
```

- [ ] **Step 3: 写累积型指标**

追加到 `metrics.py`：

```python
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
```

- [ ] **Step 4: 写隐藏型指标**

追加到 `metrics.py`：

```python
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
```

- [ ] **Step 5: 写元指标**

追加到 `metrics.py`：

```python
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
```

- [ ] **Step 6: 打开 apps.py 的注册钩子**

把 `achievement/apps.py` 改成：

```python
from django.apps import AppConfig


class AchievementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "achievement"

    def ready(self):
        # 导入以触发 @metric 装饰器把指标注册进 METRIC_REGISTRY
        import achievement.metrics  # noqa: F401
```

- [ ] **Step 7: 验证注册表与全量重算**

```bash
cd OnlineJudge
python manage.py shell -c "
from achievement.metrics import METRIC_REGISTRY, META_METRICS
print('registered:', len(METRIC_REGISTRY))
for k, m in METRIC_REGISTRY.items():
    print(' ', k, '|', m.name)
print('meta:', META_METRICS)
"
```

Expected: `registered: 16`，逐行列出全部指标，`meta: {'achievement_unlocked_count'}`。

拿一个真实用户跑一遍全量重算，确认每个指标都能算出值且不抛异常：

```bash
python manage.py shell -c "
from account.models import User
from achievement.metrics import METRIC_REGISTRY
u = User.objects.filter(is_disabled=False).first()
print('user:', u.username)
for k, m in METRIC_REGISTRY.items():
    print(f'  {k} = {m.recompute(u)}')
"
```

Expected: 每个指标打印一个整数或 `None`，无 traceback。**特别确认 `min_ac_code_chars` 对没有 AC 记录的用户返回 `None` 而不是 0。**

- [ ] **Step 8: Lint 并提交**

```bash
cd OnlineJudge
ruff format . && ruff check .
git add achievement/metrics.py achievement/apps.py
git commit -m "feat(achievement): 添加指标注册表与 16 个内置指标"
```

---

## Task 3: 判定核心、通知模块与判题链路接入

**Files:**
- Create: `OnlineJudge/achievement/checker.py`、`achievement/notify.py`、`achievement/tasks.py`
- Modify: `OnlineJudge/judge/tasks.py`

**Interfaces:**
- Consumes: `METRIC_REGISTRY`、`META_METRICS`、`build_ctx`（Task 2），三个模型（Task 1）
- Produces:
  - `checker.evaluate(user, metrics: dict, only_metrics: set | None = None) -> list[Achievement]` — 纯判定，返回应解锁但尚未解锁的成就
  - `checker.unlock(user, achievements: list, backfilled=False, notified=False) -> list[UserAchievement]` — 写库 + 更新 `unlock_count`
  - `checker.run_for_submission(user_id: int, submission) -> list[UserAchievement]` — 完整两轮流程
  - `notify.notify_achievements(user_id: int, records: list[UserAchievement]) -> None`
  - `notify.notify_badges(user_id: int, badges: list) -> None`
  - `tasks.check_achievements.send(user_id, submission_id)`

- [ ] **Step 1: 写 `achievement/checker.py`**

```python
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


def get_or_create_stat(user):
    stat, _ = UserStat.objects.get_or_create(user=user)
    return stat


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
        # 否则 min_ac_code_chars 这类极小值指标会对新用户恒成立
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
    for key in META_METRICS:
        value = METRIC_REGISTRY[key].recompute(user)
        if value is None:
            stat.metrics.pop(key, None)
        else:
            stat.metrics[key] = value
    stat.save(update_fields=["metrics", "update_time"])
    second = unlock(user, evaluate(user, stat.metrics, only_metrics=META_METRICS))

    return first + second
```

- [ ] **Step 2: 写 `achievement/notify.py`**

```python
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
```

- [ ] **Step 3: 写 `achievement/tasks.py`**

```python
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
```

- [ ] **Step 4: 接入判题链路**

修改 `judge/tasks.py`，在 `judge_task` 末尾投递。**必须挂在 actor 末尾而不是 dispatcher 内部**：`JudgeDispatcher.judge()` 对比赛分支在 `judge/dispatcher.py:213` 会提前 `return`，挂在里面会漏；挂在这里同时覆盖 `JudgeDispatcher` 和 `SQLJudgeDispatcher` 两条链路。

改成：

```python
import dramatiq

from account.models import User
from achievement.tasks import check_achievements
from judge.dispatcher import JudgeDispatcher
from judge.sql_dispatcher import SQLJudgeDispatcher
from submission.models import Submission
from utils.shortcuts import DRAMATIQ_WORKER_ARGS


@dramatiq.actor(**DRAMATIQ_WORKER_ARGS())
def judge_task(submission_id, problem_id):
    submission = Submission.objects.get(id=submission_id)
    if User.objects.get(id=submission.user_id).is_disabled:
        return
    # SQL 题不依赖 JudgeServer 沙箱，在 worker 内用 sqlite3 判题
    if submission.language == "SQL":
        SQLJudgeDispatcher(submission_id, problem_id).judge()
    else:
        JudgeDispatcher(submission_id, problem_id).judge()

    # 判题结束后异步判定成就；投递失败不影响判题结果
    check_achievements.send(submission.user_id, submission_id)
```

- [ ] **Step 5: 手动验证判定流程**

先造一个必然达成的成就，再拿一条已有的练习提交跑一遍：

```bash
cd OnlineJudge
python manage.py shell -c "
from account.models import User
from achievement.models import Achievement, Operator, UserAchievement, UserStat
from achievement import checker
from submission.models import Submission

a = Achievement.objects.create(name='初次提交', description='提交一次代码', icon='🎯', metric='submission_count', operator=Operator.GTE, threshold=1)
sub = Submission.objects.filter(contest_id__isnull=True).order_by('-create_time').first()
user = User.objects.get(id=sub.user_id)
UserStat.objects.filter(user=user).delete()
UserAchievement.objects.filter(user=user).delete()

records = checker.run_for_submission(user, sub)
print('unlocked:', [r.achievement.name for r in records])
print('metrics:', UserStat.objects.get(user=user).metrics)
a.refresh_from_db()
print('unlock_count:', a.unlock_count)

UserAchievement.objects.filter(user=user).delete()
a.delete()
print('cleaned')
"
```

Expected: `unlocked: ['初次提交']`，`metrics` 里出现 `submission_count` 等 key，`unlock_count: 1`，最后打印 `cleaned`。

再验证比赛提交被跳过：

```bash
python manage.py shell -c "
from account.models import User
from achievement import checker
from submission.models import Submission
sub = Submission.objects.filter(contest_id__isnull=False).first()
if sub is None:
    print('no contest submission, skip check')
else:
    user = User.objects.get(id=sub.user_id)
    print('result:', checker.run_for_submission(user, sub))
"
```

Expected: 打印 `result: []`（或提示无比赛提交可测）。

- [ ] **Step 6: Lint 并提交**

```bash
cd OnlineJudge
ruff format . && ruff check .
git add achievement/checker.py achievement/notify.py achievement/tasks.py judge/tasks.py
git commit -m "feat(achievement): 添加判定核心、通知模块并接入判题链路"
```

---

## Task 4: 用户侧 API

**Files:**
- Create: `OnlineJudge/achievement/serializers.py`、`achievement/views/oj.py`、`achievement/urls/oj.py`
- Modify: `OnlineJudge/oj/urls.py`

**Interfaces:**
- Consumes: 三个模型、`METRIC_REGISTRY`
- Produces: 四个用户侧端点
  - `GET /api/achievements?name=<username>`
  - `GET /api/achievements/summary?name=<username>`
  - `GET /api/achievements/pending`
  - `POST /api/achievements/pending/read`，body `{"ids": [1, 2]}`

- [ ] **Step 1: 写 `achievement/serializers.py`**

隐藏成就的打码必须在序列化层完成——未解锁的隐藏成就绝不能把真实 `name`/`description` 下发到前端，否则打开 DevTools 就能看光。

```python
from django.conf import settings
from django.core.cache import cache
from rest_framework import serializers

from account.models import User
from achievement.models import Achievement


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

    class Meta:
        model = Achievement
        fields = (
            "id", "name", "description", "icon", "rarity", "hidden", "metric",
            "operator", "threshold", "unlocked", "unlock_time", "backfilled",
            "progress", "unlock_rate",
        )

    def _masked(self, obj):
        return obj.hidden and not getattr(obj, "unlocked", False)

    def get_name(self, obj):
        return "???" if self._masked(obj) else obj.name

    def get_description(self, obj):
        return "达成条件保密" if self._masked(obj) else obj.description

    def get_icon(self, obj):
        return "❓" if self._masked(obj) else obj.icon

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
        from achievement.models import UserAchievement

        model = UserAchievement
        fields = ("id", "name", "description", "icon", "rarity")
```

- [ ] **Step 2: 写 `achievement/views/oj.py`**

```python
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
        return self.success({
            "username": user.username,
            "achievements": AchievementSerializer(achievements, many=True).data,
        })


class AchievementSummaryAPI(APIView):
    @login_required
    def get(self, request):
        user = _resolve_user(request)
        if user is None:
            return self.error("用户不存在")

        total_by_rarity = dict(
            Achievement.objects.filter(visible=True).values_list("rarity").annotate(c=Count("id"))
        )
        unlocked_by_rarity = dict(
            UserAchievement.objects.filter(user=user, achievement__visible=True)
            .values_list("achievement__rarity")
            .annotate(c=Count("id"))
        )
        total = sum(total_by_rarity.values())
        unlocked = sum(unlocked_by_rarity.values())

        recent = list(
            UserAchievement.objects.filter(user=user, achievement__visible=True)
            .select_related("achievement")
            .order_by("-unlock_time")[:5]
        )

        return self.success({
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
        })


class AchievementPendingAPI(APIView):
    @login_required
    def get(self, request):
        """返回尚未弹过的解锁记录。前端在布局层路由切换时拉取。"""
        records = (
            UserAchievement.objects.filter(user=request.user, notified=False, achievement__visible=True)
            .select_related("achievement")
            .order_by("unlock_time")
        )
        return self.success(PendingAchievementSerializer(records, many=True).data)

    @login_required
    def post(self, request):
        """弹完后标记已读，避免下次导航重复弹。body: {"ids": [成就 id]}"""
        ids = request.data.get("ids") or []
        if not isinstance(ids, list):
            return self.error("参数错误")
        UserAchievement.objects.filter(user=request.user, achievement_id__in=ids).update(notified=True)
        return self.success("ok")
```

- [ ] **Step 3: 写 `achievement/urls/oj.py`**

```python
from django.urls import path

from achievement.views.oj import AchievementListAPI, AchievementPendingAPI, AchievementSummaryAPI

urlpatterns = [
    path("achievements", AchievementListAPI.as_view(), name="achievement_list_api"),
    path("achievements/summary", AchievementSummaryAPI.as_view(), name="achievement_summary_api"),
    path("achievements/pending", AchievementPendingAPI.as_view(), name="achievement_pending_api"),
]
```

> 待读标记复用 `AchievementPendingAPI` 的 `post`，因此不需要单独的 `pending/read` 路径。**Spec 里写的 `POST /api/achievements/pending/read` 以此实现为准：`POST /api/achievements/pending`。** 前端 Task 8 按这个路径写。

- [ ] **Step 4: 注册路由**

在 `oj/urls.py` 的 `urlpatterns` 末尾（`class_pk` 那行之后）加：

```python
    path("api/", include("achievement.urls.oj")),
```

- [ ] **Step 5: 验证端点**

启动开发服务器：

```bash
cd OnlineJudge
python dev.py
```

另开一个终端，先造两条成就（一条普通、一条隐藏），然后用浏览器登录后访问接口。取一个已登录会话的 cookie 最简单的办法是直接在浏览器地址栏打开：

```
http://localhost:8000/api/achievements
http://localhost:8000/api/achievements/summary
http://localhost:8000/api/achievements/pending
```

造数据：

```bash
python manage.py shell -c "
from achievement.models import Achievement, Operator, Rarity
Achievement.objects.create(name='初出茅庐', description='通过 1 道题', icon='🌱', metric='accepted_count', operator=Operator.GTE, threshold=1, rarity=Rarity.BRONZE, order=1)
Achievement.objects.create(name='夜猫子', description='凌晨提交 10 次', icon='🦉', metric='midnight_submissions', operator=Operator.GTE, threshold=10, rarity=Rarity.SILVER, hidden=True, order=2)
print('seeded')
"
```

Expected:
- `/api/achievements` 返回 `data.achievements` 数组，其中「夜猫子」若未解锁，`name` 为 `"???"`、`description` 为 `"达成条件保密"`、`icon` 为 `"❓"`、`progress` 为 `null`
- 「初出茅庐」的 `progress` 是一个数字，`unlock_rate` 是 0~100 的浮点数
- `/api/achievements/summary` 返回 `total`、`unlocked`、`percent`、`rarity` 四档、`recent`
- `/api/achievements/pending` 返回数组（可能为空）

- [ ] **Step 6: Lint 并提交**

```bash
cd OnlineJudge
ruff format . && ruff check .
git add achievement/serializers.py achievement/views/oj.py achievement/urls/oj.py oj/urls.py
git commit -m "feat(achievement): 添加用户侧成就 API"
```

---

## Task 5: 管理侧 API 与阈值下调补发

**Files:**
- Create: `OnlineJudge/achievement/views/admin.py`、`achievement/urls/admin.py`
- Modify: `OnlineJudge/achievement/tasks.py`、`OnlineJudge/oj/urls.py`

**Interfaces:**
- Consumes: `Achievement`、`METRIC_REGISTRY`、`checker.evaluate`/`unlock`
- Produces:
  - `GET/POST/PUT/DELETE /api/admin/achievement`
  - `GET /api/admin/achievement/metrics`
  - `tasks.rescan_achievement.send(achievement_id)`

- [ ] **Step 1: 加补发任务到 `achievement/tasks.py`**

追加：

```python
@dramatiq.actor(**DRAMATIQ_WORKER_ARGS())
def rescan_achievement(achievement_id):
    """新建成就或调低阈值后，补发给已达标的存量用户。

    判定只在判题时发生，因此后台改了阈值不会自动补发，必须显式扫一遍。
    """
    from django.db.models import IntegerField
    from django.db.models.fields.json import KeyTextTransform
    from django.db.models.functions import Cast

    from achievement.models import Achievement, Operator, UserAchievement, UserStat
    from achievement.notify import notify_achievements

    try:
        achievement = Achievement.objects.get(id=achievement_id, visible=True)
    except Achievement.DoesNotExist:
        return

    # JSONField 的默认比较是 JSON 值比较，数字会按字符串序比（"9" > "50"），
    # 必须显式 cast 成整数，否则筛出来的用户是错的
    qs = UserStat.objects.filter(metrics__has_key=achievement.metric).annotate(
        v=Cast(KeyTextTransform(achievement.metric, "metrics"), IntegerField())
    )
    if achievement.operator == Operator.GTE:
        qs = qs.filter(v__gte=achievement.threshold)
    else:
        qs = qs.filter(v__lte=achievement.threshold)

    already = set(UserAchievement.objects.filter(achievement=achievement).values_list("user_id", flat=True))
    for stat in qs.select_related("user").iterator():
        if stat.user_id in already:
            continue
        try:
            records = checker.unlock(stat.user, [achievement])
            notify_achievements(stat.user_id, records)
        except Exception as e:
            logger.error(f"rescan_achievement failed for user {stat.user_id}: {e}")
```

- [ ] **Step 2: 写 `achievement/views/admin.py`**

```python
from account.decorators import super_admin_required
from achievement.metrics import METRIC_REGISTRY
from achievement.models import Achievement
from achievement.tasks import rescan_achievement
from utils.api import APIView
from utils.shortcuts import check_is_id


class AchievementAdminAPI(APIView):
    @super_admin_required
    def get(self, request):
        achievement_id = request.GET.get("id")
        if achievement_id:
            try:
                achievement = Achievement.objects.get(id=achievement_id)
            except Achievement.DoesNotExist:
                return self.error("成就不存在")
            return self.success(_serialize(achievement))
        return self.success([_serialize(a) for a in Achievement.objects.all()])

    @super_admin_required
    def post(self, request):
        data = request.data
        error = _validate(data)
        if error:
            return self.error(error)
        achievement = Achievement.objects.create(
            name=data["name"],
            description=data["description"],
            icon=data["icon"],
            rarity=data["rarity"],
            hidden=data.get("hidden", False),
            metric=data["metric"],
            operator=data["operator"],
            threshold=data["threshold"],
            visible=data.get("visible", True),
            order=data.get("order", 0),
        )
        # 新建成就需要补发给已达标的存量用户
        rescan_achievement.send(achievement.id)
        return self.success(_serialize(achievement))

    @super_admin_required
    def put(self, request):
        data = request.data
        if not check_is_id(data.get("id")):
            return self.error("参数错误")
        try:
            achievement = Achievement.objects.get(id=data["id"])
        except Achievement.DoesNotExist:
            return self.error("成就不存在")
        error = _validate(data)
        if error:
            return self.error(error)

        old_threshold = achievement.threshold
        old_operator = achievement.operator
        for field in ("name", "description", "icon", "rarity", "hidden", "metric", "operator", "threshold", "visible", "order"):
            if field in data:
                setattr(achievement, field, data[field])
        achievement.save()

        # 条件放宽（gte 调低阈值 / lte 调高阈值 / 换了比较符）时补发
        loosened = (
            achievement.operator != old_operator
            or (achievement.operator == "gte" and achievement.threshold < old_threshold)
            or (achievement.operator == "lte" and achievement.threshold > old_threshold)
        )
        if loosened and achievement.visible:
            rescan_achievement.send(achievement.id)
        return self.success(_serialize(achievement))

    @super_admin_required
    def delete(self, request):
        achievement_id = request.GET.get("id")
        if not check_is_id(achievement_id):
            return self.error("参数错误")
        Achievement.objects.filter(id=achievement_id).delete()
        return self.success("删除成功")


class AchievementMetricAdminAPI(APIView):
    @super_admin_required
    def get(self, request):
        """供后台指标下拉框使用。这里的列表就是代码里注册了什么。"""
        return self.success([
            {"key": key, "name": m.name, "help_text": m.help_text}
            for key, m in METRIC_REGISTRY.items()
        ])


def _validate(data):
    for field in ("name", "description", "icon", "rarity", "metric", "operator"):
        if not data.get(field):
            return f"{field} 不能为空"
    if data["metric"] not in METRIC_REGISTRY:
        return "指标不存在"
    if data["operator"] not in ("gte", "lte"):
        return "比较符不合法"
    if not isinstance(data.get("threshold"), int):
        return "阈值必须是整数"
    return None


def _serialize(a):
    return {
        "id": a.id,
        "name": a.name,
        "description": a.description,
        "icon": a.icon,
        "rarity": a.rarity,
        "hidden": a.hidden,
        "metric": a.metric,
        "metric_name": METRIC_REGISTRY[a.metric].name if a.metric in METRIC_REGISTRY else a.metric,
        "operator": a.operator,
        "threshold": a.threshold,
        "visible": a.visible,
        # 后台列表必须显示这个：阈值配错时学生永远拿不到也永远不会来问，
        # 这个计数器是唯一的仪表盘
        "unlock_count": a.unlock_count,
        "order": a.order,
        "create_time": a.create_time,
    }
```

- [ ] **Step 3: 写 `achievement/urls/admin.py`**

```python
from django.urls import path

from achievement.views.admin import AchievementAdminAPI, AchievementMetricAdminAPI

urlpatterns = [
    path("achievement", AchievementAdminAPI.as_view(), name="achievement_admin_api"),
    path("achievement/metrics", AchievementMetricAdminAPI.as_view(), name="achievement_metric_admin_api"),
]
```

- [ ] **Step 4: 注册路由**

在 `oj/urls.py` 加：

```python
    path("api/admin/", include("achievement.urls.admin")),
```

- [ ] **Step 5: 验证补发逻辑**

```bash
cd OnlineJudge
python manage.py shell -c "
from achievement.models import Achievement, Operator, UserAchievement, UserStat
from achievement.tasks import rescan_achievement
from account.models import User

# 造一个有指标的用户
u = User.objects.filter(is_disabled=False).first()
stat, _ = UserStat.objects.get_or_create(user=u)
stat.metrics['submission_count'] = 100
stat.save()

a = Achievement.objects.create(name='补发测试', description='d', icon='🔁', metric='submission_count', operator=Operator.GTE, threshold=9)
print('before:', UserAchievement.objects.filter(achievement=a).count())
rescan_achievement(a.id)   # 直接同步调用 actor 函数体
print('after:', UserAchievement.objects.filter(achievement=a).count())

UserAchievement.objects.filter(achievement=a).delete()
a.delete()
print('cleaned')
"
```

Expected: `before: 0`，`after: 1`，`cleaned`。

**特别验证 JSONB 的字符串序陷阱**：把上面的 `threshold=9` 换成 `threshold=9`、`metrics['submission_count'] = 100`。如果 cast 写错，`"100" >= "9"` 按字符串比较为 `False`，`after` 会是 `0`。看到 `after: 1` 才说明 cast 正确。

- [ ] **Step 6: Lint 并提交**

```bash
cd OnlineJudge
ruff format . && ruff check .
git add achievement/views/admin.py achievement/urls/admin.py achievement/tasks.py oj/urls.py
git commit -m "feat(achievement): 添加管理侧成就 API 与阈值补发"
```

---

## Task 6: 全量重算管理命令

**Files:**
- Create: `OnlineJudge/achievement/management/commands/recompute_achievements.py`

**Interfaces:**
- Consumes: `METRIC_REGISTRY`、`checker.evaluate`/`unlock`
- Produces: `python manage.py recompute_achievements [--user <id>] [--silent]`

- [ ] **Step 1: 写命令**

```python
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
            records += checker.unlock(
                user, checker.evaluate(user, metrics, only_metrics=META_METRICS), backfilled=True, notified=silent
            )

            total_unlocked += len(records)
            if index % 50 == 0:
                self.stdout.write(f"processed {index}/{total_users}")

        self.stdout.write(self.style.SUCCESS(f"完成：{total_users} 个用户，新解锁 {total_unlocked} 条"))
```

> 注意：重算时丢弃了 `_active_dates` / `_languages` 等下划线前缀的增量辅助 key。这是有意的——`recompute` 直接算出终值，辅助 key 会在下一次判题的 `on_submission` 中自然重建。但 `active_days`、`languages_used`、`max_ac_in_one_day`、`max_ac_streak_days` 这四个指标在重算后的第一次判题会**从辅助 key 缺失的状态重新累积**，可能导致数值短暂偏低。**因此重算后应立刻再跑一次重算是无效的；正确做法是重算命令只在低峰期执行，且执行后不依赖增量值的绝对精确性——这些指标的成就阈值判定用的是 max 语义，不会回退。**

- [ ] **Step 2: 单用户试跑**

```bash
cd OnlineJudge
python manage.py shell -c "
from account.models import User
u = User.objects.filter(is_disabled=False).first()
print('test user id:', u.id, u.username)
"
```

用上面打印的 id：

```bash
python manage.py recompute_achievements --user <上面的id>
```

Expected: 输出 `完成：1 个用户，新解锁 N 条`，无 traceback。

- [ ] **Step 3: 检查重算结果**

```bash
python manage.py shell -c "
from account.models import User
from achievement.models import UserStat, UserAchievement
u = User.objects.filter(is_disabled=False).first()
s = UserStat.objects.get(user=u)
print('metrics keys:', sorted(s.metrics.keys()))
print('unlocked:', [(r.achievement.name, r.backfilled, r.notified) for r in UserAchievement.objects.filter(user=u).select_related('achievement')])
"
```

Expected: `metrics keys` 不含 `min_ac_code_chars`（若该用户无 AC 记录），解锁记录的 `backfilled` 为 `True`。

- [ ] **Step 4: 验证 `--silent`**

```bash
python manage.py shell -c "
from achievement.models import UserAchievement
UserAchievement.objects.all().delete()
print('cleared')
"
python manage.py recompute_achievements --silent
python manage.py shell -c "
from achievement.models import UserAchievement
print('total:', UserAchievement.objects.count())
print('unnotified:', UserAchievement.objects.filter(notified=False).count())
"
```

Expected: `unnotified: 0` —— `--silent` 下所有补发记录都是已通知状态。

- [ ] **Step 5: Lint 并提交**

```bash
cd OnlineJudge
ruff format . && ruff check .
git add achievement/management
git commit -m "feat(achievement): 添加全量重算管理命令"
```

---

## Task 7: 题单奖章接入通知通道

**Files:**
- Modify: `OnlineJudge/problemset/views/oj.py:231-247`

**Interfaces:**
- Consumes: `achievement.notify.notify_badges`
- Produces: 无新接口，只修复现有 `_check_badges` 并接通知

- [ ] **Step 1: 重写 `_check_badges`**

把 `problemset/views/oj.py` 的 `_check_badges` 方法整体替换为：

```python
    def _check_badges(self, progress):
        """检查是否获得奖章。

        一次查询取出全部已获奖章 id，内存比对，避免逐条 exists()（原来的 N+1）。
        用 get_or_create 避免并发重复提交撞 unique constraint 抛异常。
        新获得的奖章推送给用户——接入前奖章是静默入库的，学生根本不知道自己拿到了。
        """
        badges = list(ProblemSetBadge.objects.filter(problemset=progress.problemset))
        if not badges:
            return

        owned = set(
            UserBadge.objects.filter(user=progress.user, badge__in=badges).values_list("badge_id", flat=True)
        )

        earned = []
        for badge in badges:
            if badge.id in owned:
                continue

            if badge.condition_type == BadgeConditionType.ALL_PROBLEMS:
                hit = progress.total_problems_count > 0 and progress.completed_problems_count == progress.total_problems_count
            elif badge.condition_type == BadgeConditionType.PROBLEM_COUNT:
                hit = progress.completed_problems_count >= badge.condition_value
            elif badge.condition_type == BadgeConditionType.SCORE:
                hit = progress.total_score >= badge.condition_value
            else:
                hit = False

            if hit:
                _, created = UserBadge.objects.get_or_create(user=progress.user, badge=badge)
                if created:
                    earned.append(badge)

        if earned:
            notify_badges(progress.user_id, earned)
```

- [ ] **Step 2: 加 import**

在 `problemset/views/oj.py` 的 import 区加：

```python
from achievement.notify import notify_badges
```

- [ ] **Step 3: 验证奖章逻辑仍正确且不再 N+1**

```bash
cd OnlineJudge
python manage.py shell -c "
from django.db import connection, reset_queries
from django.test.utils import CaptureQueriesContext
from problemset.models import ProblemSetBadge, ProblemSetProgress, UserBadge

progress = ProblemSetProgress.objects.filter(problemset__problemsetbadge__isnull=False).first()
if progress is None:
    print('no problemset with badges, skip')
else:
    badge_count = ProblemSetBadge.objects.filter(problemset=progress.problemset).count()
    print('badges in this problemset:', badge_count)
    from problemset.views.oj import ProblemSetProgressAPI
    api = ProblemSetProgressAPI()
    with CaptureQueriesContext(connection) as ctx:
        api._check_badges(progress)
    print('queries used:', len(ctx))
"
```

Expected: `queries used` 是个小常数（约 2–3），**不随该题单的奖章数量线性增长**。改动前这里会是 `1 + badge_count` 条。

> 若 `ProblemSetProgressAPI` 不是 `_check_badges` 所在的类名，用 `grep -n "_check_badges" problemset/views/oj.py` 找到实际类名替换。

- [ ] **Step 4: 验证重复调用不抛异常**

```bash
python manage.py shell -c "
from problemset.models import ProblemSetProgress
from problemset.views.oj import ProblemSetProgressAPI
progress = ProblemSetProgress.objects.filter(problemset__problemsetbadge__isnull=False).first()
if progress:
    api = ProblemSetProgressAPI()
    api._check_badges(progress)
    api._check_badges(progress)
    api._check_badges(progress)
    print('no IntegrityError')
else:
    print('skip')
"
```

Expected: 打印 `no IntegrityError`。改动前第二次调用若并发写入会抛 `IntegrityError`。

- [ ] **Step 5: Lint 并提交**

```bash
cd OnlineJudge
ruff format . && ruff check .
git add problemset/views/oj.py
git commit -m "fix(problemset): 奖章判定修复 N+1 与并发冲突并接入通知"
```

---

## Task 8: 前端 API 层、类型与 WebSocket 分流修复

**Files:**
- Create: `ojnext/src/oj/achievement/api.ts`
- Modify: `ojnext/src/utils/types.ts`、`ojnext/src/oj/problem/composables/useSubmissionMonitor.ts`

**Interfaces:**
- Consumes: Task 4 的四个用户侧端点
- Produces:
  - `Achievement`、`AchievementSummary`、`PendingAchievement` 三个 TS 类型
  - `getAchievements(name?)`、`getAchievementSummary(name?)`、`getPendingAchievements()`、`markAchievementsRead(ids)`

- [ ] **Step 1: 加类型到 `src/utils/types.ts`**

追加：

```typescript
export type AchievementRarity = "bronze" | "silver" | "gold" | "platinum"

export interface Achievement {
  id: number
  name: string
  description: string
  icon: string
  rarity: AchievementRarity
  hidden: boolean
  metric: string
  operator: "gte" | "lte"
  threshold: number
  unlocked: boolean
  unlock_time: string | null
  backfilled: boolean
  progress: number | null
  unlock_rate: number
}

export interface AchievementRarityStat {
  rarity: AchievementRarity
  label: string
  total: number
  unlocked: number
}

export interface PendingAchievement {
  id: number
  name: string
  description: string
  icon: string
  rarity: AchievementRarity
}

export interface AchievementSummary {
  username: string
  total: number
  unlocked: number
  percent: number
  rarity: AchievementRarityStat[]
  recent: PendingAchievement[]
}
```

- [ ] **Step 2: 写 `src/oj/achievement/api.ts`**

```typescript
import http from "utils/http"
import type {
  Achievement,
  AchievementSummary,
  PendingAchievement,
} from "utils/types"

export function getAchievements(name?: string) {
  return http.get<{ username: string; achievements: Achievement[] }>(
    "achievements",
    { params: name ? { name } : {} },
  )
}

export function getAchievementSummary(name?: string) {
  return http.get<AchievementSummary>("achievements/summary", {
    params: name ? { name } : {},
  })
}

export function getPendingAchievements() {
  return http.get<PendingAchievement[]>("achievements/pending")
}

export function markAchievementsRead(ids: number[]) {
  return http.post("achievements/pending", { ids })
}
```

> 若 `utils/http` 的默认导出不是 `http` 或基础路径不含 `/api`，照 `src/oj/api.ts` 里现有写法调整——**先读一遍 `src/oj/api.ts` 的前 20 行，照抄它的 import 与调用风格**。

- [ ] **Step 3: 修复 WebSocket 消息分流**

这是**必须改的现有文件**。`utils/websocket.py:push_to_user()` 复用了 `submission_update` 这个 channel layer handler 名（`submission/consumers.py` 文档中明写不可改名），只把自定义 `type` 塞进内层 data。`SubmissionWebSocket` 的泛型是 `SubmissionUpdate`，成就消息会被当成提交更新去读 `submission_id` / `result`。

先看现有 handler：

```bash
cd ojnext
grep -n "handleSubmissionUpdate" -A 20 src/oj/problem/composables/useSubmissionMonitor.ts
```

在 `handleSubmissionUpdate` 函数体**最开头**插入类型守卫。成就 store 要到 Task 10 才存在，所以本步骤先只丢弃非提交帧，Task 10 Step 4 再把成就帧分流给 store：

```typescript
  // push_to_user 复用了 submission_update 这个 channel handler，
  // 其他类型的消息（如成就通知）会走同一条 WebSocket 帧进来，必须先挡掉
  if (data.type !== "submission_update") {
    return
  }
```

- [ ] **Step 4: 验证类型检查与格式化**

```bash
cd ojnext
npm run build
npm fmt
```

Expected: 构建成功，无 TypeScript 报错。

- [ ] **Step 5: 提交**

```bash
cd ojnext
git add src/utils/types.ts src/oj/achievement/api.ts src/oj/problem/composables/useSubmissionMonitor.ts
git commit -m "feat(achievement): 添加成就 API 层与类型，修复 WebSocket 消息分流"
```

---

## Task 9: 奖杯馆页面

**Files:**
- Create: `ojnext/src/oj/achievement/index.vue`、`ojnext/src/oj/achievement/components/AchievementCard.vue`
- Modify: `ojnext/src/routes.ts`

**Interfaces:**
- Consumes: Task 8 的 `getAchievements`、`getAchievementSummary`，Task 8 的类型
- Produces: 路由 `/achievement?name=<username>`

- [ ] **Step 1: 写 `AchievementCard.vue`**

```vue
<script setup lang="ts">
import type { Achievement } from "utils/types"

const props = defineProps<{ achievement: Achievement }>()

const RARITY_COLOR: Record<string, string> = {
  bronze: "#b87333",
  silver: "#9fa6b2",
  gold: "#e0a300",
  platinum: "#7dd3fc",
}

const RARITY_LABEL: Record<string, string> = {
  bronze: "青铜",
  silver: "白银",
  gold: "黄金",
  platinum: "白金",
}

const masked = computed(
  () => props.achievement.hidden && !props.achievement.unlocked,
)

// 获得率低于 5% 的加稀有闪光边框
const isRare = computed(
  () => props.achievement.unlock_rate > 0 && props.achievement.unlock_rate < 5,
)

const percent = computed(() => {
  const { progress, threshold, operator } = props.achievement
  if (progress === null || operator === "lte") return 0
  if (threshold <= 0) return 100
  return Math.min(100, Math.round((progress / threshold) * 100))
})
</script>

<template>
  <n-card
    size="small"
    :class="{ locked: !achievement.unlocked, rare: isRare }"
    :style="{ borderColor: RARITY_COLOR[achievement.rarity] }"
  >
    <div class="row">
      <div class="icon">{{ achievement.icon }}</div>
      <div class="body">
        <div class="title">
          <span class="name">{{ achievement.name }}</span>
          <n-tag size="tiny" :color="{ borderColor: RARITY_COLOR[achievement.rarity], textColor: RARITY_COLOR[achievement.rarity] }">
            {{ RARITY_LABEL[achievement.rarity] }}
          </n-tag>
        </div>
        <div class="desc">{{ achievement.description }}</div>

        <div v-if="achievement.unlocked" class="meta">
          <span v-if="!achievement.backfilled && achievement.unlock_time">
            {{ new Date(achievement.unlock_time).toLocaleDateString() }} 获得
          </span>
          <span v-else>已获得</span>
          <span class="rate">仅 {{ achievement.unlock_rate }}% 的人获得</span>
        </div>

        <div v-else-if="!masked" class="meta">
          <n-progress
            type="line"
            :percentage="percent"
            :height="6"
            :show-indicator="false"
          />
          <span class="progress-text">
            {{ achievement.progress ?? 0 }} / {{ achievement.threshold }}
          </span>
        </div>

        <div v-else class="meta">
          <span class="rate">仅 {{ achievement.unlock_rate }}% 的人获得</span>
        </div>
      </div>
    </div>
  </n-card>
</template>

<style scoped>
.row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.icon {
  font-size: 32px;
  line-height: 1;
}
.body {
  flex: 1;
  min-width: 0;
}
.title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}
.desc {
  margin-top: 4px;
  font-size: 13px;
  opacity: 0.75;
}
.meta {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  opacity: 0.65;
}
.meta :deep(.n-progress) {
  flex: 1;
}
.progress-text {
  white-space: nowrap;
}
.locked {
  filter: grayscale(1);
  opacity: 0.55;
}
.rare {
  box-shadow: 0 0 12px rgba(125, 211, 252, 0.55);
}
</style>
```

- [ ] **Step 2: 写 `index.vue`**

```vue
<script setup lang="ts">
import {
  getAchievements,
  getAchievementSummary,
} from "oj/achievement/api"
import { getUserBadges } from "oj/api"
import type { Achievement, AchievementSummary } from "utils/types"
import AchievementCard from "./components/AchievementCard.vue"

const route = useRoute()
const name = computed(() => route.query.name as string | undefined)

const achievements = ref<Achievement[]>([])
const summary = ref<AchievementSummary | null>(null)
const badges = ref<any[]>([])
const tab = ref("all")
const loading = ref(true)

const filtered = computed(() => {
  if (tab.value === "unlocked")
    return achievements.value.filter((a) => a.unlocked)
  if (tab.value === "locked")
    return achievements.value.filter((a) => !a.unlocked)
  return achievements.value
})

async function load() {
  loading.value = true
  try {
    const [list, sum, badgeRes] = await Promise.all([
      getAchievements(name.value),
      getAchievementSummary(name.value),
      getUserBadges(name.value),
    ])
    achievements.value = list.achievements
    summary.value = sum
    badges.value = badgeRes ?? []
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(name, load)
</script>

<template>
  <div class="hall">
    <n-spin :show="loading">
      <n-card v-if="summary" class="overview">
        <div class="overview-row">
          <div class="percent">
            <div class="big">{{ summary.percent }}%</div>
            <div class="sub">
              {{ summary.unlocked }} / {{ summary.total }} 已获得
            </div>
          </div>
          <div class="rarity">
            <div v-for="r in summary.rarity" :key="r.rarity" class="rarity-item">
              <div class="rarity-label">{{ r.label }}</div>
              <div class="rarity-count">{{ r.unlocked }} / {{ r.total }}</div>
            </div>
          </div>
        </div>
      </n-card>

      <n-tabs v-model:value="tab" type="line" class="tabs">
        <n-tab name="all">全部</n-tab>
        <n-tab name="unlocked">已获得</n-tab>
        <n-tab name="locked">未获得</n-tab>
        <n-tab name="badges">题单奖章</n-tab>
      </n-tabs>

      <div v-if="tab !== 'badges'" class="grid">
        <AchievementCard
          v-for="a in filtered"
          :key="a.id"
          :achievement="a"
        />
      </div>

      <div v-else class="grid">
        <n-card v-for="b in badges" :key="b.id" size="small">
          <div class="badge-row">
            <img v-if="b.badge?.icon" :src="b.badge.icon" class="badge-icon" />
            <div>
              <div class="badge-name">{{ b.badge?.name }}</div>
              <div class="badge-desc">{{ b.badge?.description }}</div>
            </div>
          </div>
        </n-card>
        <n-empty v-if="!badges.length" description="还没有获得任何题单奖章" />
      </div>
    </n-spin>
  </div>
</template>

<style scoped>
.hall {
  max-width: 1100px;
  margin: 0 auto;
  padding: 16px;
}
.overview-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  flex-wrap: wrap;
}
.big {
  font-size: 40px;
  font-weight: 700;
  line-height: 1;
}
.sub {
  margin-top: 6px;
  font-size: 13px;
  opacity: 0.7;
}
.rarity {
  display: flex;
  gap: 20px;
}
.rarity-item {
  text-align: center;
}
.rarity-label {
  font-size: 12px;
  opacity: 0.7;
}
.rarity-count {
  font-weight: 600;
  margin-top: 2px;
}
.tabs {
  margin: 16px 0;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
}
.badge-row {
  display: flex;
  gap: 12px;
  align-items: center;
}
.badge-icon {
  width: 40px;
  height: 40px;
}
.badge-name {
  font-weight: 600;
}
.badge-desc {
  font-size: 12px;
  opacity: 0.7;
}
</style>
```

> `getUserBadges` 已存在于前端某个 api 文件中（Task 前先 `grep -rn "getUserBadges" src/` 确认它的导出位置与参数签名），把上面的 import 路径改成实际路径。

- [ ] **Step 3: 加路由**

在 `src/routes.ts` 的 `ojs` 子路由里，`user` 那一项之后加：

```typescript
    {
      path: "achievement",
      name: "achievement",
      component: () => import("oj/achievement/index.vue"),
      meta: { requiresAuth: true },
    },
```

- [ ] **Step 4: 浏览器验证**

```bash
cd ojnext
npm start
```

访问 `http://localhost:5173/achievement`，逐项确认：

- 顶部显示完成度百分比与四档稀有度计数
- 已解锁成就彩色，显示获得日期与获得率
- 未解锁的公开成就**灰度显示**且有进度条
- 未解锁的隐藏成就显示 `???`、描述为「达成条件保密」、图标为 `❓`、**没有进度条**
- 切到「题单奖章」tab 能看到奖章或空状态
- 访问 `/achievement?name=<其他用户名>` 能看到他人的成就

- [ ] **Step 5: 格式化并提交**

```bash
cd ojnext
npm fmt && npm run build
git add src/oj/achievement src/routes.ts
git commit -m "feat(achievement): 添加奖杯馆页面"
```

---

## Task 10: 全局解锁弹窗与 pending 拉取

**Files:**
- Create: `ojnext/src/shared/store/achievement.ts`、`ojnext/src/shared/components/AchievementToast.vue`
- Modify: `ojnext/src/shared/layout/default.vue`、`ojnext/src/oj/problem/composables/useSubmissionMonitor.ts`

**Interfaces:**
- Consumes: `getPendingAchievements`、`markAchievementsRead`（Task 8），`PendingAchievement` 类型
- Produces: `useAchievementStore()`，含 `queue`、`enqueue(items)`、`fetchPending()`、`shift()`

- [ ] **Step 1: 写 store**

```typescript
import { defineStore } from "pinia"
import {
  getPendingAchievements,
  markAchievementsRead,
} from "oj/achievement/api"
import type { PendingAchievement } from "utils/types"

export const useAchievementStore = defineStore("achievement", () => {
  const queue = ref<PendingAchievement[]>([])
  const current = ref<PendingAchievement | null>(null)

  function enqueue(items: PendingAchievement[]) {
    // 去重：WebSocket 推来的和 pending 拉来的可能是同一批
    const known = new Set([
      ...queue.value.map((i) => i.id),
      ...(current.value ? [current.value.id] : []),
    ])
    queue.value.push(...items.filter((i) => !known.has(i.id)))
  }

  async function fetchPending() {
    try {
      const items = await getPendingAchievements()
      enqueue(items ?? [])
    } catch {
      // 拉取失败静默处理，下次导航会再拉
    }
  }

  function next() {
    current.value = queue.value.shift() ?? null
    return current.value
  }

  async function markRead(id: number) {
    try {
      await markAchievementsRead([id])
    } catch {
      // 标记失败下次会重复弹一次，可接受
    }
  }

  return { queue, current, enqueue, fetchPending, next, markRead }
})
```

- [ ] **Step 2: 写 `AchievementToast.vue`**

```vue
<script setup lang="ts">
import { useAchievementStore } from "shared/store/achievement"

const store = useAchievementStore()
const { current, queue } = storeToRefs(store)
const visible = ref(false)

const RARITY_COLOR: Record<string, string> = {
  bronze: "#b87333",
  silver: "#9fa6b2",
  gold: "#e0a300",
  platinum: "#7dd3fc",
}

let timer: ReturnType<typeof setTimeout> | null = null

// 多个同时解锁时排队依次弹出，不重叠堆积
function playNext() {
  const item = store.next()
  if (!item) return
  visible.value = true
  timer = setTimeout(async () => {
    visible.value = false
    await store.markRead(item.id)
    setTimeout(playNext, 400)
  }, 3000)
}

watch(
  () => queue.value.length,
  (len) => {
    if (len > 0 && !visible.value) playNext()
  },
)

onUnmounted(() => {
  if (timer) clearTimeout(timer)
})
</script>

<template>
  <Transition name="slide">
    <div
      v-if="visible && current"
      class="toast"
      :style="{ borderColor: RARITY_COLOR[current.rarity] }"
    >
      <div class="icon">{{ current.icon }}</div>
      <div class="body">
        <div class="label">成就解锁</div>
        <div class="name">{{ current.name }}</div>
        <div class="desc">{{ current.description }}</div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.toast {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 3000;
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 14px 18px;
  border-radius: 10px;
  border: 2px solid;
  background: var(--n-color, rgba(24, 24, 28, 0.95));
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35);
  min-width: 260px;
}
.icon {
  font-size: 34px;
}
.label {
  font-size: 11px;
  letter-spacing: 2px;
  opacity: 0.6;
}
.name {
  font-weight: 700;
  margin-top: 2px;
}
.desc {
  font-size: 12px;
  opacity: 0.7;
  margin-top: 2px;
}
.slide-enter-active,
.slide-leave-active {
  transition: all 0.35s ease;
}
.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  transform: translateX(40px);
}
</style>
```

- [ ] **Step 3: 挂到布局层并在路由切换时拉 pending**

在 `src/shared/layout/default.vue` 的 `<template>` 末尾加：

```vue
  <AchievementToast />
```

在 `<script setup>` 里加：

```typescript
import AchievementToast from "shared/components/AchievementToast.vue"
import { useAchievementStore } from "shared/store/achievement"
import { useUserStore } from "shared/store/user"

const achievementStore = useAchievementStore()
const userStore = useUserStore()
const currentRoute = useRoute()

// WebSocket 不是常驻连接（只在问题页有提交监听时建连），
// 所以拉取才是主通道：任何页面、任何时刻解锁的成就最终都会弹到
watch(
  () => currentRoute.path,
  () => {
    if (userStore.isAuthed) achievementStore.fetchPending()
  },
  { immediate: true },
)
```

> `useUserStore` 的实际导出名与"是否已登录"的字段名以 `src/shared/store/` 下的实现为准——先 `grep -n "isAuthed\|isLogin\|export const useUserStore" src/shared/store/user.ts`，用实际的字段名替换 `userStore.isAuthed`。

- [ ] **Step 4: 补上 WebSocket 分流到 store**

回到 `src/oj/problem/composables/useSubmissionMonitor.ts`，把 Task 8 Step 3 写的类型守卫补全为：

```typescript
  // push_to_user 复用了 submission_update 这个 channel handler，
  // 成就通知会走同一条 WebSocket 帧进来，必须先分流出去
  if ((data as any).type === "achievement_unlocked") {
    useAchievementStore().enqueue((data as any).achievements ?? [])
    return
  }
  if (data.type !== "submission_update") {
    return
  }
```

并在文件顶部加 import：

```typescript
import { useAchievementStore } from "shared/store/achievement"
```

- [ ] **Step 5: 端到端验证**

后端造一条必然解锁的成就并清掉已读状态：

```bash
cd OnlineJudge
python manage.py shell -c "
from achievement.models import Achievement, Operator, UserAchievement
Achievement.objects.create(name='弹窗测试', description='提交一次代码', icon='🎉', metric='submission_count', operator=Operator.GTE, threshold=1, order=99)
UserAchievement.objects.update(notified=False)
print('ready')
"
```

前端刷新任意页面。Expected：右下角滑入奖杯弹窗，3 秒后淡出；若有多条待弹，依次弹出不重叠。

再验证不重复弹：**刷新页面**，Expected：不再弹出（已标记 `notified=True`）。

再验证判题当场即时弹：在问题页提交一次代码，Expected：判题结果出来后不到一秒弹出奖杯（走 WebSocket 而非等下次导航）。

清理测试数据：

```bash
python manage.py shell -c "
from achievement.models import Achievement, UserAchievement
a = Achievement.objects.filter(name='弹窗测试')
UserAchievement.objects.filter(achievement__in=a).delete()
a.delete()
print('cleaned')
"
```

- [ ] **Step 6: 格式化并提交**

```bash
cd ojnext
npm fmt && npm run build
git add src/shared/store/achievement.ts src/shared/components/AchievementToast.vue src/shared/layout/default.vue src/oj/problem/composables/useSubmissionMonitor.ts
git commit -m "feat(achievement): 添加全局解锁弹窗与待弹拉取"
```

---

## Task 11: 炫耀入口（个人主页摘要与排行榜徽章）

**Files:**
- Modify: `ojnext/src/oj/user/index.vue`、`ojnext/src/oj/rank/list.vue`

**Interfaces:**
- Consumes: `getAchievementSummary`（Task 8）

- [ ] **Step 1: 个人主页加成就摘要区**

在 `src/oj/user/index.vue` 的 `<script setup>` 加：

```typescript
import { getAchievementSummary } from "oj/achievement/api"
import type { AchievementSummary } from "utils/types"

const achievementSummary = ref<AchievementSummary | null>(null)

async function loadAchievementSummary() {
  try {
    achievementSummary.value = await getAchievementSummary(
      route.query.name as string | undefined,
    )
  } catch {
    achievementSummary.value = null
  }
}
```

把 `loadAchievementSummary()` 加进该页面现有的数据加载流程（文件里已有一个 `promises` 数组，把它 push 进去）。

在模板中合适位置（个人信息卡片之后）插入：

```vue
      <n-card v-if="achievementSummary" size="small" class="achievement-summary">
        <div class="achievement-head">
          <span class="achievement-title">
            成就 {{ achievementSummary.unlocked }} / {{ achievementSummary.total }}
            （{{ achievementSummary.percent }}%）
          </span>
          <n-button
            text
            type="primary"
            @click="
              router.push({
                path: '/achievement',
                query: route.query.name ? { name: route.query.name } : {},
              })
            "
          >
            查看全部
          </n-button>
        </div>
        <div class="achievement-recent">
          <n-tooltip v-for="a in achievementSummary.recent" :key="a.id">
            <template #trigger>
              <span class="achievement-icon">{{ a.icon }}</span>
            </template>
            {{ a.name }}
          </n-tooltip>
          <n-text v-if="!achievementSummary.recent.length" depth="3">
            还没有获得成就
          </n-text>
        </div>
      </n-card>
```

样式：

```css
.achievement-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.achievement-title {
  font-weight: 600;
}
.achievement-recent {
  margin-top: 10px;
  display: flex;
  gap: 10px;
  align-items: center;
}
.achievement-icon {
  font-size: 24px;
  cursor: default;
}
```

- [ ] **Step 2: 排行榜挂徽章**

后端在排行榜序列化里加成就信息成本较高，改用**前端按需拉取**：排行榜行数有限（一页几十行），页面加载后对可见用户批量取摘要会产生 N 次请求，不可接受。

**因此本步骤改为：在排行榜的用户名后加一个跳转奖杯馆的小图标，不显示徽章内容。** 这样零额外请求，仍然提供了炫耀入口。

在 `src/oj/rank/list.vue` 渲染用户名的列里，在用户名后追加一个按钮：

```vue
            <n-button
              text
              size="tiny"
              title="查看成就"
              @click.stop="router.push({ path: '/achievement', query: { name: row.user.username } })"
            >
              🏆
            </n-button>
```

> 该文件用的是 Naive UI DataTable 的 render 函数还是模板，取决于现有实现。先 `grep -n "username" src/oj/rank/list.vue` 确认渲染方式：若是 render 函数，用 `h(NButton, { text: true, size: "tiny", onClick: ... }, () => "🏆")` 等价改写。

- [ ] **Step 3: 浏览器验证**

- 访问 `/user`，Expected：看到「成就 N / M（X%）」摘要与最近获得的图标，点「查看全部」跳转 `/achievement`
- 访问 `/user?name=<他人>`，Expected：显示他人的成就摘要，「查看全部」跳转带上 `name` 参数
- 访问 `/rank`，Expected：每行用户名后有 🏆 按钮，点击跳到该用户的奖杯馆

- [ ] **Step 4: 格式化并提交**

```bash
cd ojnext
npm fmt && npm run build
git add src/oj/user/index.vue src/oj/rank/list.vue
git commit -m "feat(achievement): 个人主页与排行榜添加成就入口"
```

---

## Task 12: 管理后台成就配置页

**Files:**
- Create: `ojnext/src/admin/achievement/list.vue`、`ojnext/src/admin/achievement/components/AchievementModal.vue`、`ojnext/src/admin/achievement/api.ts`
- Modify: `ojnext/src/routes.ts`

**Interfaces:**
- Consumes: Task 5 的管理端点

- [ ] **Step 1: 写 `src/admin/achievement/api.ts`**

```typescript
import http from "utils/http"

export interface AdminAchievement {
  id: number
  name: string
  description: string
  icon: string
  rarity: string
  hidden: boolean
  metric: string
  metric_name: string
  operator: "gte" | "lte"
  threshold: number
  visible: boolean
  unlock_count: number
  order: number
  create_time: string
}

export interface MetricOption {
  key: string
  name: string
  help_text: string
}

export function getAdminAchievements() {
  return http.get<AdminAchievement[]>("admin/achievement")
}

export function getMetricOptions() {
  return http.get<MetricOption[]>("admin/achievement/metrics")
}

export function createAchievement(data: Partial<AdminAchievement>) {
  return http.post<AdminAchievement>("admin/achievement", data)
}

export function updateAchievement(data: Partial<AdminAchievement>) {
  return http.put<AdminAchievement>("admin/achievement", data)
}

export function deleteAchievement(id: number) {
  return http.delete("admin/achievement", { params: { id } })
}
```

> 路径前缀以 `src/admin/` 下现有 api 文件的写法为准（`grep -n "admin/problemset" src/admin/problemset/*.ts` 看它怎么拼路径），照抄。

- [ ] **Step 2: 写 `AchievementModal.vue`**

```vue
<script setup lang="ts">
import {
  createAchievement,
  getMetricOptions,
  updateAchievement,
  type AdminAchievement,
  type MetricOption,
} from "admin/achievement/api"

const props = defineProps<{
  show: boolean
  editing: AdminAchievement | null
}>()
const emit = defineEmits<{ "update:show": [boolean]; saved: [] }>()

const message = useMessage()
const metrics = ref<MetricOption[]>([])
const saving = ref(false)

const form = ref({
  name: "",
  description: "",
  icon: "🏆",
  rarity: "bronze",
  hidden: false,
  metric: "",
  operator: "gte" as "gte" | "lte",
  threshold: 1,
  visible: true,
  order: 0,
})

const metricOptions = computed(() =>
  metrics.value.map((m) => ({ label: `${m.name}（${m.key}）`, value: m.key })),
)

const metricHelp = computed(
  () => metrics.value.find((m) => m.key === form.value.metric)?.help_text ?? "",
)

watch(
  () => props.show,
  async (show) => {
    if (!show) return
    if (!metrics.value.length) metrics.value = await getMetricOptions()
    if (props.editing) {
      form.value = { ...form.value, ...props.editing }
    } else {
      form.value = {
        name: "",
        description: "",
        icon: "🏆",
        rarity: "bronze",
        hidden: false,
        metric: metrics.value[0]?.key ?? "",
        operator: "gte",
        threshold: 1,
        visible: true,
        order: 0,
      }
    }
  },
)

async function save() {
  if (!form.value.name || !form.value.metric) {
    message.error("名称和指标不能为空")
    return
  }
  saving.value = true
  try {
    if (props.editing) {
      await updateAchievement({ ...form.value, id: props.editing.id })
    } else {
      await createAchievement(form.value)
    }
    message.success("保存成功")
    emit("update:show", false)
    emit("saved")
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <n-modal
    :show="show"
    preset="card"
    style="width: 560px"
    :title="editing ? '编辑成就' : '新建成就'"
    @update:show="emit('update:show', $event)"
  >
    <n-form label-placement="left" :label-width="80">
      <n-form-item label="名称" required>
        <n-input v-model:value="form.name" placeholder="成就名称" />
      </n-form-item>
      <n-form-item label="描述" required>
        <n-input
          v-model:value="form.description"
          type="textarea"
          placeholder="达成条件的描述，展示给学生看"
        />
      </n-form-item>
      <n-form-item label="图标">
        <n-input v-model:value="form.icon" placeholder="emoji，例如 🦉" />
      </n-form-item>
      <n-form-item label="稀有度">
        <n-select
          v-model:value="form.rarity"
          :options="[
            { label: '青铜', value: 'bronze' },
            { label: '白银', value: 'silver' },
            { label: '黄金', value: 'gold' },
            { label: '白金', value: 'platinum' },
          ]"
        />
      </n-form-item>
      <n-form-item label="指标" required>
        <n-select
          v-model:value="form.metric"
          :options="metricOptions"
          filterable
        />
      </n-form-item>
      <n-form-item v-if="metricHelp" label=" ">
        <n-text depth="3">{{ metricHelp }}</n-text>
      </n-form-item>
      <n-form-item label="条件">
        <n-space align="center">
          <n-select
            v-model:value="form.operator"
            style="width: 130px"
            :options="[
              { label: '大于等于', value: 'gte' },
              { label: '小于等于', value: 'lte' },
            ]"
          />
          <n-input-number v-model:value="form.threshold" :min="0" />
        </n-space>
      </n-form-item>
      <n-form-item label="隐藏成就">
        <n-switch v-model:value="form.hidden" />
        <n-text depth="3" style="margin-left: 12px">
          未解锁时学生只能看到 ???
        </n-text>
      </n-form-item>
      <n-form-item label="上架">
        <n-switch v-model:value="form.visible" />
      </n-form-item>
      <n-form-item label="排序">
        <n-input-number v-model:value="form.order" />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="emit('update:show', false)">取消</n-button>
        <n-button type="primary" :loading="saving" @click="save">保存</n-button>
      </n-space>
    </template>
  </n-modal>
</template>
```

- [ ] **Step 3: 写 `list.vue`**

```vue
<script setup lang="ts">
import {
  deleteAchievement,
  getAdminAchievements,
  type AdminAchievement,
} from "admin/achievement/api"
import AchievementModal from "./components/AchievementModal.vue"

const message = useMessage()
const dialog = useDialog()

const list = ref<AdminAchievement[]>([])
const loading = ref(false)
const showModal = ref(false)
const editing = ref<AdminAchievement | null>(null)

async function load() {
  loading.value = true
  try {
    list.value = await getAdminAchievements()
  } finally {
    loading.value = false
  }
}

function create() {
  editing.value = null
  showModal.value = true
}

function edit(row: AdminAchievement) {
  editing.value = row
  showModal.value = true
}

function remove(row: AdminAchievement) {
  dialog.warning({
    title: "删除成就",
    content: `确定删除「${row.name}」？已解锁记录会一并删除。`,
    positiveText: "删除",
    negativeText: "取消",
    onPositiveClick: async () => {
      await deleteAchievement(row.id)
      message.success("已删除")
      load()
    },
  })
}

onMounted(load)
</script>

<template>
  <n-card title="成就管理">
    <template #header-extra>
      <n-button type="primary" @click="create">新建成就</n-button>
    </template>

    <n-alert type="info" style="margin-bottom: 12px">
      「已解锁人数」是唯一的仪表盘：配置一周后仍为 0，多半是阈值配错了而不是太难。
    </n-alert>

    <n-data-table
      :loading="loading"
      :data="list"
      :columns="[
        { title: '图标', key: 'icon', width: 60 },
        { title: '名称', key: 'name' },
        { title: '稀有度', key: 'rarity', width: 90 },
        { title: '指标', key: 'metric_name' },
        {
          title: '条件',
          key: 'threshold',
          width: 110,
          render: (row) =>
            `${row.operator === 'gte' ? '≥' : '≤'} ${row.threshold}`,
        },
        {
          title: '隐藏',
          key: 'hidden',
          width: 70,
          render: (row) => (row.hidden ? '是' : '—'),
        },
        {
          title: '上架',
          key: 'visible',
          width: 70,
          render: (row) => (row.visible ? '是' : '否'),
        },
        { title: '已解锁人数', key: 'unlock_count', width: 110 },
        {
          title: '操作',
          key: 'actions',
          width: 130,
          render: (row) =>
            h(NSpace, {}, () => [
              h(NButton, { text: true, type: 'primary', onClick: () => edit(row) }, () => '编辑'),
              h(NButton, { text: true, type: 'error', onClick: () => remove(row) }, () => '删除'),
            ]),
        },
      ]"
      :row-key="(row) => row.id"
    />

    <AchievementModal
      v-model:show="showModal"
      :editing="editing"
      @saved="load"
    />
  </n-card>
</template>
```

> `NSpace` / `NButton` / `h` 在 render 函数里使用时，Naive UI 组件由 `unplugin-vue-components` 自动导入**只对模板生效**，render 函数里需要显式 `import { NButton, NSpace } from "naive-ui"`。`h` 由 Vue 自动导入。**请在 `<script setup>` 顶部加这行 import。**

- [ ] **Step 4: 加管理后台路由**

在 `src/routes.ts` 的 `admins` 子路由里，参照 `problemset/list` 那几项的写法加：

```typescript
    {
      path: "achievement/list",
      name: "admin achievement list",
      component: () => import("admin/achievement/list.vue"),
      meta: { requiresSuperAdmin: true },
    },
```

> `meta` 的实际字段以同文件里 problemset 管理路由的写法为准，照抄它的 meta。若管理后台有侧边栏菜单配置文件（`grep -rn "problemset/list" src/shared/layout/admin.vue src/admin/`），把成就管理也加进菜单。

- [ ] **Step 5: 浏览器验证**

用超级管理员账号访问管理后台的成就管理页，逐项确认：

- 列表显示图标、名称、稀有度、指标中文名、条件、隐藏、上架、**已解锁人数**
- 点「新建成就」，指标下拉框能看到 16 个指标，选中后下方显示该指标的说明文字
- 保存后列表刷新出新成就
- 编辑一条成就把阈值**调低**，保存后等几秒，回到 `/achievement` 页面确认该成就被补发（这验证了 Task 5 的 `rescan_achievement`）
- 删除成就有二次确认

- [ ] **Step 6: 格式化并提交**

```bash
cd ojnext
npm fmt && npm run build
git add src/admin/achievement src/routes.ts
git commit -m "feat(achievement): 添加管理后台成就配置页"
```

---

## Task 13: 上线补发与收尾

**Files:** 无代码改动，纯运维步骤 + 一条一次性提示

- [ ] **Step 1: 配置首批成就**

用管理后台配出首批成就。建议每个指标至少配一条，累积型设 `hidden=False`、隐藏型设 `hidden=True`。参考配置（可直接在后台照着填）：

| 名称 | 图标 | 指标 | 条件 | 稀有度 | 隐藏 |
|---|---|---|---|---|---|
| 初出茅庐 | 🌱 | accepted_count | ≥ 1 | 青铜 | 否 |
| 小有所成 | 📗 | accepted_count | ≥ 10 | 青铜 | 否 |
| 百题斩 | 📚 | accepted_count | ≥ 100 | 黄金 | 否 |
| 坚持三天 | 📅 | max_ac_streak_days | ≥ 3 | 青铜 | 否 |
| 坚持一周 | 🗓️ | max_ac_streak_days | ≥ 7 | 白银 | 否 |
| 博采众长 | 🌐 | languages_used | ≥ 3 | 白银 | 否 |
| 题单收藏家 | 🎖️ | badge_count | ≥ 10 | 黄金 | 否 |
| 一发入魂 | 🎯 | first_try_ac_count | ≥ 1 | 青铜 | 是 |
| 神射手 | 🏹 | first_try_ac_count | ≥ 20 | 黄金 | 是 |
| 夜猫子 | 🦉 | midnight_submissions | ≥ 10 | 白银 | 是 |
| 作息已崩坏 | 🌙 | midnight_submissions | ≥ 100 | 黄金 | 是 |
| 与编译器搏斗 | 💥 | compile_error_count | ≥ 50 | 青铜 | 是 |
| 屡败屡战 | 🔥 | max_wa_before_ac | ≥ 20 | 白银 | 是 |
| 高产日 | ⚡ | max_ac_in_one_day | ≥ 10 | 白银 | 是 |
| 极简主义 | ✂️ | min_ac_code_chars | ≤ 50 | 黄金 | 是 |
| 洋洋洒洒 | 📜 | max_code_lines | ≥ 300 | 青铜 | 是 |
| 奖杯收藏家 | 💎 | achievement_unlocked_count | ≥ 12 | 白金 | 否 |

- [ ] **Step 2: 低峰期执行补发**

```bash
cd OnlineJudge
python manage.py recompute_achievements --silent
```

Expected: 输出 `完成：N 个用户，新解锁 M 条`。**必须带 `--silent`** —— 否则学生下次登录会被几十个奖杯连续糊脸。

- [ ] **Step 3: 抽查补发结果**

```bash
python manage.py shell -c "
from achievement.models import Achievement, UserAchievement
print('unnotified (应为 0):', UserAchievement.objects.filter(notified=False).count())
for a in Achievement.objects.order_by('-unlock_count')[:5]:
    print(f'{a.name}: {a.unlock_count} 人')
for a in Achievement.objects.filter(unlock_count=0):
    print(f'!! 零解锁: {a.name} ({a.metric} {a.operator} {a.threshold})')
"
```

Expected: `unnotified` 为 0；零解锁的成就逐条核对是不是阈值配错了（隐藏型高门槛成就零解锁是正常的）。

- [ ] **Step 4: 加上线提示**

在 `ojnext/src/oj/user/index.vue` 的成就摘要卡片里，当 `achievementSummary.unlocked > 0` 时显示一次性提示。用 `localStorage` 记住已关闭：

```typescript
const showLaunchTip = ref(
  localStorage.getItem("achievement_launch_tip_dismissed") !== "1",
)

function dismissLaunchTip() {
  showLaunchTip.value = false
  localStorage.setItem("achievement_launch_tip_dismissed", "1")
}
```

```vue
        <n-alert
          v-if="showLaunchTip && achievementSummary.unlocked > 0"
          type="success"
          closable
          style="margin-bottom: 10px"
          @close="dismissLaunchTip"
        >
          成就系统上线了，你已解锁 {{ achievementSummary.unlocked }} 个成就
        </n-alert>
```

- [ ] **Step 5: 提交前端改动**

```bash
cd ojnext
npm fmt && npm run build
git add src/oj/user/index.vue
git commit -m "feat(achievement): 添加成就系统上线提示"
```

- [ ] **Step 6: 全链路回归**

在浏览器里完整走一遍：

1. 用学生账号提交一道**未做过**的题并 AC → Expected: 判题结果出来后奖杯弹窗出现
2. 打开 `/achievement` → Expected: 该成就已点亮，显示获得日期与获得率
3. 打开 `/achievement?name=<另一个学生>` → Expected: 看到他人成就，隐藏且他未解锁的仍显示 `???`
4. 在**比赛中**提交并 AC → Expected: `accepted_count` 不增加（比赛题不计入）

比赛不计入的验证：

```bash
cd OnlineJudge
python manage.py shell -c "
from account.models import User
from achievement.models import UserStat
u = User.objects.get(username='<测试学生用户名>')
print('accepted_count:', UserStat.objects.get(user=u).metrics.get('accepted_count'))
"
```

比赛提交前后跑两次，Expected: 数值不变。

---

## Self-Review

**Spec 覆盖检查：**

| Spec 章节 | 对应任务 |
|---|---|
| 数据模型（三张表） | Task 1 |
| 指标注册表 + 16 个指标 | Task 2 |
| 极小值型初始值陷阱 | Task 2 Step 7 验证、Task 1 模型注释、Task 3 `evaluate` |
| 比赛提交不计入 | Task 2 `_practice_submissions` / `build_ctx`、Task 13 Step 6 验证 |
| 元指标与两轮判定 | Task 2 Step 5、Task 3 `run_for_submission` |
| 判定流程 + 投递点 | Task 3 |
| 解锁通知推拉结合 | Task 3（notify）、Task 4（pending 端点）、Task 10（前端） |
| `useSubmissionMonitor` 分流 | Task 8 Step 3、Task 10 Step 4 |
| 前端奖杯馆三种视觉状态 | Task 9 |
| 获得率分母缓存 | Task 4 Step 1 `get_active_user_count` |
| 炫耀入口 | Task 11 |
| 管理后台 + unlock_count 仪表盘 | Task 5、Task 12 |
| 历史补发 + backfilled + --silent | Task 6、Task 13 |
| 阈值下调补发 + JSONB cast 陷阱 | Task 5 Step 1、Step 5 |
| 题单奖章分层共存 + 修 N+1 | Task 7、Task 9（奖章 tab） |

**已知偏离 spec 之处（有意，已在任务内说明）：**

1. **`POST /api/achievements/pending/read` 改为 `POST /api/achievements/pending`** —— 复用同一个视图类的 `post` 方法，少一个路由。Task 4 Step 3 已注明，前端 Task 8 按实际路径实现。
2. **排行榜不显示徽章内容，只放一个跳转按钮** —— spec 原写「每行挂最稀有的 1–2 枚徽章」，但那需要为每行拉一次摘要（N 次请求）或改后端排行榜序列化器。Task 11 Step 2 已说明改为零额外请求的入口按钮。若后续确实需要徽章内容，应单独开一个任务改后端排行榜接口批量返回。

**Task 2 的已知取舍：** `recompute` 会丢弃 `_active_dates`、`_languages`、`_ac_per_day` 等下划线前缀的增量辅助 key，重算后这几个指标的辅助状态从零重建。因为相关指标（`active_days`、`languages_used`、`max_ac_in_one_day`、`max_ac_streak_days`）都是 max/count 语义且 `recompute` 直接给出终值，成就判定不会回退。Task 6 Step 1 的注释已记录这一点。
