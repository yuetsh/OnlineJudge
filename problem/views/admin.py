import hashlib
import json
import os

# import shutil
import zipfile
from wsgiref.util import FileWrapper

from django.conf import settings
from django.db.models import Count, Q
from django.db.models.functions import ExtractYear
from django.http import StreamingHttpResponse

from account.decorators import ensure_created_by, problem_permission_required, teacher_admin_required
from contest.models import Contest, ContestStatus
from judge.sql_runner import SQLCaseError, build_display
from submission.models import Submission
from utils.api import APIError, APIView, CSRFExemptAPIView, validate_serializer
from utils.openai import get_ai_client
from utils.shortcuts import natural_sort_key, rand_str

from ..models import Problem, ProblemRuleType, ProblemTag
from ..serializers import (
    AddContestProblemSerializer,
    ContestProblemMakePublicSerializer,
    CreateContestProblemSerializer,
    CreateProblemSerializer,
    EditContestProblemSerializer,
    EditProblemSerializer,
    ProblemAdminListSerializer,
    ProblemAdminSerializer,
    SQLTestCasePreviewSerializer,
    TestCaseUploadForm,
)
from ..utils import generate_sql_display


class TestCaseZipProcessor(object):
    def process_zip(self, uploaded_zip_file, dir="", sql=False):
        try:
            zip_file = zipfile.ZipFile(uploaded_zip_file, "r")
        except zipfile.BadZipFile:
            raise APIError("Bad zip file")
        name_list = zip_file.namelist()
        if sql:
            test_case_list = self.filter_sql_name_list(name_list, dir=dir)
        else:
            test_case_list = self.filter_name_list(name_list, dir=dir)
        if not test_case_list:
            raise APIError("Empty file")

        test_case_id = rand_str()
        test_case_dir = os.path.join(settings.TEST_CASE_DIR, test_case_id)
        os.mkdir(test_case_dir)
        os.chmod(test_case_dir, 0o710)

        size_cache = {}
        md5_cache = {}

        for item in test_case_list:
            with open(os.path.join(test_case_dir, item), "wb") as f:
                content = zip_file.read(f"{dir}{item}").replace(b"\r\n", b"\n")
                size_cache[item] = len(content)
                if item.endswith(".out"):
                    md5_cache[item] = hashlib.md5(content.rstrip()).hexdigest()
                f.write(content)
        test_case_info = {"test_cases": {}}

        info = []

        if sql:
            # SQL 题：每个 N.sql 是一个测试点的建表+数据脚本，没有期望输出（判题时跑标准答案生成）。
            # output_name 复用同名、md5 置空，以兼容 CreateTestCaseScoreSerializer 和前端测试点表格。
            test_case_info["sql"] = True
            for index, item in enumerate(test_case_list):
                data = {
                    "stripped_output_md5": "",
                    "input_size": size_cache[item],
                    "output_size": 0,
                    "input_name": item,
                    "output_name": item,
                }
                info.append(data)
                test_case_info["test_cases"][str(index + 1)] = data
        else:
            # ["1.in", "1.out", "2.in", "2.out"] => [("1.in", "1.out"), ("2.in", "2.out")]
            test_case_list = zip(*[test_case_list[i::2] for i in range(2)])
            for index, item in enumerate(test_case_list):
                data = {
                    "stripped_output_md5": md5_cache[item[1]],
                    "input_size": size_cache[item[0]],
                    "output_size": size_cache[item[1]],
                    "input_name": item[0],
                    "output_name": item[1],
                }
                info.append(data)
                test_case_info["test_cases"][str(index + 1)] = data

        with open(os.path.join(test_case_dir, "info"), "w", encoding="utf-8") as f:
            f.write(json.dumps(test_case_info, indent=4))

        for item in os.listdir(test_case_dir):
            os.chmod(os.path.join(test_case_dir, item), 0o640)

        return info, test_case_id

    def filter_name_list(self, name_list, dir=""):
        ret = []
        prefix = 1
        while True:
            in_name = f"{prefix}.in"
            out_name = f"{prefix}.out"
            if f"{dir}{in_name}" in name_list and f"{dir}{out_name}" in name_list:
                ret.append(in_name)
                ret.append(out_name)
                prefix += 1
                continue
            else:
                return sorted(ret, key=natural_sort_key)

    def filter_sql_name_list(self, name_list, dir=""):
        # SQL 题测试点：连续编号的 1.sql, 2.sql, ...
        ret = []
        prefix = 1
        while True:
            name = f"{prefix}.sql"
            if f"{dir}{name}" in name_list:
                ret.append(name)
                prefix += 1
                continue
            else:
                return sorted(ret, key=natural_sort_key)


