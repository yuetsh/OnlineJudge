from django.db import models
from django.contrib.auth import get_user_model
from utils.shortcuts import rand_str
from problem.models import Problem

User = get_user_model()

class FlowchartSubmissionStatus:
    PENDING = 0      # 等待AI评分
    PROCESSING = 1   # AI评分中
    COMPLETED = 2    # 评分完成
    FAILED = 3       # 评分失败

class FlowchartSubmission(models.Model):
    """流程图提交模型"""
    id = models.TextField(default=rand_str, primary_key=True, db_index=True)
    
    # 基础信息
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='flowchart_submissions')
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE, related_name='flowchart_submissions')
    
    # 提交内容
    mermaid_code = models.TextField()  # Mermaid代码
    flowchart_data = models.JSONField(default=dict)  # 流程图元数据
    
    # 状态信息
    status = models.IntegerField(default=FlowchartSubmissionStatus.PENDING)
    create_time = models.DateTimeField(auto_now_add=True)
    
    # AI评分结果
    ai_score = models.FloatField(null=True, blank=True)  # AI评分 (0-100)
    ai_grade = models.CharField(max_length=10, null=True, blank=True)  # 等级 (S/A/B/C)
    ai_feedback = models.TextField(null=True, blank=True)  # AI反馈
    ai_suggestions = models.TextField(null=True, blank=True)  # AI建议
    ai_criteria_details = models.JSONField(default=dict)  # 详细评分标准
    
    # 处理信息
    ai_provider = models.CharField(max_length=50, default='deepseek')
    ai_model = models.CharField(max_length=50, default='deepseek-chat')
    processing_time = models.FloatField(null=True, blank=True)  # AI处理耗时(秒)
    evaluation_time = models.DateTimeField(null=True, blank=True) # 评分完成时间
    
    
    class Meta:
        db_table = 'flowchart_submission'
        ordering = ['-create_time']
        indexes = [
            models.Index(fields=['user', 'create_time'], name='flowchart_user_time_idx'),
            models.Index(fields=['problem', 'create_time'], name='flowchart_problem_time_idx'),
            models.Index(fields=['status'], name='flowchart_status_idx'),
        ]
    
    def __str__(self):
        return f"FlowchartSubmission {self.id}"
    
    def check_user_permission(self, user, check_share=True):
        """检查用户权限"""
        if (
            self.user_id == user.id
            or not user.is_regular_user()
            or self.problem.created_by_id == user.id
        ):
            return True
        
        return False
