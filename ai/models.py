from django.db import models

from account.models import User


class AIAnalysis(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    provider = models.TextField(default="deepseek")
    model = models.TextField(default="deepseek-v4-flash")
    data = models.JSONField()
    system_prompt = models.TextField()
    user_prompt = models.TextField()
    analysis = models.TextField()
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_analysis"
        ordering = ["-create_time"]