class TestCaseAPI(CSRFExemptAPIView, TestCaseZipProcessor):
    request_parsers = ()

    def get(self, request):
        problem_id = request.GET.get("problem_id")
        if not problem_id:
            return self.error("Parameter error, problem_id is required")
        try:
            problem = Problem.objects.get(id=problem_id)
        except Problem.DoesNotExist:
            return self.error("Problem does not exists")

        if problem.contest:
            ensure_created_by(problem.contest, request.user)
        else:
            ensure_created_by(problem, request.user)

        test_case_dir = os.path.join(settings.TEST_CASE_DIR, problem.test_case_id)
        if not os.path.isdir(test_case_dir):
            return self.error("Test case does not exists")
        # SQL 题的测试点是 N.sql，需按 info 里的类型标记选择文件列表
        is_sql = False
        info_path = os.path.join(test_case_dir, "info")
        if os.path.isfile(info_path):
            try:
                with open(info_path, encoding="utf-8") as f:
                    is_sql = bool(json.load(f).get("sql"))
            except (OSError, json.JSONDecodeError):
                pass
        if is_sql:
            name_list = self.filter_sql_name_list(os.listdir(test_case_dir))
        else:
            name_list = self.filter_name_list(os.listdir(test_case_dir))
        name_list.append("info")
        file_name = os.path.join(test_case_dir, problem.test_case_id + ".zip")
        with zipfile.ZipFile(file_name, "w") as file:
            for test_case in name_list:
                file.write(f"{test_case_dir}/{test_case}", test_case)
        response = StreamingHttpResponse(FileWrapper(open(file_name, "rb")), content_type="application/octet-stream")

        response["Content-Disposition"] = f"attachment; filename=problem_{problem.id}_test_cases.zip"
        response["Content-Length"] = os.path.getsize(file_name)
        return response

    def post(self, request):
        form = TestCaseUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = form.cleaned_data["file"]
        else:
            return self.error("Upload failed")
        zip_file = f"/tmp/{rand_str()}.zip"
        with open(zip_file, "wb") as f:
            for chunk in file:
                f.write(chunk)
        sql = request.POST.get("sql") in ("1", "true", "True")
        info, test_case_id = self.process_zip(zip_file, sql=sql)
        os.remove(zip_file)
        return self.success({"id": test_case_id, "info": info})


class ProblemBase(APIView):
    def common_checks(self, request):
        data = request.data
        if data["rule_type"] == ProblemRuleType.OI:
            total_score = 0
            for item in data["test_case_score"]:
                if item["score"] <= 0:
                    return "Invalid score"
                else:
                    total_score += item["score"]
            data["total_score"] = total_score
        data["languages"] = list(data["languages"])

        # SQL 题校验：.sql 测试点与 .in/.out 沙箱判题互斥，SQL 必须是唯一语言
        if "SQL" in data["languages"]:
            if data["languages"] != ["SQL"]:
                return "SQL problem cannot be mixed with other languages"
            if not data.get("sql_config"):
                return "SQL problem requires sql_config"
            has_sql_answer = any(item.get("language") == "SQL" and item.get("code", "").strip() for item in (data.get("answers") or []))
            if not has_sql_answer:
                return "SQL problem requires a SQL reference answer"
            return self._build_sql_display(data)
        else:
            # 序列化器已放宽（SQL 题不填这些），非 SQL 题在此保持原有强校验
            if not data["input_description"] or not data["output_description"]:
                return "Input and output description are required"
            if not data["samples"]:
                return "Samples are required"
            # 防脏数据：非 SQL 题不应携带 SQL 配置
            data["sql_config"] = None
            data["sql_display"] = None

    def _build_sql_display(self, data):
        """SQL 题：生成题目页展示数据。返回错误信息字符串，成功返回 None。"""
        display, error = generate_sql_display(data["test_case_id"], data["answers"], data["sql_config"])
        if error:
            return error
        data["sql_display"] = display


