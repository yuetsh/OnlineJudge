from comment.models import Comment
from utils.api import serializers


class CreateCommentSerializer(serializers.Serializer):
    problem_id = serializers.IntegerField()
    description_rating = serializers.IntegerField()
    difficulty_rating = serializers.IntegerField()
    comprehensive_rating = serializers.IntegerField()
    content = serializers.CharField()


class CommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = "__all__"
