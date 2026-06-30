from django.db import models

from account.models import User


class TutorialType(models.TextChoices):
    PYTHON = "python", "Python"
    C = "c", "C"


class ExerciseType(models.TextChoices):
    MCQ = "mcq", "选择题"
    SORT = "sort", "代码排序"
    FILL = "fill", "代码填空"
    MATCH = "match", "连线匹配"
    PREDICT = "predict", "输出预测"
    DEBUG = "debug", "代码找错"
    GROUP = "group", "归类分组"


class Tutorial(models.Model):
    title = models.CharField(max_length=128)
    content = models.TextField()
    code = models.TextField(null=True, blank=True)
    type = models.CharField(max_length=10, choices=TutorialType.choices, default=TutorialType.PYTHON)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_public = models.BooleanField(default=False)
    order = models.IntegerField(default=0)

    class Meta:
        db_table = "tutorial"
        ordering = ["order", "-created_at"]

    def __str__(self):
        return self.title


class Exercise(models.Model):
    tutorial = models.ForeignKey(Tutorial, on_delete=models.CASCADE, related_name="exercises")
    type = models.CharField(max_length=16, choices=ExerciseType.choices)
    data = models.JSONField()
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "exercise"
        ordering = ["order", "created_at"]

    def __str__(self):
        return f"{self.get_type_display()} (Order {self.order})"