class ProblemAPI(ProblemBase):
    @problem_permission_required
    @validate_serializer(CreateProblemSerializer)
    def post(self, request):
        data = request.data
        _id = data["_id"]
        if not _id:
            return self.error("Display ID is required")
        if Problem.objects.filter(_id=_id, contest_id__isnull=True).exists():
            return self.error("Display ID already exists")

        error_info = self.common_checks(request)
        if error_info:
            return self.error(error_info)

        # todo check filename and score info
        tags = data.pop("tags")
        data["created_by"] = request.user
        problem = Problem.objects.create(**data)

        for item in tags:
            try:
                tag = ProblemTag.objects.get(name=item)
            except ProblemTag.DoesNotExist:
                tag = ProblemTag.objects.create(name=item)
            problem.tags.add(tag)
        return self.success(ProblemAdminSerializer(problem).data)

    @problem_permission_required
    def get(self, request):
        problem_id = request.GET.get("id")
        user = request.user
        if problem_id:
            try:
                problem = Problem.objects.get(id=problem_id)
                ensure_created_by(problem, request.user)
                return self.success(ProblemAdminSerializer(problem).data)
            except Problem.DoesNotExist:
                return self.error("Problem does not exist")

        problems = Problem.objects.filter(contest_id__isnull=True).order_by("-create_time")

        author = request.GET.get("author", "")
        if author:
            problems = problems.filter(created_by__username=author)

        keyword = request.GET.get("keyword", "").strip()
        if keyword:
            problems = problems.filter(Q(title__icontains=keyword) | Q(_id__icontains=keyword))
        if not user.can_mgmt_all_problem():
            problems = problems.filter(created_by=user)
        return self.success(self.paginate_data(request, problems, ProblemAdminListSerializer))

    @problem_permission_required
    @validate_serializer(EditProblemSerializer)
    def put(self, request):
        data = request.data
        problem_id = data.pop("id")

        try:
            problem = Problem.objects.get(id=problem_id)
            ensure_created_by(problem, request.user)
        except Problem.DoesNotExist:
            return self.error("Problem does not exist")

        _id = data["_id"]
        if not _id:
            return self.error("Display ID is required")
        if Problem.objects.exclude(id=problem_id).filter(_id=_id, contest_id__isnull=True).exists():
            return self.error("Display ID already exists")

        error_info = self.common_checks(request)
        if error_info:
            return self.error(error_info)
        # todo check filename and score info
        tags = data.pop("tags")
        data["languages"] = list(data["languages"])

        for k, v in data.items():
            setattr(problem, k, v)
        problem.save()

        problem.tags.remove(*problem.tags.all())
        for tag in tags:
            try:
                tag = ProblemTag.objects.get(name=tag)
            except ProblemTag.DoesNotExist:
                tag = ProblemTag.objects.create(name=tag)
            problem.tags.add(tag)

        return self.success()

    @problem_permission_required
    def delete(self, request):
        id = request.GET.get("id")
        if not id:
            return self.error("Invalid parameter, id is required")
        try:
            problem = Problem.objects.get(id=id, contest_id__isnull=True)
        except Problem.DoesNotExist:
            return self.error("Problem does not exists")
        ensure_created_by(problem, request.user)
        # d = os.path.join(settings.TEST_CASE_DIR, problem.test_case_id)
        # if os.path.isdir(d):
        #     shutil.rmtree(d, ignore_errors=True)
        problem.delete()
        return self.success()


