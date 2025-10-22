
from django.db.models import Q
from django.db import models
from django.utils import timezone

from utils.api import APIView, validate_serializer

from problemset.models import (
    ProblemSet,
    ProblemSetProblem,
    ProblemSetBadge,
    ProblemSetProgress,
    UserBadge,
    ProblemSetSubmission,
)
from problemset.serializers import (
    ProblemSetSerializer,
    ProblemSetListSerializer,
    ProblemSetProblemSerializer,
    ProblemSetBadgeSerializer,
    ProblemSetProgressSerializer,
    UserBadgeSerializer,
    JoinProblemSetSerializer,
    UpdateProgressSerializer,
    ProblemSetSubmissionSerializer,
)


class ProblemSetAPI(APIView):
    """题单API - 用户端"""

    def get(self, request):
        """获取题单列表"""
        problem_sets = ProblemSet.objects.filter(visible=True).exclude(status="draft")

        # 过滤条件
        keyword = request.GET.get("keyword", "").strip()
        if keyword:
            problem_sets = problem_sets.filter(
                Q(title__icontains=keyword) | Q(description__icontains=keyword)
            )

        difficulty = request.GET.get("difficulty")
        if difficulty:
            problem_sets = problem_sets.filter(difficulty=difficulty)

        status_filter = request.GET.get("status")
        if status_filter:
            problem_sets = problem_sets.filter(status=status_filter)

        # 排序
        sort = request.GET.get("sort")
        if sort:
            problem_sets = problem_sets.order_by(sort)
        else:
            problem_sets = problem_sets.order_by("-create_time")

        data = self.paginate_data(request, problem_sets, ProblemSetListSerializer)
        return self.success(data)


class ProblemSetDetailAPI(APIView):
    """题单详情API - 用户端"""

    def get(self, request, problem_set_id):
        """获取题单详情"""
        try:
            problem_set = ProblemSet.objects.filter(id=problem_set_id, visible=True).exclude(status="draft").get()
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        serializer = ProblemSetSerializer(problem_set, context={"request": request})
        return self.success(serializer.data)


class ProblemSetProblemAPI(APIView):
    """题单题目API - 用户端"""

    def get(self, request, problem_set_id):
        """获取题单中的题目列表"""
        try:
            problem_set = ProblemSet.objects.filter(id=problem_set_id, visible=True).exclude(status="draft").get()
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        problems = ProblemSetProblem.objects.filter(problemset=problem_set).order_by(
            "order"
        )
        serializer = ProblemSetProblemSerializer(
            problems, many=True, context={"request": request}
        )
        return self.success(serializer.data)


class ProblemSetProgressAPI(APIView):
    """题单进度API"""

    @validate_serializer(JoinProblemSetSerializer)
    def post(self, request):
        """加入题单"""
        data = request.data
        try:
            problem_set = ProblemSet.objects.filter(id=data["problemset_id"], visible=True).exclude(status="draft").get()
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        if ProblemSetProgress.objects.filter(
            problemset=problem_set, user=request.user
        ).exists():
            return self.error("已经加入该题单")

        # 创建进度记录
        progress = ProblemSetProgress.objects.create(
            problemset=problem_set, user=request.user
        )
        progress.update_progress()

        return self.success("成功加入题单")

    def get(self, request, problem_set_id):
        """获取题单进度"""
        try:
            problem_set = ProblemSet.objects.filter(id=problem_set_id, visible=True).exclude(status="draft").get()
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        try:
            progress = ProblemSetProgress.objects.get(
                problemset=problem_set, user=request.user
            )
        except ProblemSetProgress.DoesNotExist:
            return self.error("未加入该题单")

        serializer = ProblemSetProgressSerializer(progress)
        return self.success(serializer.data)

    @validate_serializer(UpdateProgressSerializer)
    def put(self, request):
        """更新进度"""
        data = request.data
        try:
            problem_set = ProblemSet.objects.filter(id=data["problemset_id"], visible=True).exclude(status="draft").get()
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        try:
            progress = ProblemSetProgress.objects.get(
                problemset=problem_set, user=request.user
            )
        except ProblemSetProgress.DoesNotExist:
            return self.error("未加入该题单")

        # 更新详细进度
        problem_id = str(data["problem_id"])
        progress.progress_detail[problem_id] = {
            "status": data["status"],
            "score": data.get("score", 0),
            "submit_time": data.get("submit_time", timezone.now().isoformat()),
        }

        # 更新进度
        progress.update_progress()

        # 检查是否获得奖章
        self._check_badges(progress)

        return self.success("进度已更新")

    def _check_badges(self, progress):
        """检查是否获得奖章"""
        badges = ProblemSetBadge.objects.filter(problemset=progress.problemset)

        for badge in badges:
            # 检查是否已经获得该奖章
            if UserBadge.objects.filter(user=progress.user, badge=badge).exists():
                continue

            # 检查是否满足获得条件
            if badge.condition_type == "all_problems":
                if progress.completed_problems_count == progress.total_problems_count:
                    UserBadge.objects.create(user=progress.user, badge=badge)
            elif badge.condition_type == "problem_count":
                if progress.completed_problems_count >= badge.condition_value:
                    UserBadge.objects.create(user=progress.user, badge=badge)
            elif badge.condition_type == "score":
                if progress.total_score >= badge.condition_value:
                    UserBadge.objects.create(user=progress.user, badge=badge)


