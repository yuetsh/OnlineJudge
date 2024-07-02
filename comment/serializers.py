from comment.models import Comment
from utils.api import UsernameSerializer, serializers


class CreateCommentSerializer(serializers.Serializer):
    problem_id = serializers.IntegerField()
    description_rating = serializers.IntegerField()
    difficulty_rating = serializers.IntegerField()
    comprehensive_rating = serializers.IntegerField()
    content = serializers.CharField(required=False, allow_blank=True)


class CommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = [
            "comprehensive_rating",
            "description_rating",
            "difficulty_rating",
            "content",
            "create_time",
        ]


class CommentListSerializer(serializers.ModelSerializer):
    problem = serializers.SlugRelatedField(read_only=True, slug_field="_id")
    user = UsernameSerializer()

    class Meta:
        model = Comment
        fields = "__all__"