class ContestProblemAPI(ProblemBase):
    @validate_serializer(CreateContestProblemSerializer)
    def post(self, request):
        data = request.data
        try:
            contest = Contest.objects.get(id=data.pop("contest_id"))
            ensure_created_by(contest, request.user)
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")

        _id = data["_id"]
        if not _id:
            return self.error("Display ID is required")

        if Problem.objects.filter(_id=_id, contest=contest).exists():
            return self.error("Duplicate Display id")

        error_info = self.common_checks(request)
        if error_info:
            return self.error(error_info)

        # todo check filename and score info
        data["contest"] = contest
        tags = data.pop("tags")
        data["created_by"] = request.user
        problem = Problem.objects.create(**data)

        for item in tags:
            try:
                tag = ProblemTag.objects.get(name=item)
            except ProblemTag.DoesNotExist:
                tag = ProblemTag.objects.create(name=item)
            problem.tags.add(tag)
        return self.success(ProblemAdminSerializer(problem).data)

    def get(self, request):
        problem_id = request.GET.get("id")
        contest_id = request.GET.get("contest_id")
        user = request.user
        if problem_id:
            try:
                problem = Problem.objects.get(id=problem_id)
                ensure_created_by(problem.contest, user)
            except Problem.DoesNotExist:
                return self.error("Problem does not exist")
            return self.success(ProblemAdminSerializer(problem).data)

        if not contest_id:
            return self.error("Contest id is required")
        try:
            contest = Contest.objects.get(id=contest_id)
            ensure_created_by(contest, user)
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")
        problems = Problem.objects.filter(contest=contest).order_by("-create_time")
        if not user.is_super_admin():
            problems = problems.filter(contest__created_by=user)
        keyword = request.GET.get("keyword")
        if keyword:
            problems = problems.filter(title__contains=keyword)
        return self.success(self.paginate_data(request, problems, ProblemAdminListSerializer))

    @validate_serializer(EditContestProblemSerializer)
    def put(self, request):
        data = request.data
        user = request.user

        try:
            contest = Contest.objects.get(id=data.pop("contest_id"))
            ensure_created_by(contest, user)
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")

        problem_id = data.pop("id")

        try:
            problem = Problem.objects.get(id=problem_id, contest=contest)
        except Problem.DoesNotExist:
            return self.error("Problem does not exist")

        _id = data["_id"]
        if not _id:
            return self.error("Display ID is required")
        if Problem.objects.exclude(id=problem_id).filter(_id=_id, contest=contest).exists():
            return self.error("Display ID already exists")

        error_info = self.common_checks(request)
        if error_info:
            return self.error(error_info)
        # todo check filename and score info
        tags = data.pop("tags")
        data["languages"] = list(data["languages"])

        for k, v in data.items():
            setattr(problem, k, v)
        problem.save()

        problem.tags.remove(*problem.tags.all())
        for tag in tags:
            try:
                tag = ProblemTag.objects.get(name=tag)
            except ProblemTag.DoesNotExist:
                tag = ProblemTag.objects.create(name=tag)
            problem.tags.add(tag)
        return self.success()

    def delete(self, request):
        id = request.GET.get("id")
        if not id:
            return self.error("Invalid parameter, id is required")
        try:
            problem = Problem.objects.get(id=id, contest_id__isnull=False)
        except Problem.DoesNotExist:
            return self.error("Problem does not exists")
        ensure_created_by(problem.contest, request.user)
        if Submission.objects.filter(problem=problem).exists():
            return self.error("Can't delete the problem as it has submissions")
        # d = os.path.join(settings.TEST_CASE_DIR, problem.test_case_id)
        # if os.path.isdir(d):
        #    shutil.rmtree(d, ignore_errors=True)
        problem.delete()
        return self.success()


class MakeContestProblemPublicAPIView(APIView):
    @validate_serializer(ContestProblemMakePublicSerializer)
    @problem_permission_required
    def post(self, request):
        data = request.data
        display_id = data.get("display_id")
        if Problem.objects.filter(_id=display_id, contest_id__isnull=True).exists():
            return self.error("Duplicate display ID")

        try:
            problem = Problem.objects.get(id=data["id"])
        except Problem.DoesNotExist:
            return self.error("Problem does not exist")

        if not problem.contest or problem.is_public:
            return self.error("Already be a public problem")
        problem.is_public = True
        problem.save()
        tags = problem.tags.all()
        problem.pk = None
        problem.contest = None
        problem._id = display_id
        problem.visible = False
        problem.submission_number = problem.accepted_number = 0
        problem.statistic_info = {}
        problem.save()
        problem.tags.set(tags)
        return self.success()


