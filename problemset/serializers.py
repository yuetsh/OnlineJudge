from utils.api import UsernameSerializer, serializers
from .models import (
    ProblemSet,
    ProblemSetProblem,
    ProblemSetBadge,
    ProblemSetProgress,
    UserBadge,
    ProblemSetSubmission,
)


def get_user_progress_data(problemset, request):
    """获取当前用户在该题单中的进度 - 公共方法"""
    if request and request.user.is_authenticated:
        try:
            progress = ProblemSetProgress.objects.get(
                problemset=problemset, user=request.user
            )
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
                progress = ProblemSetProgress.objects.get(
                    problemset=obj, user=request.user
                )
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
    problems_count = serializers.SerializerMethodField()
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
            "problems_count",
            "user_progress",
            "badges",
            "visible",
        ]

    def get_problems_count(self, obj):
        """获取题单中的题目数量"""
        return ProblemSetProblem.objects.filter(problemset=obj).count()

    def get_user_progress(self, obj):
        """获取当前用户在该题单中的进度"""
        request = self.context.get("request")
        return get_user_progress_data(obj, request)

    def get_badges(self, obj):
        """获取题单的奖章列表"""
        badges = ProblemSetBadge.objects.filter(problemset=obj)
        return ProblemSetBadgeSerializer(badges, many=True).data


class CreateProblemSetSerializer(serializers.Serializer):
    """创建题单序列化器"""

    title = serializers.CharField(max_length=200)
    description = serializers.CharField()
    difficulty = serializers.CharField(default="Easy")
    status = serializers.CharField(default="active")


class EditProblemSetSerializer(serializers.Serializer):
    """编辑题单序列化器"""

    id = serializers.IntegerField()
    title = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(required=False)
    difficulty = serializers.CharField(required=False)
    status = serializers.CharField(required=False)
    visible = serializers.BooleanField(required=False)


class ProblemSetProblemSerializer(serializers.ModelSerializer):
    """题单题目序列化器"""

    problem = serializers.SerializerMethodField()

    class Meta:
        model = ProblemSetProblem
        fields = "__all__"

    def get_problem(self, obj):
        """获取题目详细信息"""
        from problem.serializers import ProblemListSerializer

        return ProblemListSerializer(obj.problem, context=self.context).data


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
    condition_type = serializers.CharField()  # all_problems, problem_count, score
    condition_value = serializers.IntegerField(required=False)


class EditProblemSetBadgeSerializer(serializers.Serializer):
    """编辑题单奖章序列化器"""
    name = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(required=False)
    icon = serializers.CharField(required=False)
    condition_type = serializers.CharField(required=False)  # all_problems, problem_count, score
    condition_value = serializers.IntegerField(required=False)


class ProblemSetProgressSerializer(serializers.ModelSerializer):
    """题单进度序列化器"""

    problemset = ProblemSetListSerializer()
    user = UsernameSerializer()

    class Meta:
        model = ProblemSetProgress
        fields = "__all__"


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
    status = serializers.CharField()  # completed, attempted, not_started
    score = serializers.IntegerField(default=0)
    submit_time = serializers.DateTimeField(required=False)


class ProblemSetSubmissionSerializer(serializers.ModelSerializer):
    """题单提交记录序列化器"""
    
    problem_title = serializers.CharField(source="problem.title", read_only=True)
    problem_id = serializers.IntegerField(source="problem.id", read_only=True)
    result_text = serializers.SerializerMethodField()
    
    class Meta:
        model = ProblemSetSubmission
        fields = [
            "id",
            "problem",
            "problem_id", 
            "problem_title",
            "submission",
            "result",
            "result_text",
            "score",
            "language",
            "code_length",
            "execution_time",
            "memory_usage",
            "submit_time",
        ]
    
    def get_result_text(self, obj):
        """获取结果文本"""
        result_map = {
            -2: "编译错误",
            -1: "答案错误", 
            0: "通过",
            1: "时间超限",
            2: "时间超限",
            3: "内存超限",
            4: "运行时错误",
            5: "系统错误",
            6: "等待中",
            7: "评测中",
            8: "部分通过",
        }
        return result_map.get(obj.result, "未知")