class UserProgressAPI(APIView):
    """用户进度API"""

    def get(self, request):
        """获取用户的题单进度列表"""
        progress_list = ProblemSetProgress.objects.filter(user=request.user).order_by(
            "-join_time"
        )
        serializer = ProblemSetProgressSerializer(progress_list, many=True)
        return self.success(serializer.data)


class UserBadgeAPI(APIView):
    """用户奖章API"""

    def get(self, request):
        """获取用户的奖章列表"""
        badges = UserBadge.objects.filter(user=request.user).order_by("-earned_time")
        serializer = UserBadgeSerializer(badges, many=True)
        return self.success(serializer.data)

    def put(self, request, badge_id):
        """标记奖章为已展示"""
        try:
            user_badge = UserBadge.objects.get(id=badge_id, user=request.user)
            user_badge.is_displayed = True
            user_badge.save()
            return self.success("奖章已标记为已展示")
        except UserBadge.DoesNotExist:
            return self.error("奖章不存在")


class ProblemSetBadgeAPI(APIView):
    """题单奖章API - 用户端"""

    def get(self, request, problem_set_id):
        """获取题单的奖章列表"""
        try:
            problem_set = ProblemSet.objects.filter(id=problem_set_id, visible=True).exclude(status="draft").get()
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        badges = ProblemSetBadge.objects.filter(problemset=problem_set)
        serializer = ProblemSetBadgeSerializer(badges, many=True)
        return self.success(serializer.data)


class ProblemSetSubmissionAPI(APIView):
    """题单提交记录API - 用户端"""

    def get(self, request, problem_set_id):
        """获取用户在题单中的提交记录"""
        try:
            problem_set = ProblemSet.objects.filter(id=problem_set_id, visible=True).exclude(status="draft").get()
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        # 检查用户是否已加入该题单
        try:
            ProblemSetProgress.objects.get(problemset=problem_set, user=request.user)
        except ProblemSetProgress.DoesNotExist:
            return self.error("您还未加入该题单")

        # 获取查询参数
        problem_id = request.GET.get("problem_id")
        result = request.GET.get("result")
        language = request.GET.get("language")
        
        # 构建查询条件
        query_filter = {
            "problemset": problem_set,
            "user": request.user
        }
        
        if problem_id:
            query_filter["problem_id"] = problem_id
        if result:
            query_filter["result"] = result
        if language:
            query_filter["language"] = language

        # 获取提交记录
        submissions = ProblemSetSubmission.objects.filter(**query_filter).order_by("-submit_time")

        # 分页
        data = self.paginate_data(request, submissions, ProblemSetSubmissionSerializer)
        return self.success(data)


class ProblemSetStatisticsAPI(APIView):
    """题单统计API - 用户端"""

    def get(self, request, problem_set_id):
        """获取题单统计信息"""
        try:
            problem_set = ProblemSet.objects.filter(id=problem_set_id, visible=True).exclude(status="draft").get()
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        # 检查用户是否已加入该题单
        try:
            progress = ProblemSetProgress.objects.get(problemset=problem_set, user=request.user)
        except ProblemSetProgress.DoesNotExist:
            return self.error("您还未加入该题单")

        # 获取统计信息
        total_submissions = ProblemSetSubmission.objects.filter(
            problemset=problem_set, user=request.user
        ).count()
        
        accepted_submissions = ProblemSetSubmission.objects.filter(
            problemset=problem_set, user=request.user, result=0
        ).count()
        
        # 按题目统计
        problem_stats = {}
        problemset_problems = ProblemSetProblem.objects.filter(problemset=problem_set)
        
        for psp in problemset_problems:
            problem_id = psp.problem.id
            problem_submissions = ProblemSetSubmission.objects.filter(
                problemset=problem_set, 
                user=request.user, 
                problem=psp.problem
            )
            
            problem_stats[str(problem_id)] = {
                "problem_title": psp.problem.title,
                "total_submissions": problem_submissions.count(),
                "accepted_submissions": problem_submissions.filter(result=0).count(),
                "is_completed": str(problem_id) in progress.progress_detail and 
                               progress.progress_detail[str(problem_id)].get("status") == "completed"
            }

        # 按语言统计
        language_stats = {}
        language_submissions = ProblemSetSubmission.objects.filter(
            problemset=problem_set, user=request.user
        ).values('language').annotate(count=models.Count('id'))
        
        for item in language_submissions:
            language_stats[item['language']] = item['count']

        # 按结果统计
        result_stats = {}
        result_submissions = ProblemSetSubmission.objects.filter(
            problemset=problem_set, user=request.user
        ).values('result').annotate(count=models.Count('id'))
        
        for item in result_submissions:
            result_stats[item['result']] = item['count']

        data = {
            "total_submissions": total_submissions,
            "accepted_submissions": accepted_submissions,
            "acceptance_rate": round(accepted_submissions / total_submissions * 100, 2) if total_submissions > 0 else 0,
            "problem_stats": problem_stats,
            "language_stats": language_stats,
            "result_stats": result_stats,
            "progress": {
                "completed_problems_count": progress.completed_problems_count,
                "total_problems_count": progress.total_problems_count,
                "progress_percentage": progress.progress_percentage,
                "total_score": progress.total_score
            }
        }
        
        return self.success(data)
