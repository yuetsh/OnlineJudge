from django.db import models
from account.models import User
from submission.models import Submission
from utils.models import RichTextField


class Message(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sender")
    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="recipient"
    )
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE)
    message = RichTextField()
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "message"
        ordering = ("-create_time",)
