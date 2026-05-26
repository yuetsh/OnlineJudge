from django.db import models

from contest.models import Contest
from problem.models import Problem
from utils.constants import ContestStatus
from utils.models import JSONField
from utils.shortcuts import rand_str


class JudgeStatus(models.IntegerChoices):
    COMPILE_ERROR = -2, "Compile Error"
    WRONG_ANSWER = -1, "Wrong Answer"
    ACCEPTED = 0, "Accepted"
    CPU_TIME_LIMIT_EXCEEDED = 1, "CPU Time Limit Exceeded"
    REAL_TIME_LIMIT_EXCEEDED = 2, "Real Time Limit Exceeded"
    MEMORY_LIMIT_EXCEEDED = 3, "Memory Limit Exceeded"
    RUNTIME_ERROR = 4, "Runtime Error"
    SYSTEM_ERROR = 5, "System Error"
    PENDING = 6, "Pending"
    JUDGING = 7, "Judging"
    PARTIALLY_ACCEPTED = 8, "Partially Accepted"
    AST_CHECK_FAILED = 10, "AST Check Failed"


def is_accepted(result):
    return result in (JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED)


class Submission(models.Model):
    id = models.TextField(default=rand_str, primary_key=True, db_index=True)
    contest = models.ForeignKey(Contest, null=True, on_delete=models.CASCADE)
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE)
    create_time = models.DateTimeField(auto_now_add=True)
    user_id = models.IntegerField(db_index=True)
    username = models.TextField()
    code = models.TextField()
    result = models.IntegerField(choices=JudgeStatus.choices, db_index=True, default=JudgeStatus.PENDING, db_default=JudgeStatus.PENDING)
    # 从JudgeServer返回的判题详情
    info = JSONField(default=dict, db_default=models.Value({}, output_field=models.JSONField()))
    language = models.TextField()
    shared = models.BooleanField(default=False, db_default=False)
    # 存储该提交所用时间和内存值，方便提交列表显示
    # {time_cost: "", memory_cost: "", err_info: "", score: 0}
    statistic_info = JSONField(default=dict, db_default=models.Value({}, output_field=models.JSONField()))
    ip = models.TextField(null=True)

    def check_user_permission(self, user, check_share=True):
        if self.user_id == user.id or not user.is_regular_user() or self.problem.created_by_id == user.id:
            return True

        if check_share:
            if self.contest and self.contest.status != ContestStatus.CONTEST_ENDED:
                return False
            if self.problem.share_submission or self.shared:
                return True
        return False

    class Meta:
        db_table = "submission"
        ordering = ("-create_time",)
        indexes = [
            models.Index(fields=["user_id", "create_time"], name="user_create_time_idx"),
            models.Index(fields=["contest_id", "-create_time"], name="contest_create_time_idx"),
            models.Index(fields=["problem_id", "user_id"], name="problem_user_idx"),
        ]

    def __str__(self):
        return self.id
