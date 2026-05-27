import random

from asgiref.sync import sync_to_async
from django.db.models import BooleanField, Case, Count, Q, Value, When
from django.db.models.functions import ExtractYear
from django.utils import timezone

from account.decorators import check_contest_permission
from account.models import User
from contest.models import ContestRuleType
from submission.models import JudgeStatus, Submission
from utils.api import APIView, AsyncAPIView
from utils.async_helpers import async_cache_get, async_cache_set
from utils.constants import CacheKey

from ..models import Problem, ProblemTag
from ..serializers import (
    ProblemListSerializer,
    ProblemSafeSerializer,
    ProblemSerializer,
    TagSerializer,
)


class ProblemTagAPI(AsyncAPIView):
    async def get(self, request):
        keyword = request.GET.get("keyword", "")
        cache_key = f"{CacheKey.problem_tags}:{keyword}"
        cached = await async_cache_get(cache_key)
        if cached is not None:
            return self.success(cached)

        qs = ProblemTag.objects
        if keyword:
            qs = ProblemTag.objects.filter(name__icontains=keyword)
        tags = qs.annotate(problem_count=Count("problem")).filter(problem_count__gt=0)
        data = await self.async_serialize_data(TagSerializer, [tag async for tag in tags], many=True)
        await async_cache_set(cache_key, data, 3600)
        return self.success(data)


class PickOneAPI(AsyncAPIView):
    async def get(self, request):
        ids = Problem.objects.filter(contest_id__isnull=True, visible=True).values_list("_id", flat=True)
        count = await ids.acount()
        if count == 0:
            return self.error("No problem to pick")
        idx = random.randint(0, count - 1)
        result = [pid async for pid in ids[idx : idx + 1]]
        return self.success(result[0])


class ProblemAPI(AsyncAPIView):
    @staticmethod
    def _add_problem_status(acm_problems_status, queryset_values):
        results = queryset_values.get("results")
        if results is not None:
            problems = results
        else:
            problems = [queryset_values]
        for problem in problems:
            problem["my_status"] = acm_problems_status.get(str(problem["id"]), {}).get("status")

    async def get(self, request):
        # 问题详情页
        problem_id = request.GET.get("problem_id")
        if problem_id:
            try:
                problem = await Problem.objects.select_related("created_by").prefetch_related("tags").filter(_id__iexact=problem_id, contest_id__isnull=True, visible=True).afirst()
                if problem is None:
                    raise Problem.DoesNotExist
                problem_data = await self.async_serialize_data(ProblemSerializer, problem)
                if request.user.is_authenticated:
                    from account.models import UserProfile

                    profile = await UserProfile.objects.aget(user=request.user)
                    acm_problems_status = profile.acm_problems_status.get("problems", {})
                    self._add_problem_status(acm_problems_status, problem_data)
                    failed_statuses = [
                        JudgeStatus.WRONG_ANSWER,
                        JudgeStatus.CPU_TIME_LIMIT_EXCEEDED,
                        JudgeStatus.REAL_TIME_LIMIT_EXCEEDED,
                        JudgeStatus.MEMORY_LIMIT_EXCEEDED,
                        JudgeStatus.RUNTIME_ERROR,
                        JudgeStatus.COMPILE_ERROR,
                    ]
                    problem_data["my_failed_count"] = await Submission.objects.filter(
                        user_id=request.user.id,
                        problem_id=problem.id,
                        result__in=failed_statuses,
                    ).acount()
                else:
                    problem_data["my_failed_count"] = 0
                return self.success(problem_data)
            except Problem.DoesNotExist:
                return self.error("Problem does not exist")

        limit = request.GET.get("limit")
        if not limit:
            return self.error("Limit is needed")

        problems = Problem.objects.select_related("created_by").prefetch_related("tags").filter(contest_id__isnull=True, visible=True).order_by("-create_time")

        author = request.GET.get("author")
        if author:
            problems = problems.filter(created_by__username=author)

        # 按照标签筛选
        tag_text = request.GET.get("tag")
        if tag_text:
            problems = problems.filter(tags__name=tag_text)

        # 搜索的情况
        keyword = request.GET.get("keyword", "").strip()
        if keyword:
            problems = problems.filter(Q(title__icontains=keyword) | Q(_id__icontains=keyword))

        # 难度筛选
        difficulty = request.GET.get("difficulty")
        if difficulty:
            problems = problems.filter(difficulty=difficulty)

        # 排序
        sort = request.GET.get("sort")
        if sort == "flowchart":
            problems = problems.order_by("-allow_flowchart", "-show_flowchart", "-create_time")
        elif sort == "ast":
            problems = problems.annotate(
                _has_ast=Case(
                    When(ast_rules__isnull=False, then=Value(True)),
                    default=Value(False),
                    output_field=BooleanField(),
                )
            ).order_by("-_has_ast", "-create_time")
        elif sort:
            problems = problems.order_by(sort)

        # 根据profile 为做过的题目添加标记
        data = await self.async_paginate_data(request, problems, ProblemListSerializer)
        if request.user.is_authenticated:
            from account.models import UserProfile

            profile = await UserProfile.objects.aget(user=request.user)
            acm_problems_status = profile.acm_problems_status.get("problems", {})
            self._add_problem_status(acm_problems_status, data)
        return self.success(data)