class AddContestProblemAPI(APIView):
    @validate_serializer(AddContestProblemSerializer)
    def post(self, request):
        data = request.data
        try:
            contest = Contest.objects.get(id=data["contest_id"])
            problem = Problem.objects.get(id=data["problem_id"])
        except (Contest.DoesNotExist, Problem.DoesNotExist):
            return self.error("Contest or Problem does not exist")

        if contest.status == ContestStatus.CONTEST_ENDED:
            return self.error("Contest has ended")
        if Problem.objects.filter(contest=contest, _id=data["display_id"]).exists():
            return self.error("Duplicate display id in this contest")

        tags = problem.tags.all()
        problem.pk = None
        problem.contest = contest
        problem.is_public = True
        problem.visible = True
        problem._id = request.data["display_id"]
        problem.submission_number = problem.accepted_number = 0
        problem.statistic_info = {}
        problem.save()
        problem.tags.set(tags)
        return self.success()


class ProblemVisibleAPI(APIView):
    @problem_permission_required
    def put(self, request):
        data = request.data
        try:
            problem = Problem.objects.get(id=data["id"])
        except Problem.DoesNotExist:
            self.error("problem does not exists")
        problem.visible = not problem.visible
        problem.save()
        return self.success()


class ProblemFlowchartAIGen(APIView):
    @problem_permission_required
    def post(self, request):
        python_code = request.data.get("python", "")
        client = get_ai_client()
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[
                {
                    "role": "system",
                    "content": """你是一个可以将Python代码转换为mermaid的助手。
                    请将用户提供的Python代码转换为 Mermaid 纯文本。
                    注意括号内的内容用引号包裹，如果本身就有引号，请注意双引号和单引号的问题。
                    请只返回 mermaid 代码，连 ``` 都不需要。""",
                },
                {"role": "user", "content": python_code},
            ],
            temperature=0,
            extra_body={"thinking": {"type": "disabled"}},
        )

        mermaid_code = response.choices[0].message.content
        return self.success({"flowchart": mermaid_code})


class StuckProblemsAPI(APIView):
    @teacher_admin_required
    def get(self, request):
        from submission.models import JudgeStatus

        failed_q = Q(
            result__in=[
                JudgeStatus.WRONG_ANSWER,
                JudgeStatus.COMPILE_ERROR,
                JudgeStatus.RUNTIME_ERROR,
            ]
        )
        rows = (
            Submission.objects.values("problem_id", "problem___id", "problem__title")
            .annotate(
                total=Count("id"),
                accepted=Count("id", filter=Q(result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED])),
                failed=Count("id", filter=failed_q),
                failed_users=Count("user_id", filter=failed_q, distinct=True),
            )
            .filter(failed_users__gt=0)
            .order_by("-failed_users")[:40]
        )
        result = [
            {
                "problem_id": r["problem___id"],
                "problem_title": r["problem__title"],
                "total": r["total"],
                "failed": r["failed"],
                "failed_users": r["failed_users"],
                "ac_rate": round(r["accepted"] / r["total"] * 100, 1) if r["total"] else 0,
            }
            for r in rows
        ]
        return self.success(result)


