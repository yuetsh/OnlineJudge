from utils.api import serializers

from .models import AIAnalysis


class AIAnalysisListSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username")
    analysis_excerpt = serializers.SerializerMethodField()

    class Meta:
        model = AIAnalysis
        fields = ["id", "create_time", "username", "analysis_excerpt", "is_pinned"]

    def get_analysis_excerpt(self, obj):
        if not obj.analysis:
            return ""
        text = " ".join(obj.analysis.split())
        return text[:120] if len(text) <= 120 else text[:120] + "…"


class AIAnalysisDetailSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username")
    class_name = serializers.CharField(source="user.class_name")

    class Meta:
        model = AIAnalysis
        fields = ["id", "create_time", "username", "class_name", "analysis"]
