from asgiref.sync import sync_to_async
from django.db import transaction
from django.db.models import Count, Q

from account.decorators import login_required
from problem.models import Problem
from reaction.models import Reaction, ReactionType
from reaction.serializers import SetReactionSerializer
from submission.models import JudgeStatus, Submission
from utils.api import AsyncAPIView
from utils.api.api import validate_serializer
from utils.async_helpers import async_cache_delete, async_cache_get, async_cache_set
from utils.constants import CacheKey

ACCEPTED_RESULTS = [JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED]


class ReactionAPI(AsyncAPIView):
    async def get_counts(self, problem_id):
        """返回该题七个表情的计数，带 Redis 缓存。"""
        cache_key = f"{CacheKey.reaction_stats}:{problem_id}"
        cached = await async_cache_get(cache_key)
        if cached is not None:
            return cached
        counts = await Reaction.objects.filter(problem_id=problem_id).aaggregate(**{t.value: Count("id", filter=Q(type=t.value)) for t in ReactionType})
        await async_cache_set(cache_key, counts, 3600)
        return counts

    @login_required
    async def get(self, request):
        problem_id = request.GET.get("problem_id")
        if not problem_id:
            return self.error("problem_id is required")
        mine = [r.type async for r in Reaction.objects.filter(user=request.user, problem_id=problem_id)]
        if not mine:
            return self.success({"mine": [], "counts": None})
        return self.success({"mine": mine, "counts": await self.get_counts(problem_id)})

    @login_required
    @validate_serializer(SetReactionSerializer)
    async def post(self, request):
        data = request.data
        try:
            problem = await Problem.objects.aget(id=data["problem_id"], visible=True)
        except Problem.DoesNotExist:
            return self.error("problem is not exists")

        solved = await Submission.objects.filter(
            user_id=request.user.id,
            problem_id=problem.id,
            result__in=ACCEPTED_RESULTS,
        ).aexists()
        if not solved:
            return self.error("submission is not exists or not accepted")

        types = data["types"]
        user = request.user

        def overwrite():
            with transaction.atomic():
                Reaction.objects.filter(user=user, problem=problem).delete()
                Reaction.objects.bulk_create([Reaction(user=user, problem=problem, type=t) for t in types])

        await sync_to_async(overwrite)()
        await async_cache_delete(f"{CacheKey.reaction_stats}:{problem.id}")

        if not types:
            return self.success({"mine": [], "counts": None})
        return self.success({"mine": types, "counts": await self.get_counts(problem.id)})
