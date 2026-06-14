import ipaddress
import logging

from asgiref.sync import sync_to_async
from django.utils import timezone

from account.decorators import check_contest_permission, login_required
from contest.models import ContestStatus
from flowchart.models import FlowchartSubmission
from judge.tasks import judge_task
from options.options import SysOptions

# from judge.dispatcher import JudgeDispatcher
from problem.models import Problem, ProblemRuleType
from utils.api import APIView, AsyncAPIView, CSRFExemptAPIView, validate_serializer
from utils.cache import cache
from utils.captcha import Captcha
from utils.throttling import TokenBucket

from ..models import Submission
from ..serializers import (
    CreateSubmissionSerializer,
    FormatCodeSerializer,
    ShareSubmissionSerializer,
    SubmissionListSerializer,
    SubmissionModelSerializer,
    SubmissionSafeModelSerializer,
    bulk_fetch_problemset_progress,
)
from ..utils import FormatSyntaxError, FormatToolError, format_code

logger = logging.getLogger(__name__)


class SubmissionAPI(AsyncAPIView):
    def throttling(self, request):
        auth_method = getattr(request, "auth_method", "")
        if auth_method == "api_key":
            return
        user_bucket = TokenBucket(
            key=str(request.user.id), redis_conn=cache, **SysOptions.throttling["user"]
        )
        can_consume, wait = user_bucket.consume()
        if not can_consume:
            return "Please wait %d seconds" % (int(wait))

    @check_contest_permission(check_type="problems")
    async def check_contest_permission(self, request):
        contest = self.contest
        if contest.status == ContestStatus.CONTEST_ENDED:
            return self.error("The contest have ended")
        if not request.user.is_contest_admin(contest):
            user_ip = ipaddress.ip_address(request.session.get("ip"))
            if contest.allowed_ip_ranges:
                if not any(
                    user_ip in ipaddress.ip_network(cidr, strict=False)
                    for cidr in contest.allowed_ip_ranges
                ):
                    return self.error("Your IP is not allowed in this contest")

    @login_required
    @validate_serializer(CreateSubmissionSerializer)
    async def post(self, request):
        data = request.data
        hide_id = False
        if data.get("contest_id"):
            error = await self.check_contest_permission(request)
            if error:
                return error
            contest = self.contest
            if not contest.problem_details_permission(request.user):
                hide_id = True

        if data.get("captcha"):
            if not Captcha(request).check(data["captcha"]):
                return self.error("Invalid captcha")
        error = await sync_to_async(self.throttling)(request)
        if error:
            return self.error(error)

        try:
            problem = await Problem.objects.aget(
                id=data["problem_id"], contest_id=data.get("contest_id"), visible=True
            )
        except Problem.DoesNotExist:
            return self.error("Problem not exist")
        if data["language"] not in problem.languages:
            return self.error(f"{data['language']} is not allowed in the problem")
        submission = await Submission.objects.acreate(
            user_id=request.user.id,
            username=request.user.username,
            language=data["language"],
            code=data["code"],
            problem_id=problem.id,
            ip=request.session["ip"],
            contest_id=data.get("contest_id"),
        )

        judge_task.send(submission.id, problem.id)
        if hide_id:
            return self.success()
        else:
            return self.success({"submission_id": submission.id})

    @login_required
    async def get(self, request):
        submission_id = request.GET.get("id")
        if not submission_id:
            return self.error("Parameter id doesn't exist")
        try:
            submission = await Submission.objects.select_related("problem", "contest").aget(
                id=submission_id
            )
        except Submission.DoesNotExist:
            return self.error("Submission doesn't exist")
        if not submission.check_user_permission(request.user):
            return self.error("No permission for this submission")

        if (
            submission.problem.rule_type == ProblemRuleType.OI
            or request.user.is_admin_role()
        ):
            submission_data = await self.async_serialize_data(SubmissionModelSerializer, submission)
        else:
            submission_data = await self.async_serialize_data(SubmissionSafeModelSerializer, submission)
        submission_data["can_unshare"] = submission.check_user_permission(
            request.user, check_share=False
        )
        return self.success(submission_data)

    @login_required
    @validate_serializer(ShareSubmissionSerializer)
    async def put(self, request):
        try:
            submission = await Submission.objects.select_related("problem", "contest").aget(
                id=request.data["id"]
            )
        except Submission.DoesNotExist:
            return self.error("Submission doesn't exist")
        if not submission.check_user_permission(request.user, check_share=False):
            return self.error("No permission to share the submission")
        if (
            submission.contest
            and submission.contest.status == ContestStatus.CONTEST_UNDERWAY
        ):
            return self.error("Can not share submission now")
        submission.shared = request.data["shared"]
        await submission.asave(update_fields=["shared"])
        return self.success()


