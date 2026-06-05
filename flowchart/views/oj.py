from django.utils import timezone

from account.decorators import login_required
from flowchart.models import FlowchartSubmission, FlowchartSubmissionStatus
from flowchart.serializers import (
    CreateFlowchartSubmissionSerializer,
    FlowchartSubmissionListSerializer,
    FlowchartSubmissionSerializer,
)
from flowchart.tasks import evaluate_flowchart_task
from problem.models import Problem
from utils.api import AsyncAPIView


class FlowchartSubmissionAPI(AsyncAPIView):
    @login_required
    async def post(self, request):
        serializer = CreateFlowchartSubmissionSerializer(data=request.data)
        if not serializer.is_valid():
            return self.error(serializer.errors)

        data = serializer.validated_data

        try:
            problem = await Problem.objects.aget(id=data["problem_id"])
        except Problem.DoesNotExist:
            return self.error("Problem doesn't exist")

        if not problem.allow_flowchart:
            return self.error("This problem does not allow flowchart submission")

        submission = await FlowchartSubmission.objects.acreate(
            user=request.user,
            problem=problem,
            mermaid_code=data["mermaid_code"],
            flowchart_data=data.get("flowchart_data", {}),
        )

        evaluate_flowchart_task.send(submission.id)

        return self.success({"submission_id": submission.id, "status": "pending"})

    @login_required
    async def get(self, request):
        submission_id = request.GET.get("id")
        if not submission_id:
            return self.error("submission_id is required")

        try:
            submission = await (
                FlowchartSubmission.objects.select_related("user", "problem")
                .filter(id=submission_id)
                .afirst()
            )
            if submission is None:
                raise FlowchartSubmission.DoesNotExist
        except FlowchartSubmission.DoesNotExist:
            return self.error("Submission doesn't exist")

        if not submission.check_user_permission(request.user):
            return self.error("No permission for this submission")

        return self.success(await self.async_serialize_data(FlowchartSubmissionSerializer, submission))


class FlowchartSubmissionListAPI(AsyncAPIView):
    @login_required
    async def get(self, request):
        username = request.GET.get("username")
        problem_id = request.GET.get("problem_id")
        myself = request.GET.get("myself")

        queryset = FlowchartSubmission.objects.select_related("user", "problem")

        if problem_id:
            try:
                problem = await Problem.objects.aget(
                    _id__iexact=problem_id, contest_id__isnull=True, visible=True
                )
            except Problem.DoesNotExist:
                return self.error("Problem doesn't exist")
            queryset = queryset.filter(problem=problem)

        if myself and myself == "1":
            queryset = queryset.filter(user=request.user)
        elif username:
            queryset = queryset.filter(user__username__icontains=username)
        elif request.user.is_regular_user():
            queryset = queryset.filter(user=request.user)

        if request.GET.get("today") == "1":
            now = timezone.now()
            queryset = queryset.filter(
                create_time__gte=now.replace(hour=0, minute=0, second=0, microsecond=0)
            )

        data = await self.async_paginate_data(request, queryset)
        data["results"] = await self.async_serialize_data(
            FlowchartSubmissionListSerializer,
            data["results"],
            many=True,
        )
        return self.success(data)


class FlowchartSubmissionRetryAPI(AsyncAPIView):
    @login_required
    async def post(self, request):
        submission_id = request.data.get("submission_id")
        if not submission_id:
            return self.error("submission_id is required")

        try:
            submission = await (
                FlowchartSubmission.objects.select_related("problem")
                .filter(id=submission_id)
                .afirst()
            )
            if submission is None:
                raise FlowchartSubmission.DoesNotExist
        except FlowchartSubmission.DoesNotExist:
            return self.error("Submission doesn't exist")

        if not submission.check_user_permission(request.user):
            return self.error("No permission for this submission")

        if submission.status not in [
            FlowchartSubmissionStatus.FAILED,
            FlowchartSubmissionStatus.COMPLETED,
        ]:
            return self.error("Submission is not in a state that allows retry")

        submission.status = FlowchartSubmissionStatus.PENDING
        submission.ai_score = None
        submission.ai_grade = None
        submission.ai_feedback = None
        submission.ai_suggestions = None
        submission.ai_criteria_details = {}
        submission.processing_time = None
        submission.evaluation_time = None
        await submission.asave()

        evaluate_flowchart_task.send(submission.id)

        return self.success(
            {
                "submission_id": submission.id,
                "status": "pending",
                "message": "AI evaluation restarted",
            }
        )


class FlowchartSubmissionDetailAPI(AsyncAPIView):
    @login_required
    async def get(self, request):
        problem_id = request.GET.get("problem_id")
        if not problem_id:
            return self.error("problem_id is required")
        try:
            problem = await Problem.objects.aget(id=problem_id)
        except Problem.DoesNotExist:
            return self.error("Problem doesn't exist")

        try:
            page = int(request.GET.get("page", 0))
        except ValueError:
            return self.error("page must be an integer")
        submissions = (
            FlowchartSubmission.objects.select_related("user", "problem")
            .filter(
                user=request.user,
                problem=problem,
                status=FlowchartSubmissionStatus.COMPLETED,
            )
            .order_by("create_time")
        )
        count = await submissions.acount()
        if count == 0:
            return self.success({"submission": None, "count": 0})
        if page == 0:
            submission = await submissions.alast()
        else:
            if page < 0 or page > count:
                return self.error("Page out of range")
            result = [s async for s in submissions[page - 1:page]]
            submission = result[0]
        data = await self.async_serialize_data(FlowchartSubmissionSerializer, submission)
        return self.success({"submission": data, "count": count})


class FlowchartSubmissionCurrentAPI(AsyncAPIView):
    @login_required
    async def get(self, request):
        problem_id = request.GET.get("problem_id")
        if not problem_id:
            return self.error("problem_id is required")
        try:
            problem = await Problem.objects.aget(id=problem_id)
        except Problem.DoesNotExist:
            return self.error("Problem doesn't exist")
        submissions = (
            FlowchartSubmission.objects.filter(
                user=request.user,
                problem=problem,
                status=FlowchartSubmissionStatus.COMPLETED,
            )
            .values("ai_score", "ai_grade")
            .order_by("-create_time")
        )
        count = await submissions.acount()
        if count == 0:
            return self.success({"count": 0, "score": 0, "grade": ""})
        submission = await submissions.afirst()
        return self.success(
            {
                "count": count,
                "score": submission["ai_score"],
                "grade": submission["ai_grade"],
            }
        )
