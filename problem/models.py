from django.db import models

from account.models import User
from contest.models import Contest
from utils.constants import Choices
from utils.models import RichTextField


class ProblemTag(models.Model):
    name = models.TextField()

    class Meta:
        db_table = "problem_tag"


class ProblemRuleType(Choices):
    ACM = "ACM"
    OI = "OI"


class ProblemDifficulty(object):
    High = "High"
    Mid = "Mid"
    Low = "Low"


class ProblemIOMode(Choices):
    standard = "Standard IO"
    file = "File IO"


def _default_io_mode():
    return {
        "io_mode": ProblemIOMode.standard,
        "input": "input.txt",
        "output": "output.txt",
    }


class Problem(models.Model):
    # display ID
    _id = models.TextField(db_index=True)
    contest = models.ForeignKey(Contest, null=True, on_delete=models.CASCADE)
    # for contest problem
    is_public = models.BooleanField(default=False)
    title = models.TextField()
    # HTML
    description = RichTextField()
    input_description = RichTextField()
    output_description = RichTextField()
    # [{input: "test", output: "123"}, {input: "test123", output: "456"}]
    samples = models.JSONField()
    test_case_id = models.TextField()
    # [{"input_name": "1.in", "output_name": "1.out", "score": 0}]
    test_case_score = models.JSONField()
    hint = RichTextField(null=True)
    languages = models.JSONField()
    template = models.JSONField()
    create_time = models.DateTimeField(auto_now_add=True)
    # we can not use auto_now here
    last_update_time = models.DateTimeField(auto_now=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    # ms
    time_limit = models.IntegerField()
    # MB
    memory_limit = models.IntegerField()
    # io mode
    io_mode = models.JSONField(default=_default_io_mode)
    rule_type = models.TextField()
    visible = models.BooleanField(default=True)
    difficulty = models.TextField()
    tags = models.ManyToManyField(ProblemTag)
    source = models.TextField(null=True)
    prompt = models.TextField(null=True)
    # [{language: "python", code: "..."}]
    answers = models.JSONField(null=True)
    # for OI mode
    total_score = models.IntegerField(default=0)
    submission_number = models.BigIntegerField(default=0)
    accepted_number = models.BigIntegerField(default=0)
    # {JudgeStatus.ACCEPTED: 3, JudgeStatus.WRONG_ANSWER: 11}, the number means count
    statistic_info = models.JSONField(default=dict)
    share_submission = models.BooleanField(default=False)
    
    # 流程图相关字段
    allow_flowchart = models.BooleanField(default=False)  # 是否允许/需要提交流程图
    mermaid_code = models.TextField(null=True, blank=True)  # 流程图答案(Mermaid代码)
    flowchart_data = models.JSONField(default=dict)  # 流程图答案元数据(JSON格式)
    flowchart_hint = models.TextField(null=True, blank=True)  # 流程图提示信息
    show_flowchart = models.BooleanField(default=False)  # 是否显示流程图答案数据，如果True，这样就不需要提交流程图了，说明就是给学生看的

    class Meta:
        db_table = "problem"
        unique_together = (("_id", "contest"),)
        ordering = ("create_time",)
        indexes = [
            models.Index(fields=["contest", "visible"], name="problem_contest_visible_idx"),
            models.Index(fields=["visible"], name="problem_visible_idx"),
        ]

    def add_submission_number(self):
        self.submission_number = models.F("submission_number") + 1
        self.save(update_fields=["submission_number"])

    def add_ac_number(self):
        self.accepted_number = models.F("accepted_number") + 1
        self.save(update_fields=["accepted_number"])


# class ProblemSet(models):
#     title = models.CharField(max_length=20)
#     subtitle = models.CharField(max_length=50)
#     problems = models.ManyToManyField(Problem)
#     badge = models.FilePathField(path=settings.UPLOAD_DIR)
#     overviews = models.JSONField()
#     create_time = models.DateTimeField(auto_now_add=True)
#     update_time = models.DateTimeField(auto_now=True)
