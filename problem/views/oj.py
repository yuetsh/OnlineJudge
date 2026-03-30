from datetime import datetime
import random
from django.db.models import Q, Count
from django.core.cache import cache
from account.models import User
from submission.models import Submission, JudgeStatus
from utils.api import APIView
from account.decorators import check_contest_permission
from utils.constants import CacheKey
from ..models import ProblemTag, Problem, ProblemRuleType
from ..serializers import (
    ProblemSerializer,
    TagSerializer,
    ProblemSafeSerializer,
    ProblemListSerializer,
)
from contest.models import ContestRuleType


class ProblemTagAPI(APIView):
    def get(self, request):
        keyword = request.GET.get("keyword", "")
        cache_key = f"{CacheKey.problem_tags}:{keyword}"
        cached = cache.get(cache_key)
        if cached is not None:
            return self.success(cached)

        qs = ProblemTag.objects
        if keyword:
            qs = ProblemTag.objects.filter(name__icontains=keyword)
        tags = qs.annotate(problem_count=Count("problem")).filter(problem_count__gt=0)
        data = TagSerializer(tags, many=True).data
        cache.set(cache_key, data, 3600)
        return self.success(data)


class PickOneAPI(APIView):
    def get(self, request):
        problems = Problem.objects.filter(contest_id__isnull=True, visible=True)
        count = problems.count()
        if count == 0:
            return self.error("No problem to pick")
        return self.success(problems[random.randint(0, count - 1)]._id)


class ProblemAPI(APIView):
    @staticmethod
    def _add_problem_status(request, queryset_values):
        if request.user.is_authenticated:
            profile = request.user.userprofile
            acm_problems_status = profile.acm_problems_status.get("problems", {})
            # paginate data
            results = queryset_values.get("results")
            if results is not None:
                problems = results
            else:
                problems = [queryset_values]
            for problem in problems:
                problem["my_status"] = acm_problems_status.get(
                    str(problem["id"]), {}
                ).get("status")

    def get(self, request):
        # 问题详情页
        problem_id = request.GET.get("problem_id")
        if problem_id:
            try:
                problem = Problem.objects.select_related("created_by").get(
                    _id=problem_id, contest_id__isnull=True, visible=True
                )
                problem_data = ProblemSerializer(problem).data
                self._add_problem_status(request, problem_data)
                if request.user.is_authenticated:
                    failed_statuses = [
                        JudgeStatus.WRONG_ANSWER,
                        JudgeStatus.CPU_TIME_LIMIT_EXCEEDED,
                        JudgeStatus.REAL_TIME_LIMIT_EXCEEDED,
                        JudgeStatus.MEMORY_LIMIT_EXCEEDED,
                        JudgeStatus.RUNTIME_ERROR,
                        JudgeStatus.COMPILE_ERROR,
                    ]
                    problem_data["my_failed_count"] = Submission.objects.filter(
                        user_id=request.user.id,
                        problem_id=problem.id,
                        result__in=failed_statuses,
                    ).count()
                else:
                    problem_data["my_failed_count"] = 0
                return self.success(problem_data)
            except Problem.DoesNotExist:
                return self.error("Problem does not exist")

        limit = request.GET.get("limit")
        if not limit:
            return self.error("Limit is needed")

        problems = (
            Problem.objects.select_related("created_by")
            .prefetch_related("tags")
            .filter(contest_id__isnull=True, visible=True)
            .order_by("-create_time")
        )

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
            problems = problems.filter(
                Q(title__icontains=keyword) | Q(_id__icontains=keyword)
            )

        # 难度筛选
        difficulty = request.GET.get("difficulty")
        if difficulty:
            problems = problems.filter(difficulty=difficulty)

        # 排序
        sort = request.GET.get("sort")
        if sort:
            problems = problems.order_by(sort)

        # 根据profile 为做过的题目添加标记
        data = self.paginate_data(request, problems, ProblemListSerializer)
        self._add_problem_status(request, data)
        return self.success(data)


