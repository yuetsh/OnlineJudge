from django.db import models

from account.models import User
from problem.models import Problem


class ReactionType(models.TextChoices):
    TOO_EASY = "too_easy", "太简单"
    TOO_HARD = "too_hard", "太难了"
    CONFUSING = "confusing", "没看懂"
    BUGGY = "buggy", "题目有错"
    LEARNED = "learned", "学到了"
    INTERESTING = "interesting", "有意思"
    WANT_EXPLAIN = "want_explain", "想听讲解"


class Reaction(models.Model):
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    type = models.CharField(max_length=20, choices=ReactionType.choices, verbose_name="表情类型")
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reaction"
        unique_together = ("problem", "user", "type")
        indexes = [
            models.Index(fields=["problem", "type"], name="reaction_problem_type_idx"),
        ]
