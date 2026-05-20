from django.db import models
from django.utils.timezone import now

from account.models import User
from problem.models import Problem
from utils.models import JSONField, RichTextField


class ProblemSetStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class ProblemSetDifficulty(models.TextChoices):
    EASY = "Easy", "Easy"
    MEDIUM = "Medium", "Medium"
    HARD = "Hard", "Hard"


class BadgeConditionType(models.TextChoices):
    ALL_PROBLEMS = "all_problems", "All Problems"
    PROBLEM_COUNT = "problem_count", "Problem Count"
    SCORE = "score", "Score"


class ProblemSet(models.Model):
    """题单模型"""

    title = models.TextField(verbose_name="题单标题")
    description = RichTextField(verbose_name="题单描述")
    # 创建者
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="创建者")
    # 创建时间
    create_time = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    # 更新时间
    last_update_time = models.DateTimeField(auto_now=True, verbose_name="更新时间")
    # 是否可见
    visible = models.BooleanField(default=True, verbose_name="是否可见")
    # 题单难度等级
    difficulty = models.TextField(
        default=ProblemSetDifficulty.EASY,
        choices=ProblemSetDifficulty.choices,
        verbose_name="难度等级",
    )
    # 题单状态
    status = models.TextField(default=ProblemSetStatus.DRAFT, choices=ProblemSetStatus.choices, verbose_name="状态")
    # 截止时间（到期后自动解除防作弊隐藏）
    end_time = models.DateTimeField(null=True, blank=True, verbose_name="截止时间")

    class Meta:
        db_table = "problemset"
        ordering = ("-create_time",)
        verbose_name = "题单"
        verbose_name_plural = "题单"

    def __str__(self):
        return self.title


class ProblemSetProblem(models.Model):
    """题单题目关联模型"""

    problemset = models.ForeignKey(ProblemSet, on_delete=models.CASCADE, verbose_name="题单")
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE, verbose_name="题目")
    # 在题单中的顺序
    order = models.IntegerField(default=0, verbose_name="顺序")
    # 是否为必做题
    is_required = models.BooleanField(default=True, verbose_name="是否必做")
    # 题目在题单中的分值
    score = models.IntegerField(default=0, verbose_name="分值")
    # 题目提示信息
    hint = models.TextField(null=True, blank=True, verbose_name="提示")

    class Meta:
        db_table = "problemset_problem"
        constraints = [
            models.UniqueConstraint(fields=["problemset", "problem"], name="unique_problemset_problem"),
        ]
        ordering = ("order",)
        verbose_name = "题单题目"
        verbose_name_plural = "题单题目"

    def __str__(self):
        return f"{self.problemset.title} - {self.problem.title}"


class ProblemSetBadge(models.Model):
    """题单奖章模型"""

    problemset = models.ForeignKey(ProblemSet, on_delete=models.CASCADE, verbose_name="题单")
    name = models.TextField(verbose_name="奖章名称")
    description = models.TextField(verbose_name="奖章描述")
    # 奖章图标路径
    icon = models.TextField(verbose_name="奖章图标")
    # 获得条件：完成所有题目、完成指定数量题目、达到指定分数等
    condition_type = models.TextField(choices=BadgeConditionType.choices, verbose_name="获得条件类型")
    condition_value = models.IntegerField(default=0, verbose_name="条件值")

    class Meta:
        db_table = "problemset_badge"
        verbose_name = "题单奖章"
        verbose_name_plural = "题单奖章"

    def __str__(self):
        return f"{self.problemset.title} - {self.name}"

    def recalculate_user_badges(self):
        """重新计算所有用户的徽章资格"""
        from django.db import transaction

        user_progresses = ProblemSetProgress.objects.filter(problemset=self.problemset)
        eligible_user_ids = {p.user_id for p in user_progresses if self._is_eligible(p)}
        with transaction.atomic():
            # 移除不再满足条件的用户徽章
            UserBadge.objects.filter(badge=self).exclude(user_id__in=eligible_user_ids).delete()
            # 为新满足条件的用户授予徽章（保留已有记录的 earned_time）
            existing_user_ids = set(UserBadge.objects.filter(badge=self).values_list("user_id", flat=True))
            new_badges = [UserBadge(user_id=uid, badge=self) for uid in eligible_user_ids - existing_user_ids]
            if new_badges:
                UserBadge.objects.bulk_create(new_badges)

    def _is_eligible(self, progress):
        """判断用户进度是否满足该徽章条件（纯逻辑，不查数据库）"""
        if self.condition_type == BadgeConditionType.ALL_PROBLEMS:
            return progress.total_problems_count > 0 and progress.completed_problems_count == progress.total_problems_count
        if self.condition_type == BadgeConditionType.PROBLEM_COUNT:
            return progress.completed_problems_count >= self.condition_value
        if self.condition_type == BadgeConditionType.SCORE:
            return progress.total_score >= self.condition_value
        return False

    def _check_user_badge_eligibility(self, progress):
        """检查并授予单个用户的徽章（供外部单次调用）"""
        if self._is_eligible(progress) and not UserBadge.objects.filter(user=progress.user, badge=self).exists():
            UserBadge.objects.create(user=progress.user, badge=self)
            return True
        return False


