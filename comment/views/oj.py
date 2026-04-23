from django.core.cache import cache
from django.db.models import Avg, Count
from django.db.models.functions import Round

from account.decorators import login_required
from comment.models import Comment
from comment.serializers import CommentSerializer, CreateCommentSerializer
from problem.models import Problem
from submission.models import JudgeStatus, Submission
from utils.api import APIView
from utils.api.api import validate_serializer
from utils.constants import CacheKey


class CommentAPI(APIView):
    @validate_serializer(CreateCommentSerializer)
    @login_required
    def post(self, request):
        data = request.data
        try:
            problem = Problem.objects.get(id=data["problem_id"], visible=True)
        except Problem.DoesNotExist:
            self.error("problem is not exists")

        try:
            submission = (
                Submission.objects.select_related("problem")
                .filter(
                    user_id=request.user.id,
                    problem_id=data["problem_id"],
                    result=JudgeStatus.ACCEPTED,
                )
                .first()
            )
        except Submission.DoesNotExist:
            self.error("submission is not exists or not accepted")

        language = submission.language
        if language == "Python3":
            language = "Python"

        Comment.objects.create(
            user=request.user,
            problem=problem,
            submission=submission,
            language=language,
            description_rating=data["description_rating"],
            difficulty_rating=data["difficulty_rating"],
            comprehensive_rating=data["comprehensive_rating"],
            content=data["content"],
        )
        cache.delete(f"{CacheKey.comment_stats}:{problem.id}")
        return self.success()

    @login_required
    def get(self, request):
        problem_id = request.GET.get("problem_id")
        comment = (
            Comment.objects.select_related("problem")
            .filter(user=request.user, problem_id=problem_id)
            .first()
        )
        if comment:
            return self.success(CommentSerializer(comment).data)
        else:
            return self.success()


class CommentStatisticsAPI(APIView):
    def get(self, request):
        problem_id = request.GET.get("problem_id")
        cache_key = f"{CacheKey.comment_stats}:{problem_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return self.success(cached)

        agg = Comment.objects.filter(problem_id=problem_id).aggregate(
            count=Count("id"),
            description=Round(Avg("description_rating"), 2),
            difficulty=Round(Avg("difficulty_rating"), 2),
            comprehensive=Round(Avg("comprehensive_rating"), 2),
        )
        if not agg["count"]:
            return self.success()

        data = {"count": agg["count"], "rating": {
            "description": agg["description"],
            "difficulty": agg["difficulty"],
            "comprehensive": agg["comprehensive"],
        }}
        cache.set(cache_key, data, 3600)
        return self.success(data)
