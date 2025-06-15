from rest_framework import serializers
from .models import Tutorial
from account.serializers import UserSerializer


class TutorialListSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = Tutorial
        fields = [
            "id",
            "title",
            "created_by",
            "created_at",
            "updated_at",
            "is_public",
            "order",
            "type",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]


class TutorialSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = Tutorial
        fields = [
            "id",
            "title",
            "content",
            "created_by",
            "created_at",
            "updated_at",
            "is_public",
            "order",
            "type",
            "code",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]


class CreateTutorialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tutorial
        fields = ["title", "content", "is_public", "order", "type", "code"]


class EditTutorialSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField()

    class Meta:
        model = Tutorial
        fields = ["id", "title", "content", "is_public", "order", "type", "code"]