class ContestProblemAPI(APIView):
    def _add_problem_status(self, request, queryset_values):
        if request.user.is_authenticated:
            profile = request.user.userprofile
            if self.contest.rule_type == ContestRuleType.ACM:
                problems_status = profile.acm_problems_status.get(
                    "contest_problems", {}
                )
            else:
                problems_status = profile.oi_problems_status.get("contest_problems", {})
            for problem in queryset_values:
                problem["my_status"] = problems_status.get(str(problem["id"]), {}).get(
                    "status"
                )

    @check_contest_permission(check_type="problems")
    def get(self, request):
        problem_id = request.GET.get("problem_id")
        if problem_id:
            try:
                problem = Problem.objects.select_related("created_by").get(
                    _id=problem_id, contest=self.contest, visible=True
                )
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

        contest_problems = Problem.objects.select_related("created_by").prefetch_related("tags").filter(
            contest=self.contest, visible=True
        )
        if self.contest.problem_details_permission(request.user):
            data = ProblemListSerializer(contest_problems, many=True).data
            self._add_problem_status(request, data)
        else:
            data = ProblemSafeSerializer(contest_problems, many=True).data
        return self.success(data)


class ProblemSolvedPeopleCount(APIView):
    def get(self, request):
        problem_id = request.GET.get("problem_id")
        rate = "0"
        if not request.user.is_authenticated:
            return self.success(rate)
        submission_count = Submission.objects.filter(
            user_id=request.user.id,
            problem_id=problem_id,
            result=JudgeStatus.ACCEPTED,
        ).count()
        if submission_count == 0:
            return self.success(rate)
        today = datetime.today()
        years_ago = datetime(today.year - 2, today.month, today.day, 0, 0)
        total_count = User.objects.filter(
            is_disabled=False, last_login__gte=years_ago
        ).count()
        accepted_count = Submission.objects.filter(
            problem_id=problem_id,
            result=JudgeStatus.ACCEPTED,
            create_time__gte=years_ago,
        ).aggregate(user_count=Count("user_id", distinct=True))["user_count"]
        if accepted_count < total_count:
            rate = "%.2f" % ((total_count - accepted_count) / total_count * 100)
        else:
            rate = "0"
        return self.success(rate)


class SimilarProblemAPI(APIView):
    def get(self, request):
        problem_display_id = request.GET.get("problem_id")
        if not problem_display_id:
            return self.error("problem_id is required")

        try:
            problem = Problem.objects.get(_id=problem_display_id, contest__isnull=True)
        except Problem.DoesNotExist:
            return self.error("Problem not found")

        tag_ids = list(problem.tags.values_list("id", flat=True))
        if not tag_ids:
            return self.success([])

        exclude_ids = [problem_display_id]
        if request.user.is_authenticated:
            profile = request.user.userprofile
            ac_display_ids = [
                v["_id"]
                for v in profile.acm_problems_status.get("problems", {}).values()
                if v.get("status") == JudgeStatus.ACCEPTED
            ]
            exclude_ids.extend(ac_display_ids)

        similar = (
            Problem.objects.select_related("created_by")
            .prefetch_related("tags")
            .filter(tags__in=tag_ids, visible=True, contest__isnull=True)
            .exclude(_id__in=exclude_ids)
            .distinct()
            .order_by("difficulty")[:5]
        )
        return self.success(ProblemListSerializer(similar, many=True).data)


class ProblemAuthorAPI(APIView):
    def get(self, request):
        show_all = request.GET.get("all", "0") == "1"
        cache_key = f"{CacheKey.problem_authors}{'_all' if show_all else '_only_visible'}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return self.success(cached_data)

        problem_filter = {"contest_id__isnull": True, "created_by__is_disabled": False}
        if not show_all:
            problem_filter["visible"] = True

        authors = (
            Problem.objects.filter(**problem_filter)
            .values("created_by__username")
            .annotate(problem_count=Count("id"))
            .order_by("-problem_count")
        )
        result = [
            {
                "username": author["created_by__username"],
                "problem_count": author["problem_count"],
            }
            for author in authors
        ]

        cache.set(cache_key, result, 7200)
        return self.success(result)
