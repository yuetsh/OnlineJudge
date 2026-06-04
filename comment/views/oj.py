from django.db.models import Avg, Count
from django.db.models.functions import Round

from account.decorators import login_required
from comment.models import Comment
from comment.serializers import CommentSerializer, CreateCommentSerializer
from problem.models import Problem
from submission.models import JudgeStatus, Submission
from utils.api import AsyncAPIView
from utils.api.api import validate_serializer
from utils.async_helpers import async_cache_delete, async_cache_get, async_cache_set
from utils.constants import CacheKey


class CommentAPI(AsyncAPIView):
    @login_required
    @validate_serializer(CreateCommentSerializer)
    async def post(self, request):
        data = request.data
        try:
            problem = await Problem.objects.aget(id=data["problem_id"], visible=True)
        except Problem.DoesNotExist:
            return self.error("problem is not exists")

        submission = await (
            Submission.objects.select_related("problem")
            .filter(
                user_id=request.user.id,
                problem_id=data["problem_id"],
                result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED],
            )
            .afirst()
        )
        if not submission:
            return self.error("submission is not exists or not accepted")

        language = submission.language
        if language == "Python3":
            language = "Python"

        await Comment.objects.acreate(
            user=request.user,
            problem=problem,
            submission=submission,
            language=language,
            description_rating=data["description_rating"],
            difficulty_rating=data["difficulty_rating"],
            comprehensive_rating=data["comprehensive_rating"],
            content=data["content"],
        )
        await async_cache_delete(f"{CacheKey.comment_stats}:{problem.id}")
        return self.success()

    @login_required
    async def get(self, request):
        problem_id = request.GET.get("problem_id")
        comment = await (
            Comment.objects.select_related("problem")
            .filter(user=request.user, problem_id=problem_id)
            .afirst()
        )
        if comment:
            return self.success(await self.async_serialize_data(CommentSerializer, comment))
        else:
            return self.success()


class CommentStatisticsAPI(AsyncAPIView):
    async def get(self, request):
        problem_id = request.GET.get("problem_id")
        cache_key = f"{CacheKey.comment_stats}:{problem_id}"
        cached = await async_cache_get(cache_key)
        if cached is not None:
            return self.success(cached)

        agg = await Comment.objects.filter(problem_id=problem_id).aaggregate(
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
        await async_cache_set(cache_key, data, 3600)
        return self.success(data)