class SubmissionListAPI(AsyncAPIView):
    async def get(self, request):
        if not request.GET.get("limit"):
            return self.error("Limit is needed")
        if request.GET.get("contest_id"):
            return self.error("Parameter error")

        submissions = Submission.objects.filter(contest_id__isnull=True).select_related(
            "problem"
        ).order_by("-create_time")
        problem_id = request.GET.get("problem_id")
        myself = request.GET.get("myself")
        result = request.GET.get("result")
        username = request.GET.get("username")
        language = request.GET.get("language")
        if problem_id:
            try:
                problem = await Problem.objects.aget(
                    _id__iexact=problem_id, contest_id__isnull=True, visible=True
                )
            except Problem.DoesNotExist:
                return self.error("Problem doesn't exist")
            submissions = submissions.filter(problem=problem)

        show_all = await SysOptions.aget("submission_list_show_all")
        if not show_all and request.user.is_regular_user():
            return self.success({"results": [], "total": 0})

        if myself and myself == "1":
            submissions = submissions.filter(user_id=request.user.id)
        elif username:
            submissions = submissions.filter(username__icontains=username)
        if result:
            submissions = submissions.filter(result=result)
        if language:
            submissions = submissions.filter(language=language)
        if request.GET.get("today") == "1":
            now = timezone.now()
            submissions = submissions.filter(
                create_time__gte=now.replace(hour=0, minute=0, second=0, microsecond=0)
            )

        data = await self.async_paginate_data(request, submissions)
        results = data["results"]
        if request.user.is_authenticated and request.user.is_regular_user():
            problem_ids = list({s.problem_id for s in results})
            progress_cache = await sync_to_async(bulk_fetch_problemset_progress)(request.user, problem_ids)
        else:
            progress_cache = {}
        data["results"] = await self.async_serialize_data(
            SubmissionListSerializer,
            results,
            many=True,
            user=request.user,
            problemset_progress_cache=progress_cache,
        )
        return self.success(data)


class ContestSubmissionListAPI(AsyncAPIView):
    @check_contest_permission(check_type="submissions")
    async def get(self, request):
        if not request.GET.get("limit"):
            return self.error("Limit is needed")

        contest = self.contest
        submissions = Submission.objects.filter(contest_id=contest.id).select_related(
            "problem", "contest"
        ).order_by("-create_time")
        problem_id = request.GET.get("problem_id")
        myself = request.GET.get("myself")
        result = request.GET.get("result")
        username = request.GET.get("username")
        if problem_id:
            try:
                problem = await Problem.objects.aget(
                    _id__iexact=problem_id, contest_id=contest.id, visible=True
                )
            except Problem.DoesNotExist:
                return self.error("Problem doesn't exist")
            submissions = submissions.filter(problem=problem)

        if myself and myself == "1":
            submissions = submissions.filter(user_id=request.user.id)
        elif username:
            submissions = submissions.filter(username__icontains=username)
        if result:
            submissions = submissions.filter(result=result)

        if contest.status != ContestStatus.CONTEST_NOT_START:
            submissions = submissions.filter(create_time__gte=contest.start_time)

        data = await self.async_paginate_data(request, submissions)
        results = data["results"]
        if request.user.is_authenticated and request.user.is_regular_user():
            problem_ids = list({s.problem_id for s in results})
            progress_cache = await sync_to_async(bulk_fetch_problemset_progress)(request.user, problem_ids)
        else:
            progress_cache = {}
        data["results"] = await self.async_serialize_data(
            SubmissionListSerializer,
            results, many=True, user=request.user, problemset_progress_cache=progress_cache
        )
        return self.success(data)


# DEPRECATED: 前端未调用 (2026-05-26)
class SubmissionExistsAPI(AsyncAPIView):
    async def get(self, request):
        if not request.GET.get("problem_id"):
            return self.error("Parameter error, problem_id is required")
        exists = (
            request.user.is_authenticated
            and await Submission.objects.filter(
                problem_id=request.GET["problem_id"], user_id=request.user.id
            ).aexists()
        )
        return self.success(exists)


class SubmissionsTodayCount(AsyncAPIView):
    async def get(self, request):
        now = timezone.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if request.GET.get("language") == "Flowchart":
            count = await FlowchartSubmission.objects.filter(
                create_time__gte=start
            ).acount()
        else:
            count = await Submission.objects.filter(
                contest_id__isnull=True, create_time__gte=start
            ).acount()
        return self.success(count)


class FormatCodeAPI(CSRFExemptAPIView):
    @login_required
    @validate_serializer(FormatCodeSerializer)
    def post(self, request):
        code = request.data["code"]
        language = request.data["language"]
        try:
            formatted = format_code(code, language)
        except FormatSyntaxError as e:
            return self.error(msg=str(e), err="format-error")
        except FormatToolError as e:
            logger.exception("format_code tool error: %s", e)
            return self.error(msg="format failed", err="server-error")
        return self.success({"code": formatted})