class TopACTrendAPI(APIView):
    @teacher_admin_required
    def get(self, request):
        import datetime
        from collections import defaultdict

        from submission.models import JudgeStatus

        current_year = datetime.datetime.now().year

        try:
            since_year = int(request.GET.get("since_year", 2023))
            if since_year < 2022 or since_year > current_year:
                since_year = 2023
        except (TypeError, ValueError):
            since_year = 2023

        try:
            until_year = int(request.GET.get("until_year", current_year))
            if until_year < since_year or until_year > current_year:
                until_year = current_year - 1
        except (TypeError, ValueError):
            until_year = current_year - 1

        try:
            min_per_year = int(request.GET.get("min_per_year", 100))
            if min_per_year not in (50, 100, 200):
                min_per_year = 100
        except (TypeError, ValueError):
            min_per_year = 100

        required_years = set(range(since_year, until_year + 1))

        yearly_rows = (
            Submission.objects.filter(
                contest_id__isnull=True,
                create_time__year__gte=since_year,
                create_time__year__lte=until_year,
            )
            .annotate(year=ExtractYear("create_time"))
            .values("problem_id", "problem___id", "problem__title", "year")
            .annotate(
                total=Count("id"),
                accepted=Count("id", filter=Q(result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED])),
            )
            .order_by("problem_id", "year")
        )

        by_problem: dict[int, list] = defaultdict(list)
        problem_meta: dict[int, tuple] = {}
        for r in yearly_rows:
            pid = r["problem_id"]
            if pid not in problem_meta:
                problem_meta[pid] = (r["problem___id"], r["problem__title"])
            by_problem[pid].append(
                {
                    "year": r["year"],
                    "total": r["total"],
                    "accepted": r["accepted"],
                    "ac_rate": round(r["accepted"] / r["total"] * 100, 1) if r["total"] else 0,
                }
            )

        result = []
        for pid, yearly in by_problem.items():
            years_present = {row["year"] for row in yearly}
            if not required_years.issubset(years_present):
                continue
            if not all(row["total"] > min_per_year for row in yearly):
                continue
            result.append(
                {
                    "problem_id": problem_meta[pid][0],
                    "problem_title": problem_meta[pid][1],
                    "yearly": sorted(yearly, key=lambda x: x["year"]),
                }
            )

        return self.success(result)


class SQLTestCasePreviewAPI(APIView):
    @validate_serializer(SQLTestCasePreviewSerializer)
    @problem_permission_required
    def post(self, request):
        data = request.data
        try:
            display = build_display(data["init_sql"], data["ref_sql"], data["mode"])
        except SQLCaseError as e:
            return self.error(e.message)
        return self.success(display)


class SQLTestCaseAIGenAPI(APIView):
    @problem_permission_required
    def post(self, request):
        ref_sql = request.data.get("ref_sql", "")
        mode = request.data.get("mode", "query")
        client = get_ai_client()
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[
                {
                    "role": "system",
                    "content": """你是一个 SQL 出题助手。用户会给你一道 SQL 题的标准答案（查询题的
                    SELECT 语句，或增删改题的 UPDATE/DELETE/INSERT 语句）和题型。
                    请你推断出该标准答案所需要的表结构，生成一份自洽的 SQLite 兼容初始化脚本，
                    包含 CREATE TABLE 和若干条 INSERT 语句，插入的数据要足够让标准答案跑出有意义的结果
                    （比如查询题要有能被筛选出来和被过滤掉的行；增删改题要有能被改动和不受影响的行）。
                    请只返回 SQL 脚本本身，连 ``` 都不需要，不要任何解释文字。""",
                },
                {
                    "role": "user",
                    "content": f"题型：{mode}\n标准答案：\n{ref_sql}",
                },
            ],
            extra_body={"thinking": {"type": "disabled"}},
        )
        sql = response.choices[0].message.content
        return self.success({"sql": sql})


class SQLTestCaseScriptsAPI(APIView, TestCaseZipProcessor):
    @problem_permission_required
    def get(self, request):
        problem_id = request.GET.get("problem_id")
        if not problem_id:
            return self.error("Parameter error, problem_id is required")
        try:
            problem = Problem.objects.get(id=problem_id)
        except Problem.DoesNotExist:
            return self.error("Problem does not exists")

        if problem.contest:
            ensure_created_by(problem.contest, request.user)
        else:
            ensure_created_by(problem, request.user)

        test_case_dir = os.path.join(settings.TEST_CASE_DIR, problem.test_case_id)
        try:
            with open(os.path.join(test_case_dir, "info"), encoding="utf-8") as f:
                info = json.load(f)
        except (OSError, json.JSONDecodeError):
            return self.error("测试点信息读取失败")
        if not info.get("sql"):
            return self.error("该题的测试点不是 SQL 类型")

        scripts = []
        for name in self.filter_sql_name_list(os.listdir(test_case_dir)):
            try:
                with open(os.path.join(test_case_dir, name), encoding="utf-8") as f:
                    scripts.append({"name": name, "content": f.read()})
            except OSError:
                return self.error(f"测试点脚本 {name} 读取失败")
        return self.success(scripts)
