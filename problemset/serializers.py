from utils.api import UsernameSerializer, serializers

from .models import (
    BadgeConditionType,
    ProblemSet,
    ProblemSetBadge,
    ProblemSetDifficulty,
    ProblemSetProblem,
    ProblemSetProgress,
    ProblemSetStatus,
    UserBadge,
)


def get_user_progress_data(problemset, request):
    """获取当前用户在该题单中的进度 - 公共方法"""
    if request and request.user.is_authenticated:
        try:
            progress = ProblemSetProgress.objects.get(problemset=problemset, user=request.user)
            return {
                "is_joined": True,
                "progress_percentage": progress.progress_percentage,
                "completed_count": progress.completed_problems_count,
                "total_count": progress.total_problems_count,
                "is_completed": progress.is_completed,
            }
        except ProblemSetProgress.DoesNotExist:
            return {
                "is_joined": False,
                "progress_percentage": 0,
                "completed_count": 0,
                "total_count": 0,
                "is_completed": False,
            }
    return {
        "is_joined": False,
        "progress_percentage": 0,
        "completed_count": 0,
        "total_count": 0,
        "is_completed": False,
    }


class ProblemSetSerializer(serializers.ModelSerializer):
    """题单序列化器"""

    created_by = UsernameSerializer()
    problems_count = serializers.SerializerMethodField()
    completed_count = serializers.SerializerMethodField()
    user_progress = serializers.SerializerMethodField()

    class Meta:
        model = ProblemSet
        fields = "__all__"

    def get_problems_count(self, obj):
        """获取题单中的题目数量"""
        return ProblemSetProblem.objects.filter(problemset=obj).count()

    def get_completed_count(self, obj):
        """获取当前用户在该题单中完成的题目数量"""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            try:
                progress = ProblemSetProgress.objects.get(problemset=obj, user=request.user)
                return progress.completed_problems_count
            except ProblemSetProgress.DoesNotExist:
                return 0
        return 0

    def get_user_progress(self, obj):
        """获取当前用户在该题单中的进度"""
        request = self.context.get("request")
        return get_user_progress_data(obj, request)


class ProblemSetListSerializer(serializers.ModelSerializer):
    """题单列表序列化器"""

    created_by = UsernameSerializer()
    problems_count = serializers.IntegerField(read_only=True)
    user_progress = serializers.SerializerMethodField()
    badges = serializers.SerializerMethodField()

    class Meta:
        model = ProblemSet
        fields = [
            "id",
            "title",
            "description",
            "created_by",
            "create_time",
            "difficulty",
            "status",
            "end_time",
            "problems_count",
            "user_progress",
            "badges",
            "visible",
        ]

    def get_user_progress(self, obj):
        """获取当前用户在该题单中的进度"""
        request = self.context.get("request")
        if request and hasattr(request, "_user_progress_map"):
            progress = request._user_progress_map.get(obj.id)
            if progress:
                return {
                    "is_joined": True,
                    "progress_percentage": progress.progress_percentage,
                    "completed_count": progress.completed_problems_count,
                    "total_count": progress.total_problems_count,
                    "is_completed": progress.is_completed,
                }
        return {
            "is_joined": False,
            "progress_percentage": 0,
            "completed_count": 0,
            "total_count": 0,
            "is_completed": False,
        }

    def get_badges(self, obj):
        """获取题单的奖章列表，并标记用户已获得的徽章"""
        request = self.context.get("request")

        # 使用预加载的奖章数据
        badges = getattr(obj, "badges", [])
        badge_data = ProblemSetBadgeSerializer(badges, many=True).data

        # 如果用户已登录，检查哪些徽章已被获得
        if request and request.user.is_authenticated and hasattr(request, "_user_earned_badge_ids"):
            earned_badge_ids = request._user_earned_badge_ids
            # 为每个徽章添加是否已获得的标记
            for badge in badge_data:
                badge["is_earned"] = badge["id"] in earned_badge_ids
        else:
            # 未登录用户或未预加载，所有徽章都标记为未获得
            for badge in badge_data:
                badge["is_earned"] = False

        return badge_data


class CreateProblemSetSerializer(serializers.Serializer):
    """创建题单序列化器"""

    title = serializers.CharField(max_length=200)
    description = serializers.CharField()
    difficulty = serializers.ChoiceField(choices=ProblemSetDifficulty.choices, default=ProblemSetDifficulty.EASY)
    status = serializers.ChoiceField(choices=ProblemSetStatus.choices, default=ProblemSetStatus.ACTIVE)
    end_time = serializers.DateTimeField(required=False)


class EditProblemSetSerializer(serializers.Serializer):
    """编辑题单序列化器"""

    id = serializers.IntegerField()
    title = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(required=False)
    difficulty = serializers.ChoiceField(choices=ProblemSetDifficulty.choices, required=False)
    status = serializers.ChoiceField(choices=ProblemSetStatus.choices, required=False)
    visible = serializers.BooleanField(required=False)
    end_time = serializers.DateTimeField(required=False, allow_null=True)


