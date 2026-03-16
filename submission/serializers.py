from django.db import models
from django.utils import timezone

from .models import Submission
from utils.api import serializers
from utils.serializers import LanguageNameChoiceField
from problemset.models import ProblemSetProgress


class CreateSubmissionSerializer(serializers.Serializer):
    problem_id = serializers.IntegerField()
    language = LanguageNameChoiceField()
    code = serializers.CharField(max_length=1024 * 1024)
    contest_id = serializers.IntegerField(required=False)
    problemset_id = serializers.IntegerField(required=False)
    captcha = serializers.CharField(required=False)


class ShareSubmissionSerializer(serializers.Serializer):
    id = serializers.CharField()
    shared = serializers.BooleanField()


class SubmissionModelSerializer(serializers.ModelSerializer):

    class Meta:
        model = Submission
        fields = "__all__"


# 不显示submission info的serializer, 用于ACM rule_type
class SubmissionSafeModelSerializer(serializers.ModelSerializer):
    problem = serializers.SlugRelatedField(read_only=True, slug_field="_id")

    class Meta:
        model = Submission
        exclude = ("info", "contest", "ip")


class SubmissionListSerializer(serializers.ModelSerializer):
    problem = serializers.SlugRelatedField(read_only=True, slug_field="_id")
    problem_title = serializers.CharField(source="problem.title")
    show_link = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = Submission
        exclude = ("info", "contest", "code", "ip")

    def get_show_link(self, obj):
        # 没传user或为匿名user
        if self.user is None or not self.user.is_authenticated:
            return False
        if not obj.check_user_permission(self.user):
            return False
        # 题单防作弊：用户加入了包含该题目的 active 题单时，隐藏加入前的提交链接
        # 如果该题目已在题单中做出来了，则恢复显示
        if obj.user_id == self.user.id and self.user.is_regular_user():
            progress = self._get_problemset_progress(obj.problem_id)
            if (
                progress
                and obj.create_time < progress.join_time
                and str(obj.problem_id) not in progress.progress_detail
            ):
                return False
        return True

    def _get_problemset_progress(self, problem_id):
        """查询用户是否加入了包含该题目的 active 题单，带缓存避免 N+1"""
        if not hasattr(self, "_problemset_progress_cache"):
            self._problemset_progress_cache = {}
        if problem_id not in self._problemset_progress_cache:
            self._problemset_progress_cache[problem_id] = (
                ProblemSetProgress.objects.filter(
                    user=self.user,
                    problemset__status="active",
                    problemset__problemsetproblem__problem_id=problem_id,
                )
                .filter(
                    models.Q(problemset__end_time__isnull=True)
                    | models.Q(problemset__end_time__gt=timezone.now())
                )
                .only("join_time", "progress_detail")
                .first()
            )
        return self._problemset_progress_cache[problem_id]