class ContestProblemAPI(APIView):
    def _add_problem_status(self, request, queryset_values):
        if request.user.is_authenticated:
            profile = request.user.userprofile
            if self.contest.rule_type == ContestRuleType.ACM:
                problems_status = profile.acm_problems_status.get("contest_problems", {})
            else:
                problems_status = profile.oi_problems_status.get("contest_problems", {})
            for problem in queryset_values:
                problem["my_status"] = problems_status.get(str(problem["id"]), {}).get("status")

    @check_contest_permission(check_type="problems")
    def get(self, request):
        problem_id = request.GET.get("problem_id")
        if problem_id:
            try:
                problem = Problem.objects.select_related("created_by").get(_id__iexact=problem_id, contest=self.contest, visible=True)
            except Problem.DoesNotExist:
                return self.error("Problem does not exist.")
            if self.contest.problem_details_permission(request.user):
                problem_data = ProblemSerializer(problem).data
                self._add_problem_status(
                    request,
                    [
                        problem_data,
                    ],
                )
            else:
                problem_data = ProblemSafeSerializer(problem).data
            return self.success(problem_data)

        contest_problems = Problem.objects.select_related("created_by").prefetch_related("tags").filter(contest=self.contest, visible=True)
        if self.contest.problem_details_permission(request.user):
            data = ProblemListSerializer(contest_problems, many=True).data
            self._add_problem_status(request, data)
        else:
            data = ProblemSafeSerializer(contest_problems, many=True).data
        return self.success(data)


class ProblemSolvedPeopleCount(AsyncAPIView):
    async def get(self, request):
        problem_id = request.GET.get("problem_id")
        rate = "0"
        if not request.user.is_authenticated:
            return self.success(rate)
        submission_count = await Submission.objects.filter(
            user_id=request.user.id,
            problem_id=problem_id,
            result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED],
        ).acount()
        if submission_count == 0:
            return self.success(rate)
        now = timezone.now()
        years_ago = now.replace(year=now.year - 2, hour=0, minute=0, second=0, microsecond=0)
        total_count = await User.objects.filter(is_disabled=False, last_login__gte=years_ago).acount()
        accepted_count = (
            await sync_to_async(
                Submission.objects.filter(
                    problem_id=problem_id,
                    result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED],
                    create_time__gte=years_ago,
                ).aggregate,
                thread_sensitive=True,
            )(user_count=Count("user_id", distinct=True))
        )["user_count"]
        if total_count and accepted_count < total_count:
            rate = "%.2f" % ((total_count - accepted_count) / total_count * 100)
        else:
            rate = "0"
        return self.success(rate)


class SimilarProblemAPI(AsyncAPIView):
    async def get(self, request):
        problem_display_id = request.GET.get("problem_id")
        if not problem_display_id:
            return self.error("problem_id is required")

        try:
            problem = await Problem.objects.aget(_id__iexact=problem_display_id, contest__isnull=True)
        except Problem.DoesNotExist:
            return self.error("Problem not found")

        tag_ids = [tag_id async for tag_id in problem.tags.values_list("id", flat=True)]
        if not tag_ids:
            return self.success([])

        exclude_ids = [problem_display_id]
        if request.user.is_authenticated:
            from account.models import UserProfile

            profile = await UserProfile.objects.aget(user=request.user)
            ac_display_ids = [v["_id"] for v in profile.acm_problems_status.get("problems", {}).values() if v.get("status") == JudgeStatus.ACCEPTED]
            exclude_ids.extend(ac_display_ids)

        similar = (
            Problem.objects.select_related("created_by")
            .prefetch_related("tags")
            .filter(tags__in=tag_ids, visible=True, contest__isnull=True)
            .exclude(_id__in=exclude_ids)
            .distinct()
            .order_by("difficulty")[:5]
        )
        similar_list = [problem async for problem in similar]
        return self.success(await self.async_serialize_data(ProblemListSerializer, similar_list, many=True))


class ProblemAuthorAPI(AsyncAPIView):
    async def get(self, request):
        show_all = request.GET.get("all", "0") == "1"
        cache_key = f"{CacheKey.problem_authors}{'_all' if show_all else '_only_visible'}"
        cached_data = await async_cache_get(cache_key)
        if cached_data:
            return self.success(cached_data)

        problem_filter = {"contest_id__isnull": True, "created_by__is_disabled": False}
        if not show_all:
            problem_filter["visible"] = True

        authors = Problem.objects.filter(**problem_filter).values("created_by__username").annotate(problem_count=Count("id")).order_by("-problem_count")
        result = [
            {
                "username": author["created_by__username"],
                "problem_count": author["problem_count"],
            }
            async for author in authors
        ]

        await async_cache_set(cache_key, result, 7200)
        return self.success(result)


class ProblemYearlyACRateAPI(AsyncAPIView):
    async def get(self, request):
        problem_id = request.GET.get("problem_id")
        if not problem_id:
            return self.error("problem_id is required")

        cache_key = f"{CacheKey.problem_yearly_ac}:{problem_id}"
        cached = await async_cache_get(cache_key)
        if cached is not None:
            return self.success(cached)

        try:
            problem = await Problem.objects.aget(_id__iexact=problem_id, contest_id__isnull=True, visible=True)
        except Problem.DoesNotExist:
            return self.error("Problem does not exist")

        rows = (
            Submission.objects.filter(
                problem_id=problem.id,
                contest_id__isnull=True,
            )
            .exclude(result__in=[JudgeStatus.PENDING, JudgeStatus.JUDGING])
            .annotate(year=ExtractYear("create_time"))
            .values("year")
            .annotate(
                total=Count("id"),
                accepted=Count("id", filter=Q(result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED])),
            )
            .order_by("year")
        )

        data = [
            {
                "year": row["year"],
                "total": row["total"],
                "accepted": row["accepted"],
                "ac_rate": round(row["accepted"] / row["total"] * 100, 2) if row["total"] > 0 else 0.0,
            }
            async for row in rows
        ]

        await async_cache_set(cache_key, data, 3600)
        return self.success(data)