class ProblemSetProblemSerializer(serializers.ModelSerializer):
    """题单题目序列化器"""

    problem = serializers.SerializerMethodField()
    is_completed = serializers.SerializerMethodField()

    class Meta:
        model = ProblemSetProblem
        fields = "__all__"

    def get_problem(self, obj):
        """获取题目详细信息"""
        from problem.serializers import ProblemListSerializer

        return ProblemListSerializer(obj.problem, context=self.context).data

    def get_is_completed(self, obj):
        """获取当前用户是否已完成该题目"""
        request = self.context.get("request")
        if not (request and request.user.is_authenticated):
            return False
        # 优先使用 view 层预取的进度对象，避免 N+1
        progress = self.context.get("user_progress")
        if progress is None:
            try:
                progress = ProblemSetProgress.objects.get(problemset=obj.problemset, user=request.user)
            except ProblemSetProgress.DoesNotExist:
                return False
        return str(obj.problem.id) in progress.progress_detail


class AddProblemToSetSerializer(serializers.Serializer):
    """添加题目到题单序列化器"""

    problem_id = serializers.CharField()
    order = serializers.IntegerField(default=0)
    is_required = serializers.BooleanField(default=True)
    score = serializers.IntegerField(default=0)
    hint = serializers.CharField(required=False, allow_blank=True)


class EditProblemInSetSerializer(serializers.Serializer):
    """编辑题单中的题目序列化器"""

    order = serializers.IntegerField(required=False)
    is_required = serializers.BooleanField(required=False)
    score = serializers.IntegerField(required=False)
    hint = serializers.CharField(required=False, allow_blank=True)


class ProblemSetBadgeSerializer(serializers.ModelSerializer):
    """题单奖章序列化器"""

    class Meta:
        model = ProblemSetBadge
        fields = "__all__"


class CreateProblemSetBadgeSerializer(serializers.Serializer):
    """创建题单奖章序列化器"""

    name = serializers.CharField(max_length=100)
    description = serializers.CharField()
    icon = serializers.CharField()
    condition_type = serializers.ChoiceField(choices=BadgeConditionType.choices)
    condition_value = serializers.IntegerField(required=False)


class EditProblemSetBadgeSerializer(serializers.Serializer):
    """编辑题单奖章序列化器"""

    name = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(required=False)
    icon = serializers.CharField(required=False)
    condition_type = serializers.ChoiceField(choices=BadgeConditionType.choices, required=False)
    condition_value = serializers.IntegerField(required=False)


class ProblemSetProgressSerializer(serializers.ModelSerializer):
    """题单进度序列化器"""

    user = UsernameSerializer()
    completed_problems = serializers.SerializerMethodField()

    class Meta:
        model = ProblemSetProgress
        fields = "__all__"

    def get_completed_problems(self, obj):
        """获取已完成的题目列表"""
        completed_problems = []

        # 尝试从 request 中获取预加载的问题字典（用于批量查询优化）
        problems_dict = {}
        request = self.context.get("request")
        if request and hasattr(request, "_problems_dict_cache"):
            problems_dict = request._problems_dict_cache

        if obj.progress_detail:
            for problem_id in obj.progress_detail.keys():
                # 优先使用预加载的问题字典
                if problems_dict:
                    problem = problems_dict.get(problem_id)
                    if problem:
                        completed_problems.append({"id": problem.id, "_id": problem._id, "title": problem.title})
                    continue

                # 如果没有预加载字典，则回退到单独查询（向后兼容）
                from problem.models import Problem

                try:
                    problem = Problem.objects.get(id=problem_id)
                    completed_problems.append({"id": problem.id, "_id": problem._id, "title": problem.title})
                except Problem.DoesNotExist:
                    continue

        return completed_problems


class UserBadgeSerializer(serializers.ModelSerializer):
    """用户奖章序列化器"""

    badge = ProblemSetBadgeSerializer()

    class Meta:
        model = UserBadge
        fields = "__all__"


class JoinProblemSetSerializer(serializers.Serializer):
    """加入题单序列化器"""

    problemset_id = serializers.IntegerField()


class UpdateProgressSerializer(serializers.Serializer):
    """更新进度序列化器"""

    problemset_id = serializers.IntegerField()
    problem_id = serializers.IntegerField()
    submission_id = serializers.CharField()


class ProblemSetVisibleSerializer(serializers.Serializer):
    """切换题单可见性序列化器"""

    id = serializers.IntegerField()


class ProblemSetUpdateStatusSerializer(serializers.Serializer):
    """更新题单状态序列化器"""

    id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=ProblemSetStatus.choices)
