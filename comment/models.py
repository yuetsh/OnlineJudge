from django.db import models

from account.models import User
from problem.models import Problem
from submission.models import Submission


class Languages(models.TextChoices):
    Python = "Python", "Python"
    C = "C", "C"
    Cpp = "C++", "C++"
    Java = "Java", "Java"


class Comment(models.Model):
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE)
    language = models.CharField(
        max_length=10,
        default=Languages.Python,
        choices=Languages.choices,
        verbose_name="解决这道题使用的语言",
    )
    description_rating = models.PositiveSmallIntegerField(
        default=5,
        verbose_name="题目描述的分数",
    )
    difficulty_rating = models.PositiveSmallIntegerField(
        default=5,
        verbose_name="题目难度的分数",
    )
    comprehensive_rating = models.PositiveSmallIntegerField(
        default=5,
        verbose_name="综合的分数",
    )
    content = models.TextField(null=True, blank=True)
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "comment"
        ordering = ("-create_time",)


