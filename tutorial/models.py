from django.db import models
from account.models import User

class Tutorial(models.Model):
    TYPE_CHOICES = [
        ('python', 'Python'),
        ('c', 'C'),
    ]
    
    title = models.CharField(max_length=128)
    content = models.TextField()
    code = models.TextField(null=True, blank=True)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='python')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_public = models.BooleanField(default=False)
    order = models.IntegerField(default=0)

    class Meta:
        db_table = "tutorial"
        ordering = ['order', '-created_at']

    def __str__(self):
        return self.title 