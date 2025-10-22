
from django.db.models import Q
from django.utils import timezone

from utils.api import APIView, validate_serializer

from problemset.models import (
    ProblemSet,
    ProblemSetProblem,
    ProblemSetBadge,
    ProblemSetProgress,
    UserBadge,
)
from problemset.serializers import (
    ProblemSetSerializer,
    ProblemSetListSerializer,
    CreateProblemSetSerializer,
    EditProblemSetSerializer,
    ProblemSetProblemSerializer,
    AddProblemToSetSerializer,
    ProblemSetBadgeSerializer,
    CreateProblemSetBadgeSerializer,
    ProblemSetProgressSerializer,
    UserBadgeSerializer,
    JoinProblemSetSerializer,
    UpdateProgressSerializer,
)
from problem.models import Problem


class ProblemSetAPI(APIView):
    """题单API"""

    def get(self, request):
        """获取题单列表"""
        problem_sets = ProblemSet.objects.filter(visible=True)

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

        # 只显示公开的题单，除非是管理员
        if not request.user.is_authenticated or not request.user.is_admin_role():
            problem_sets = problem_sets.filter(is_public=True)

        # 排序
        sort = request.GET.get("sort")
        if sort:
            problem_sets = problem_sets.order_by(sort)
        else:
            problem_sets = problem_sets.order_by("-create_time")

        data = self.paginate_data(request, problem_sets, ProblemSetListSerializer)
        return self.success(data)

    @validate_serializer(CreateProblemSetSerializer)
    def post(self, request):
        """创建题单"""
        data = request.data
        data["created_by"] = request.user
        problem_set = ProblemSet.objects.create(**data)
        return self.success(ProblemSetSerializer(problem_set).data)


class ProblemSetDetailAPI(APIView):
    """题单详情API"""

    def get(self, request, problem_set_id):
        """获取题单详情"""
        try:
            problem_set = ProblemSet.objects.get(id=problem_set_id, visible=True)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        # 检查权限
        if not problem_set.is_public and not (
            request.user.is_authenticated and request.user.is_admin_role()
        ):
            return self.error("无权限访问该题单")

        serializer = ProblemSetSerializer(problem_set, context={"request": request})
        return self.success(serializer.data)

    @validate_serializer(EditProblemSetSerializer)
    def put(self, request, problem_set_id):
        """编辑题单"""
        try:
            problem_set = ProblemSet.objects.get(id=problem_set_id)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        # 检查权限
        if not request.user.is_admin_role() and problem_set.created_by != request.user:
            return self.error("无权限编辑该题单")

        data = request.data
        for key, value in data.items():
            if key != "id":
                setattr(problem_set, key, value)
        problem_set.save()

        return self.success(ProblemSetSerializer(problem_set).data)

    def delete(self, request, problem_set_id):
        """删除题单"""
        try:
            problem_set = ProblemSet.objects.get(id=problem_set_id)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        # 检查权限
        if not request.user.is_admin_role() and problem_set.created_by != request.user:
            return self.error("无权限删除该题单")

        problem_set.visible = False
        problem_set.save()

        return self.success("题单已删除")


class ProblemSetProblemAPI(APIView):
    """题单题目管理API"""

    def get(self, request, problem_set_id):
        """获取题单中的题目列表"""
        try:
            problem_set = ProblemSet.objects.get(id=problem_set_id, visible=True)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        # 检查权限
        if not problem_set.is_public and not (
            request.user.is_authenticated and request.user.is_admin_role()
        ):
            return self.error("无权限访问该题单")

        problems = ProblemSetProblem.objects.filter(problemset=problem_set).order_by(
            "order"
        )
        serializer = ProblemSetProblemSerializer(
            problems, many=True, context={"request": request}
        )
        return self.success(serializer.data)

    @validate_serializer(AddProblemToSetSerializer)
    def post(self, request, problem_set_id):
        """添加题目到题单"""
        try:
            problem_set = ProblemSet.objects.get(id=problem_set_id)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        # 检查权限
        if not request.user.is_admin_role() and problem_set.created_by != request.user:
            return self.error("无权限管理该题单")

        data = request.data
        try:
            problem = Problem.objects.get(id=data["problem_id"])
        except Problem.DoesNotExist:
            return self.error("题目不存在")

        # 检查题目是否已经在题单中
        if ProblemSetProblem.objects.filter(
            problemset=problem_set, problem=problem
        ).exists():
            return self.error("题目已在该题单中")

        ProblemSetProblem.objects.create(
            problemset=problem_set,
            problem=problem,
            order=data.get("order", 0),
            is_required=data.get("is_required", True),
            score=data.get("score", 0),
            hint=data.get("hint", ""),
        )

        return self.success("题目已添加到题单")

    def delete(self, request, problem_set_id, problem_id):
        """从题单中移除题目"""
        try:
            problem_set = ProblemSet.objects.get(id=problem_set_id)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        # 检查权限
        if not request.user.is_admin_role() and problem_set.created_by != request.user:
            return self.error("无权限管理该题单")

        try:
            problem_set_problem = ProblemSetProblem.objects.get(
                problemset=problem_set, problem_id=problem_id
            )
            problem_set_problem.delete()
            return self.success("题目已从题单中移除")
        except ProblemSetProblem.DoesNotExist:
            return self.error("题目不在该题单中")


class ProblemSetProgressAPI(APIView):
    """题单进度API"""

    @validate_serializer(JoinProblemSetSerializer)
    def post(self, request):
        """加入题单"""
        data = request.data
        try:
            problem_set = ProblemSet.objects.get(id=data["problemset_id"], visible=True)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        # 检查权限
        if not problem_set.is_public and not request.user.is_admin_role():
            return self.error("无权限加入该题单")

        # 检查是否已经加入
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
            problem_set = ProblemSet.objects.get(id=problem_set_id, visible=True)
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
            problem_set = ProblemSet.objects.get(id=data["problemset_id"], visible=True)
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
    """题单奖章管理API"""

    def get(self, request, problem_set_id):
        """获取题单的奖章列表"""
        try:
            problem_set = ProblemSet.objects.get(id=problem_set_id, visible=True)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        badges = ProblemSetBadge.objects.filter(problemset=problem_set)
        serializer = ProblemSetBadgeSerializer(badges, many=True)
        return self.success(serializer.data)

    @validate_serializer(CreateProblemSetBadgeSerializer)
    def post(self, request, problem_set_id):
        """创建题单奖章"""
        try:
            problem_set = ProblemSet.objects.get(id=problem_set_id)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        # 检查权限
        if not request.user.is_admin_role() and problem_set.created_by != request.user:
            return self.error("无权限管理该题单")

        data = request.data
        data["problemset"] = problem_set
        badge = ProblemSetBadge.objects.create(**data)

        return self.success(ProblemSetBadgeSerializer(badge).data)