class ProblemSetProgress(models.Model):
    """题单进度模型"""

    problemset = models.ForeignKey(ProblemSet, on_delete=models.CASCADE, verbose_name="题单")
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="用户")
    # 加入时间
    join_time = models.DateTimeField(auto_now_add=True, verbose_name="加入时间")
    # 完成时间
    complete_time = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")
    # 是否完成
    is_completed = models.BooleanField(default=False, verbose_name="是否完成")
    # 完成进度百分比
    progress_percentage = models.FloatField(default=0.0, verbose_name="完成进度")
    # 已完成的题目数量
    completed_problems_count = models.IntegerField(default=0, verbose_name="已完成题目数")
    # 总题目数量
    total_problems_count = models.IntegerField(default=0, verbose_name="总题目数")
    # 获得的总分
    total_score = models.IntegerField(default=0, verbose_name="总分")
    # 用户在该题单中的详细进度信息
    # {"problem_id": {"score": 20, "submit_time": "2024-01-01T00:00:00Z"}}
    progress_detail = JSONField(default=dict, verbose_name="详细进度")

    class Meta:
        db_table = "problemset_progress"
        constraints = [
            models.UniqueConstraint(fields=["problemset", "user"], name="unique_problemset_progress_user"),
        ]
        verbose_name = "题单进度"
        verbose_name_plural = "题单进度"

    def __str__(self):
        return f"{self.user.username} - {self.problemset.title}"

    def update_progress(self):
        """更新进度信息"""
        # 获取题单中的所有题目
        problemset_problems = ProblemSetProblem.objects.filter(problemset=self.problemset)
        self.total_problems_count = problemset_problems.count()

        # 获取当前题单中所有题目的ID集合（直接用 problem_id FK 字段，无需额外查询）
        current_problem_ids = {str(psp.problem_id) for psp in problemset_problems}

        # 清理已删除题目的进度记录
        progress_detail_to_remove = []
        for problem_id in self.progress_detail.keys():
            if problem_id not in current_problem_ids:
                progress_detail_to_remove.append(problem_id)

        for problem_id in progress_detail_to_remove:
            del self.progress_detail[problem_id]

        # 计算已完成题目数
        completed_count = 0
        total_score = 0

        for psp in problemset_problems:
            problem_id = str(psp.problem_id)
            if problem_id in self.progress_detail:
                problem_progress = self.progress_detail[problem_id]
                completed_count += 1
                total_score += psp.score
                problem_progress["score"] = psp.score

        self.completed_problems_count = completed_count
        self.total_score = total_score

        # 计算完成百分比
        if self.total_problems_count > 0:
            self.progress_percentage = (completed_count / self.total_problems_count) * 100
        else:
            self.progress_percentage = 0

        # 检查是否完成
        self.is_completed = completed_count == self.total_problems_count
        if self.is_completed and not self.complete_time:
            self.complete_time = now()

        self.save()

    @classmethod
    def sync_all_progress_for_problemset(cls, problemset):
        """同步指定题单的所有用户进度"""
        progresses = cls.objects.filter(problemset=problemset)
        for progress in progresses:
            progress.update_progress()
        return progresses.count()


class ProblemSetSubmission(models.Model):
    """题单提交记录模型"""

    problemset = models.ForeignKey(ProblemSet, on_delete=models.CASCADE, verbose_name="题单")
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="用户")
    submission = models.ForeignKey("submission.Submission", on_delete=models.CASCADE, verbose_name="提交记录")
    problem = models.ForeignKey("problem.Problem", on_delete=models.CASCADE, verbose_name="题目")

    class Meta:
        db_table = "problemset_submission"
        ordering = ("-submission__create_time",)
        verbose_name = "题单提交记录"
        verbose_name_plural = "题单提交记录"
        indexes = [
            models.Index(fields=["problemset", "user"]),
            models.Index(fields=["problemset", "problem"]),
            models.Index(fields=["user"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.problemset.title} - {self.problem.title}"

    @property
    def submit_time(self):
        """提交时间"""
        return self.submission.create_time

    @property
    def result(self):
        """提交结果"""
        return self.submission.result

    @property
    def language(self):
        """编程语言"""
        return self.submission.language


class UserBadge(models.Model):
    """用户奖章模型"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="用户")
    badge = models.ForeignKey(ProblemSetBadge, on_delete=models.CASCADE, verbose_name="奖章")
    # 获得时间
    earned_time = models.DateTimeField(auto_now_add=True, verbose_name="获得时间")

    class Meta:
        db_table = "user_badge"
        constraints = [
            models.UniqueConstraint(fields=["user", "badge"], name="unique_user_badge"),
        ]
        verbose_name = "用户奖章"
        verbose_name_plural = "用户奖章"

    def __str__(self):
        return f"{self.user.username} - {self.badge.name}"
