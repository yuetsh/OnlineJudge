from rest_framework import serializers
from .models import FlowchartSubmission


class CreateFlowchartSubmissionSerializer(serializers.Serializer):
    problem_id = serializers.IntegerField()
    mermaid_code = serializers.CharField()
    flowchart_data = serializers.JSONField(required=False, default=dict)

    def validate_mermaid_code(self, value):
        if not value.strip():
            raise serializers.ValidationError("Mermaid代码不能为空")
        return value


class FlowchartSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FlowchartSubmission
        fields = [
            "id",
            "user",
            "problem",
            "mermaid_code",
            "flowchart_data",
            "status",
            "create_time",
            "ai_score",
            "ai_grade",
            "ai_feedback",
            "ai_suggestions",
            "ai_criteria_details",
            "ai_provider",
            "ai_model",
            "processing_time",
            "evaluation_time",
        ]
        read_only_fields = ["id", "create_time", "evaluation_time"]


class FlowchartSubmissionListSerializer(serializers.ModelSerializer):
    """用于列表显示的简化序列化器"""

    username = serializers.CharField(source="user.username")
    problem_title = serializers.CharField(source="problem.title")

    class Meta:
        model = FlowchartSubmission
        fields = [
            "id",
            "username",
            "problem_title",
            "status",
            "create_time",
            "ai_score",
            "ai_grade",
            "ai_provider",
            "ai_model",
            "processing_time",
            "evaluation_time",
        ]
