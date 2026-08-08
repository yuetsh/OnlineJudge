from rest_framework import serializers

from .models import FlowchartSubmission


class CreateFlowchartSubmissionSerializer(serializers.Serializer):
    problem_id = serializers.IntegerField()
    mermaid_code = serializers.CharField(max_length=50000)
    flowchart_data = serializers.JSONField(required=False, default=dict)

    def validate_mermaid_code(self, value):
        if not value.strip():
            raise serializers.ValidationError("Mermaid代码不能为空")
        lines = [line for line in value.split("\n") if line.strip()]
        if len(lines) > 200:
            raise serializers.ValidationError("流程图过于复杂，请简化后提交")
        return value

    def validate_flowchart_data(self, value):
        import json

        if len(json.dumps(value)) > 500 * 1024:
            raise serializers.ValidationError("流程图数据过大")
        return value


class FlowchartSubmissionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = FlowchartSubmission
        fields = [
            "id",
            "username",
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
    problem = serializers.CharField(source="problem._id")
    problem_title = serializers.CharField(source="problem.title")

    class Meta:
        model = FlowchartSubmission
        fields = [
            "id",
            "username",
            "problem_title",
            "problem",
            "status",
            "create_time",
            "ai_score",
            "ai_grade",
            "ai_provider",
            "ai_model",
            "processing_time",
            "evaluation_time",
        ]

