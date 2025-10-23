from django.db.models import Q

from utils.api import APIView, validate_serializer
from account.decorators import super_admin_required, ensure_created_by

from problemset.models import (
    ProblemSet,
    ProblemSetProblem,
    ProblemSetBadge,
    ProblemSetProgress,
)
from problemset.serializers import (
    ProblemSetSerializer,
    ProblemSetListSerializer,
    CreateProblemSetSerializer,
    EditProblemSetSerializer,
    ProblemSetProblemSerializer,
    AddProblemToSetSerializer,
    EditProblemInSetSerializer,
    ProblemSetBadgeSerializer,
    CreateProblemSetBadgeSerializer,
    EditProblemSetBadgeSerializer,
    ProblemSetProgressSerializer,
)
from problem.models import Problem


class ProblemSetAdminAPI(APIView):
    """题单管理API"""

    @super_admin_required
    def get(self, request):
        """获取题单列表（管理员）"""
        problem_sets = ProblemSet.objects.all().order_by("-create_time")

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

        # 权限过滤：如果不是超级管理员，只能看到自己创建的题单
        if not request.user.is_admin():
            problem_sets = problem_sets.filter(created_by=request.user)

        # 使用统一的分页方法
        data = self.paginate_data(request, problem_sets, ProblemSetListSerializer)
        return self.success(data)

    @super_admin_required
    @validate_serializer(CreateProblemSetSerializer)
    def post(self, request):
        """创建题单"""
        data = request.data
        data["created_by"] = request.user
        problem_set = ProblemSet.objects.create(**data)
        return self.success(ProblemSetSerializer(problem_set).data)

    @super_admin_required
    @validate_serializer(EditProblemSetSerializer)
    def put(self, request):
        """编辑题单"""
        data = request.data
        problem_set_id = data.pop("id")

        try:
            problem_set = ProblemSet.objects.get(id=problem_set_id)
            ensure_created_by(problem_set, request.user)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        # 更新题单信息
        for key, value in data.items():
            if key != "id":
                setattr(problem_set, key, value)
        problem_set.save()

        return self.success(ProblemSetSerializer(problem_set).data)

    @super_admin_required
    def delete(self, request):
        """删除题单"""
        problem_set_id = request.GET.get("id")
        if not problem_set_id:
            return self.error("题单ID是必需的")

        try:
            problem_set = ProblemSet.objects.get(id=problem_set_id)
            ensure_created_by(problem_set, request.user)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        # 软删除：设置为不可见
        problem_set.visible = False
        problem_set.save()

        return self.success("题单已删除")


class ProblemSetDetailAdminAPI(APIView):
    """题单详情管理API"""

    @super_admin_required
    def get(self, request, problem_set_id):
        """获取题单详情（管理员）"""
        try:
            problem_set = ProblemSet.objects.get(id=problem_set_id)
            ensure_created_by(problem_set, request.user)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        serializer = ProblemSetSerializer(problem_set, context={"request": request})
        return self.success(serializer.data)


class ProblemSetProblemAdminAPI(APIView):
    """题单题目管理API（管理员）"""

    @super_admin_required
    def get(self, request, problem_set_id):
        """获取题单中的题目列表（管理员）"""
        try:
            problem_set = ProblemSet.objects.get(id=problem_set_id)
            ensure_created_by(problem_set, request.user)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        problems = ProblemSetProblem.objects.filter(problemset=problem_set).order_by(
            "order"
        )
        serializer = ProblemSetProblemSerializer(
            problems, many=True, context={"request": request}
        )
        return self.success(serializer.data)

    @super_admin_required
    @validate_serializer(AddProblemToSetSerializer)
    def post(self, request, problem_set_id):
        """添加题目到题单（管理员）"""
        try:
            problem_set = ProblemSet.objects.get(id=problem_set_id)
            ensure_created_by(problem_set, request.user)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        data = request.data
        try:
            problem = Problem.objects.filter(
                _id=data["problem_id"],
                visible=True,
                contest_id__isnull=True,
            ).get()
        except Problem.DoesNotExist:
            return self.error("题目不存在或不可见")

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

        # 同步所有用户的进度
        ProblemSetProgress.sync_all_progress_for_problemset(problem_set)

        return self.success("题目已添加到题单")

    @super_admin_required
    @validate_serializer(EditProblemInSetSerializer)
    def put(self, request, problem_set_id, problem_set_problem_id):
        """编辑题单中的题目（管理员）"""
        try:
            problem_set = ProblemSet.objects.get(id=problem_set_id)
            ensure_created_by(problem_set, request.user)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        try:
            problem_set_problem = ProblemSetProblem.objects.get(
                id=problem_set_problem_id, problemset=problem_set
            )
        except ProblemSetProblem.DoesNotExist:
            return self.error("题目不在该题单中")

        data = request.data
        # 更新题目属性
        if "order" in data:
            problem_set_problem.order = data["order"]
        if "is_required" in data:
            problem_set_problem.is_required = data["is_required"]
        if "score" in data:
            problem_set_problem.score = data["score"]
        if "hint" in data:
            problem_set_problem.hint = data["hint"]

        problem_set_problem.save()
        
        # 同步所有用户的进度
        ProblemSetProgress.sync_all_progress_for_problemset(problem_set)
        
        return self.success("题目已更新")

    @super_admin_required
    def delete(self, request, problem_set_id, problem_set_problem_id):
        """从题单中移除题目（管理员）"""
        try:
            problem_set = ProblemSet.objects.get(id=problem_set_id)
            ensure_created_by(problem_set, request.user)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        try:
            problem_set_problem = ProblemSetProblem.objects.get(
                id=problem_set_problem_id, problemset=problem_set
            )
            problem_set_problem.delete()
            
            # 同步所有用户的进度
            ProblemSetProgress.sync_all_progress_for_problemset(problem_set)
            
            return self.success("题目已从题单中移除")
        except ProblemSetProblem.DoesNotExist:
            return self.error("题目不在该题单中")


