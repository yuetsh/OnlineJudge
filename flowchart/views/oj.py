from utils.api import APIView
from account.decorators import login_required
from flowchart.models import FlowchartSubmission, FlowchartSubmissionStatus
from flowchart.serializers import (
    CreateFlowchartSubmissionSerializer,
    FlowchartSubmissionSerializer,
    FlowchartSubmissionListSerializer,
)
from flowchart.tasks import evaluate_flowchart_task
from problem.models import Problem


class FlowchartSubmissionAPI(APIView):
    @login_required
    def post(self, request):
        """创建流程图提交"""
        serializer = CreateFlowchartSubmissionSerializer(data=request.data)
        if not serializer.is_valid():
            return self.error(serializer.errors)

        data = serializer.validated_data

        # 验证题目存在
        try:
            from problem.models import Problem

            problem = Problem.objects.get(id=data["problem_id"])
        except Problem.DoesNotExist:
            return self.error("Problem doesn't exist")

        # 验证题目是否允许流程图提交
        if not problem.allow_flowchart:
            return self.error("This problem does not allow flowchart submission")

        # 创建提交记录
        submission = FlowchartSubmission.objects.create(
            user=request.user,
            problem=problem,
            mermaid_code=data["mermaid_code"],
            flowchart_data=data.get("flowchart_data", {}),
        )

        # 启动AI评分任务
        evaluate_flowchart_task.send(submission.id)

        return self.success({"submission_id": submission.id, "status": "pending"})

    @login_required
    def get(self, request):
        """获取流程图提交详情"""
        submission_id = request.GET.get("id")
        if not submission_id:
            return self.error("submission_id is required")

        try:
            submission = FlowchartSubmission.objects.get(id=submission_id)
        except FlowchartSubmission.DoesNotExist:
            return self.error("Submission doesn't exist")

        if not submission.check_user_permission(request.user):
            return self.error("No permission for this submission")

        serializer = FlowchartSubmissionSerializer(submission)
        return self.success(serializer.data)


class FlowchartSubmissionListAPI(APIView):
    @login_required
    def get(self, request):
        """获取流程图提交列表"""
        user_id = request.GET.get("user_id")
        problem_id = request.GET.get("problem_id")
        offset = int(request.GET.get("offset", 0))
        limit = int(request.GET.get("limit", 20))

        queryset = FlowchartSubmission.objects.select_related("user", "problem")

        # 权限过滤
        if not request.user.is_admin_role():
            queryset = queryset.filter(user=request.user)

        # 其他过滤条件
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        if problem_id:
            queryset = queryset.filter(problem_id=problem_id)

        total = queryset.count()
        submissions = queryset[offset : offset + limit]

        serializer = FlowchartSubmissionListSerializer(submissions, many=True)

        return self.success({"results": serializer.data, "total": total})


class FlowchartSubmissionRetryAPI(APIView):
    @login_required
    def post(self, request):
        """重新触发AI评分"""
        submission_id = request.data.get("submission_id")
        if not submission_id:
            return self.error("submission_id is required")

        try:
            submission = FlowchartSubmission.objects.get(id=submission_id)
        except FlowchartSubmission.DoesNotExist:
            return self.error("Submission doesn't exist")

        # 检查权限
        if not submission.check_user_permission(request.user):
            return self.error("No permission for this submission")

        # 检查是否可以重新评分
        if submission.status not in [
            FlowchartSubmissionStatus.FAILED,
            FlowchartSubmissionStatus.COMPLETED,
        ]:
            return self.error("Submission is not in a state that allows retry")

        # 重置状态并重新启动AI评分
        submission.status = FlowchartSubmissionStatus.PENDING
        submission.ai_score = None
        submission.ai_grade = None
        submission.ai_feedback = None
        submission.ai_suggestions = None
        submission.ai_criteria_details = {}
        submission.processing_time = None
        submission.evaluation_time = None
        submission.save()

        # 重新启动AI评分任务
        evaluate_flowchart_task.send(submission.id)

        return self.success(
            {
                "submission_id": submission.id,
                "status": "pending",
                "message": "AI evaluation restarted",
            }
        )


class FlowchartSubmissionCurrentAPI(APIView):
    @login_required
    def get(self, request):
        """获取当前用户对指定题目的最新流程图提交"""
        problem_id = request.GET.get("problem_id")
        if not problem_id:
            return self.error("problem_id is required")
        try:
            problem = Problem.objects.get(id=problem_id)
        except Problem.DoesNotExist:
            return self.error("Problem doesn't exist")

        submissions = FlowchartSubmission.objects.filter(
            user=request.user, problem=problem
        ).order_by("-create_time")
        count = submissions.count()
        if count == 0:
            return self.success({"submission": None, "count": 0})
        first_submission = submissions[0]
        serializer = FlowchartSubmissionSerializer(first_submission)
        return self.success({"submission": serializer.data, "count": count})
