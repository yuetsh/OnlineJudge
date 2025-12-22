from django.db.models import Q, Avg, Count
from django.utils import timezone

from utils.api import APIView, validate_serializer

from account.models import User

from problemset.models import (
    ProblemSet,
    ProblemSetProblem,
    ProblemSetBadge,
    ProblemSetProgress,
    ProblemSetSubmission,
    UserBadge,
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
)

from submission.models import Submission
from problem.models import Problem


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
            problem_set = (
                ProblemSet.objects.filter(id=problem_set_id, visible=True)
                .exclude(status="draft")
                .get()
            )
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        serializer = ProblemSetSerializer(problem_set, context={"request": request})
        return self.success(serializer.data)


class ProblemSetProblemAPI(APIView):
    """题单题目API - 用户端"""

    def get(self, request, problem_set_id):
        """获取题单中的题目列表"""
        try:
            problem_set = (
                ProblemSet.objects.filter(id=problem_set_id, visible=True)
                .exclude(status="draft")
                .get()
            )
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
            problem_set = (
                ProblemSet.objects.filter(id=data["problemset_id"], visible=True)
                .exclude(status="draft")
                .get()
            )
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
            problem_set = (
                ProblemSet.objects.filter(id=problem_set_id, visible=True)
                .exclude(status="draft")
                .get()
            )
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
            problem_set = (
                ProblemSet.objects.filter(id=data["problemset_id"], visible=True)
                .exclude(status="draft")
                .get()
            )
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

        # 获取该题目在题单中的分值
        try:
            problemset_problem = ProblemSetProblem.objects.get(
                problemset=problem_set, problem_id=problem_id
            )
            problem_score = problemset_problem.score
        except ProblemSetProblem.DoesNotExist:
            problem_score = 0

        progress.progress_detail[problem_id] = {
            "score": problem_score,  # 题单中设置的分值
            "submit_time": data.get("submit_time", timezone.now().isoformat()),
        }

        # 更新进度
        progress.update_progress()

        # 只有当提供了submission_id时才创建ProblemSetSubmission记录
        if "submission_id" in data and data["submission_id"]:
            try:
                submission = Submission.objects.get(id=data["submission_id"])
                problem = Problem.objects.get(id=problem_id)

                has_accepted = ProblemSetSubmission.objects.filter(
                    problemset=problem_set,
                    user=request.user,
                    problem=problem,
                ).exists()
                if not has_accepted:
                    ProblemSetSubmission.objects.create(
                        problemset=problem_set,
                        user=request.user,
                        submission=submission,
                        problem=problem,
                    )
            except Submission.DoesNotExist:
                # 如果提交记录不存在，记录错误但不中断流程
                pass

        # 检查是否获得奖章
        self._check_badges(progress)

        return self.success("进度已更新")

    def _check_badges(self, progress):
        """检查是否获得奖章"""
        badges = ProblemSetBadge.objects.filter(problemset=progress.problemset)

        for badge in badges:
            if UserBadge.objects.filter(user=progress.user, badge=badge).exists():
                continue

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
        # 支持通过username参数获取指定用户的徽章
        username = request.GET.get("username")
        
        if username:
            # 获取指定用户的徽章
            try:
                target_user = User.objects.get(username=username, is_disabled=False)
                badges = UserBadge.objects.filter(user=target_user).order_by("-earned_time")
            except User.DoesNotExist:
                return self.error("用户不存在")
        else:
            # 获取当前用户的徽章
            badges = UserBadge.objects.filter(user=request.user).order_by("-earned_time")
        
        serializer = UserBadgeSerializer(badges, many=True)
        return self.success(serializer.data)


class ProblemSetBadgeAPI(APIView):
    """题单奖章API - 用户端"""

    def get(self, request, problem_set_id):
        """获取题单的奖章列表"""
        try:
            problem_set = (
                ProblemSet.objects.filter(id=problem_set_id, visible=True)
                .exclude(status="draft")
                .get()
            )
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        badges = ProblemSetBadge.objects.filter(problemset=problem_set)
        serializer = ProblemSetBadgeSerializer(badges, many=True)
        return self.success(serializer.data)


class ProblemSetUserProgressAPI(APIView):
    """题单用户进度列表API"""

    def get(self, request, problem_set_id: int):
        """获取题单的用户进度列表"""
        try:
            problem_set = (
                ProblemSet.objects.filter(id=problem_set_id, visible=True)
                .exclude(status="draft")
                .get()
            )
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        # 获取所有参与该题单的用户进度，使用 select_related 预加载用户信息
        progresses = ProblemSetProgress.objects.filter(problemset=problem_set).select_related('user')
        
        # 班级过滤
        class_name = request.GET.get("class_name", "").strip()
        if class_name:
            progresses = progresses.filter(user__username__icontains=class_name)
        
        # 排序
        progresses = progresses.order_by(
            "-is_completed", "-progress_percentage", "join_time"
        )
        
        # 计算统计数据（基于所有数据，而非分页数据）
        # 使用一次查询获取所有统计数据
        stats = progresses.aggregate(
            total=Count('id'),
            completed=Count('id', filter=Q(is_completed=True)),
            avg_progress=Avg("progress_percentage")
        )
        total_count = stats['total']
        completed_count = stats['completed']
        avg_progress = stats['avg_progress'] or 0
        
        # 获取分页参数，用于预先收集当前页需要的问题ID
        try:
            limit = int(request.GET.get("limit", "10"))
        except ValueError:
            limit = 10
        try:
            offset = int(request.GET.get("offset", "0"))
        except ValueError:
            offset = 0
        if offset < 0:
            offset = 0
        
        # 只从当前页的数据中收集问题ID，避免遍历所有记录
        paginated_progresses = list(progresses[offset:offset + limit])
        all_problem_ids = set()
        for progress in paginated_progresses:
            if progress.progress_detail:
                all_problem_ids.update(progress.progress_detail.keys())
        
        # 批量加载当前页所需的问题
        problems_dict = {}
        if all_problem_ids:
            problems = Problem.objects.filter(id__in=all_problem_ids).only('id', '_id', 'title')
            problems_dict = {str(problem.id): problem for problem in problems}
        
        # 将预加载的问题字典存储到 request 中，供序列化器使用
        request._problems_dict_cache = problems_dict
        
        # 使用分页
        data = self.paginate_data(request, progresses, ProblemSetProgressSerializer)
        
        # 添加统计数据
        data["statistics"] = {
            "total": total_count,
            "completed": completed_count,
            "avg_progress": round(avg_progress, 2)
        }

        # 返回问题 ID 列表
        data["problems"] = [problem.id for problem in problems_dict.values()]
        
        return self.success(data)
