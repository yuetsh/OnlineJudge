from rest_framework import serializers

from .models import AIAnalysis


class AIAnalysisListSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username")
    class_name = serializers.CharField(source="user.class_name")

    class Meta:
        model = AIAnalysis
        fields = ["id", "create_time", "username", "class_name"]


class AIAnalysisDetailSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username")
    class_name = serializers.CharField(source="user.class_name")

    class Meta:
        model = AIAnalysis
        fields = ["id", "create_time", "username", "class_name", "analysis"]
