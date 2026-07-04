from django import forms

from utils.api import UsernameSerializer, serializers
from utils.constants import Difficulty
from utils.serializers import (
    LanguageNameChoiceField,
    LanguageNameMultiChoiceField,
)

from .models import Problem, ProblemTag
from .utils import parse_problem_template


class TestCaseUploadForm(forms.Form):
    file = forms.FileField()


class CreateSampleSerializer(serializers.Serializer):
    input = serializers.CharField(trim_whitespace=False)
    output = serializers.CharField(trim_whitespace=False)


class CreateAnswerSerializer(serializers.Serializer):
    language = serializers.CharField()
    code = serializers.CharField()


class CreateTestCaseScoreSerializer(serializers.Serializer):
    input_name = serializers.CharField(max_length=32)
    output_name = serializers.CharField(max_length=32)
    score = serializers.IntegerField(min_value=0)


class CreateProblemCodeTemplateSerializer(serializers.Serializer):
    pass


class SQLConfigSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=["query", "modify"])
    order_sensitive = serializers.BooleanField(default=False)


class SQLTestCasePreviewSerializer(serializers.Serializer):
    init_sql = serializers.CharField(trim_whitespace=False)
    ref_sql = serializers.CharField(trim_whitespace=False)
    mode = serializers.ChoiceField(choices=["query", "modify"])


class CreateOrEditProblemSerializer(serializers.Serializer):
    _id = serializers.CharField(max_length=32, allow_blank=True, allow_null=True)
    title = serializers.CharField(max_length=1024)
    description = serializers.CharField()
    input_description = serializers.CharField(allow_blank=True)
    output_description = serializers.CharField(allow_blank=True)
    samples = serializers.ListField(child=CreateSampleSerializer(), allow_empty=True)
    test_case_id = serializers.RegexField(regex=r"^[a-zA-Z0-9]+$", max_length=32)
    test_case_score = serializers.ListField(child=CreateTestCaseScoreSerializer(), allow_empty=True)
    time_limit = serializers.IntegerField(min_value=1, max_value=1000 * 60)
    memory_limit = serializers.IntegerField(min_value=1, max_value=1024)
    languages = LanguageNameMultiChoiceField()
    template = serializers.DictField(child=serializers.CharField(min_length=1))
    visible = serializers.BooleanField()
    difficulty = serializers.ChoiceField(choices=Difficulty.choices)
    tags = serializers.ListField(child=serializers.CharField(max_length=32), allow_empty=False)
    hint = serializers.CharField(allow_blank=True, allow_null=True)
    source = serializers.CharField(max_length=256, allow_blank=True, allow_null=True)
    prompt = serializers.CharField(allow_blank=True, allow_null=True)
    answers = serializers.ListField(
        child=CreateAnswerSerializer(),
        allow_empty=True,
        allow_null=True,
    )
    share_submission = serializers.BooleanField()

    # 流程图相关字段
    allow_flowchart = serializers.BooleanField(required=False, default=False)
    show_flowchart = serializers.BooleanField(required=False, default=False)
    mermaid_code = serializers.CharField(allow_blank=True, allow_null=True, required=False)

    flowchart_hint = serializers.CharField(allow_blank=True, allow_null=True, required=False)

    # AST 规则
    ast_rules = serializers.JSONField(required=False, allow_null=True, default=None)

    # SQL 题配置
    sql_config = SQLConfigSerializer(required=False, allow_null=True, default=None)


class CreateProblemSerializer(CreateOrEditProblemSerializer):
    pass


class EditProblemSerializer(CreateOrEditProblemSerializer):
    id = serializers.IntegerField()


class CreateContestProblemSerializer(CreateOrEditProblemSerializer):
    contest_id = serializers.IntegerField()


class EditContestProblemSerializer(CreateOrEditProblemSerializer):
    id = serializers.IntegerField()
    contest_id = serializers.IntegerField()


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProblemTag
        fields = "__all__"


class BaseProblemSerializer(serializers.ModelSerializer):
    tags = serializers.SlugRelatedField(many=True, slug_field="name", read_only=True)
    created_by = UsernameSerializer()

    def get_public_template(self, obj):
        ret = {}
        for lang, code in obj.template.items():
            ret[lang] = parse_problem_template(code)["template"]
        return ret


class ProblemAdminSerializer(BaseProblemSerializer):
    class Meta:
        model = Problem
        fields = "__all__"


class ProblemAdminListSerializer(BaseProblemSerializer):
    has_ast_rules = serializers.SerializerMethodField()

    def get_has_ast_rules(self, obj):
        return bool(obj.ast_rules)

    class Meta:
        model = Problem
        fields = ["_id", "id", "title", "created_by", "visible", "create_time", "difficulty", "tags", "has_ast_rules", "allow_flowchart", "show_flowchart"]


class ProblemSerializer(BaseProblemSerializer):
    template = serializers.SerializerMethodField("get_public_template")
    mermaid_code = serializers.SerializerMethodField()
    flowchart_data = serializers.SerializerMethodField()

    class Meta:
        model = Problem
        exclude = (
            "test_case_score",
            "test_case_id",
            "visible",
            "is_public",
            "answers",
        )

    def get_mermaid_code(self, obj):
        # 当 allow_flowchart 为 True 时，不返回 mermaid_code
        if obj.allow_flowchart:
            return None
        return obj.mermaid_code

    def get_flowchart_data(self, obj):
        # 当 allow_flowchart 为 True 时，不返回 flowchart_data
        if obj.allow_flowchart:
            return None
        return obj.flowchart_data


class ProblemListSerializer(BaseProblemSerializer):
    has_ast_rules = serializers.SerializerMethodField()

    def get_has_ast_rules(self, obj):
        return bool(obj.ast_rules)

    class Meta:
        model = Problem
        fields = [
            "id",
            "_id",
            "title",
            "submission_number",
            "accepted_number",
            "difficulty",
            "created_by",
            "tags",
            "contest",
            "allow_flowchart",
            "show_flowchart",
            "has_ast_rules",
        ]


class ProblemSafeSerializer(BaseProblemSerializer):
    template = serializers.SerializerMethodField("get_public_template")
    mermaid_code = serializers.SerializerMethodField()
    flowchart_data = serializers.SerializerMethodField()

    class Meta:
        model = Problem
        exclude = (
            "test_case_score",
            "test_case_id",
            "visible",
            "is_public",
            "difficulty",
            "submission_number",
            "accepted_number",
            "statistic_info",
            "answers",
        )

    def get_mermaid_code(self, obj):
        # 当 allow_flowchart 为 True 时，不返回 mermaid_code
        if obj.allow_flowchart:
            return None
        return obj.mermaid_code

    def get_flowchart_data(self, obj):
        # 当 allow_flowchart 为 True 时，不返回 flowchart_data
        if obj.allow_flowchart:
            return None
        return obj.flowchart_data


class ContestProblemMakePublicSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    display_id = serializers.CharField(max_length=32)


class AddContestProblemSerializer(serializers.Serializer):
    contest_id = serializers.IntegerField()
    problem_id = serializers.IntegerField()
    display_id = serializers.CharField()


class TestCaseScoreSerializer(serializers.Serializer):
    score = serializers.IntegerField(min_value=1)
    input_name = serializers.CharField(max_length=32)
    output_name = serializers.CharField(max_length=32)


class TemplateSerializer(serializers.Serializer):
    prepend = serializers.CharField()
    template = serializers.CharField()
    append = serializers.CharField()


class AnswerSerializer(serializers.Serializer):
    code = serializers.CharField()
    language = LanguageNameChoiceField()
