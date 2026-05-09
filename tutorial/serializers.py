from rest_framework import serializers

from account.serializers import UserSerializer

from .models import Exercise, ExerciseType, Tutorial


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


class ExerciseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exercise
        fields = ["id", "type", "data", "order"]


class CreateExerciseSerializer(serializers.Serializer):
    tutorial_id = serializers.IntegerField()
    type = serializers.ChoiceField(choices=ExerciseType.choices)
    data = serializers.JSONField()
    order = serializers.IntegerField(default=0)


class EditExerciseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    type = serializers.ChoiceField(choices=ExerciseType.choices)
    data = serializers.JSONField()
    order = serializers.IntegerField(default=0)
