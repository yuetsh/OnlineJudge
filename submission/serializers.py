from django.db import models
from django.db.models import F
from django.utils import timezone

from .models import Submission
from utils.api import serializers
from utils.serializers import LanguageNameChoiceField
from problemset.models import ProblemSetProgress


def bulk_fetch_problemset_progress(user, problem_ids):
    """一次 IN 查询获取该用户对多个题目的题单进度，返回 {problem_id: ProblemSetProgress|None}"""
    if not problem_ids:
        return {}
    rows = (
        ProblemSetProgress.objects.filter(
            user=user,
            problemset__status="active",
            problemset__problemsetproblem__problem_id__in=problem_ids,
        )
        .filter(
            models.Q(problemset__end_time__isnull=True)
            | models.Q(problemset__end_time__gt=timezone.now())
        )
        .annotate(matched_problem_id=F("problemset__problemsetproblem__problem_id"))
        .only("join_time", "progress_detail")
    )
    cache = {}
    for row in rows:
        pid = row.matched_problem_id
        if pid not in cache:
            cache[pid] = row
    for pid in problem_ids:
        cache.setdefault(pid, None)
    return cache


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
        preloaded = kwargs.pop("problemset_progress_cache", None)
        super().__init__(*args, **kwargs)
        if preloaded is not None:
            self._problemset_progress_cache = preloaded

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
