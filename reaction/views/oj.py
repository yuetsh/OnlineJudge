from django.db.models import Count, Q

from account.decorators import login_required
from problem.models import Problem
from reaction.models import Reaction, ReactionType
from reaction.serializers import SetReactionSerializer
from submission.models import JudgeStatus, Submission
from utils.api import AsyncAPIView
from utils.api.api import validate_serializer

ACCEPTED_RESULTS = [JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED]


class ReactionAPI(AsyncAPIView):
    async def get_counts(self, problem_id):
        """直接从数据库返回该题七个表情的计数。"""
        return await Reaction.objects.filter(problem_id=problem_id).aaggregate(**{t.value: Count("id", filter=Q(type=t.value)) for t in ReactionType})

    @login_required
    async def get(self, request):
        problem_id = request.GET.get("problem_id")
        if not problem_id:
            return self.error("problem_id is required")
        mine = await Reaction.objects.filter(user=request.user, problem_id=problem_id).values_list("type", flat=True).afirst()
        if mine is None:
            return self.success({"mine": None, "counts": None})
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

        reaction_type = data["type"]
        user = request.user

        # 数据库唯一约束保证一人一题只有一条；重复请求返回实际保存的评价，
        # 让网络重试和多标签页并发都收敛到同一状态。
        reaction, _ = await Reaction.objects.aget_or_create(
            user=user,
            problem=problem,
            defaults={"type": reaction_type},
        )

        return self.success({"mine": reaction.type, "counts": await self.get_counts(problem.id)})