class ProblemSetBadgeAdminAPI(APIView):
    """题单奖章管理API（管理员）"""

    @super_admin_required
    def get(self, request, problem_set_id):
        """获取题单的奖章列表（管理员）"""
        try:
            problem_set = ProblemSet.objects.get(id=problem_set_id)
            ensure_created_by(problem_set, request.user)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        badges = ProblemSetBadge.objects.filter(problemset=problem_set)
        serializer = ProblemSetBadgeSerializer(badges, many=True)
        return self.success(serializer.data)

    @super_admin_required
    @validate_serializer(CreateProblemSetBadgeSerializer)
    def post(self, request, problem_set_id):
        """创建题单奖章（管理员）"""
        try:
            problem_set = ProblemSet.objects.get(id=problem_set_id)
            ensure_created_by(problem_set, request.user)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        data = request.data
        data["problemset"] = problem_set
        badge = ProblemSetBadge.objects.create(**data)

        return self.success(ProblemSetBadgeSerializer(badge).data)

    @super_admin_required
    @validate_serializer(EditProblemSetBadgeSerializer)
    def put(self, request, problem_set_id, badge_id):
        """编辑题单奖章（管理员）"""
        try:
            problem_set = ProblemSet.objects.get(id=problem_set_id)
            ensure_created_by(problem_set, request.user)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        try:
            badge = ProblemSetBadge.objects.get(id=badge_id, problemset=problem_set)
        except ProblemSetBadge.DoesNotExist:
            return self.error("奖章不存在")

        data = request.data
        
        # 记录是否修改了条件相关的字段
        condition_changed = False
        
        # 更新奖章属性
        if "name" in data:
            badge.name = data["name"]
        if "description" in data:
            badge.description = data["description"]
        if "icon" in data:
            badge.icon = data["icon"]
        if "condition_type" in data:
            badge.condition_type = data["condition_type"]
            condition_changed = True
        if "condition_value" in data:
            badge.condition_value = data["condition_value"]
            condition_changed = True
        if "level" in data:
            badge.level = data["level"]

        badge.save()
        
        # 如果修改了条件，重新计算所有用户的徽章资格
        if condition_changed:
            try:
                badge.recalculate_user_badges()
                return self.success("奖章已更新，并重新计算了所有用户的徽章资格")
            except Exception as e:
                return self.error(f"奖章已更新，但重新计算徽章资格时出错: {str(e)}")
        
        return self.success("奖章已更新")

    @super_admin_required
    def delete(self, request, problem_set_id, badge_id):
        """删除题单奖章（管理员）"""
        try:
            problem_set = ProblemSet.objects.get(id=problem_set_id)
            ensure_created_by(problem_set, request.user)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        try:
            badge = ProblemSetBadge.objects.get(id=badge_id, problemset=problem_set)
            badge.delete()
            return self.success("奖章已删除")
        except ProblemSetBadge.DoesNotExist:
            return self.error("奖章不存在")


class ProblemSetProgressAdminAPI(APIView):
    """题单进度管理API（管理员）"""

    @super_admin_required
    def get(self, request, problem_set_id):
        """获取题单的所有用户进度（管理员）"""
        try:
            problem_set = ProblemSet.objects.get(id=problem_set_id)
            ensure_created_by(problem_set, request.user)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        progress_list = ProblemSetProgress.objects.filter(
            problemset=problem_set
        ).order_by("-join_time")
        serializer = ProblemSetProgressSerializer(progress_list, many=True)
        return self.success(serializer.data)

    @super_admin_required
    def delete(self, request, problem_set_id, user_id):
        """移除用户从题单（管理员）"""
        try:
            problem_set = ProblemSet.objects.get(id=problem_set_id)
            ensure_created_by(problem_set, request.user)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        try:
            progress = ProblemSetProgress.objects.get(
                problemset=problem_set, user_id=user_id
            )
            progress.delete()
            return self.success("用户已从题单中移除")
        except ProblemSetProgress.DoesNotExist:
            return self.error("用户未加入该题单")


class ProblemSetSyncAPI(APIView):
    """题单同步管理API"""
    
    @super_admin_required
    def post(self, request, problem_set_id):
        """手动同步题单的所有用户进度（管理员）"""
        try:
            problem_set = ProblemSet.objects.get(id=problem_set_id)
            ensure_created_by(problem_set, request.user)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")
        
        # 同步所有用户的进度
        synced_count = ProblemSetProgress.sync_all_progress_for_problemset(problem_set)
        
        return self.success(f"已同步 {synced_count} 个用户的进度")


class ProblemSetVisibleAPI(APIView):
    """题单可见性管理API"""

    @super_admin_required
    def put(self, request):
        """切换题单可见性"""
        data = request.data
        try:
            problem_set = ProblemSet.objects.get(id=data["id"])
            ensure_created_by(problem_set, request.user)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        problem_set.visible = not problem_set.visible
        problem_set.save()
        return self.success()


class ProblemSetStatusAPI(APIView):
    """题单状态管理API"""

    @super_admin_required
    def put(self, request):
        """更新题单状态"""
        data = request.data
        try:
            problem_set = ProblemSet.objects.get(id=data["id"])
            ensure_created_by(problem_set, request.user)
        except ProblemSet.DoesNotExist:
            return self.error("题单不存在")

        status = data.get("status")
        if status not in ["active", "archived", "draft"]:
            return self.error("无效的状态")

        problem_set.status = status
        problem_set.save()
        return self.success()
