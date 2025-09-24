from collections import defaultdict
from datetime import datetime, timedelta
import hashlib
import json

from dateutil.relativedelta import relativedelta
from django.core.cache import cache
from django.db.models import Min
from django.http import StreamingHttpResponse
from django.utils import timezone
from openai import OpenAI

from utils.api import APIView
from utils.shortcuts import get_env

from account.models import User
from problem.models import Problem
from submission.models import Submission, JudgeStatus
from account.decorators import login_required
from ai.models import AIAnalysis


# 常量定义
CACHE_TIMEOUT = 300  # 5分钟缓存
DIFFICULTY_MAP = {"Low": "简单", "Mid": "中等", "High": "困难"}
DEFAULT_CLASS_SIZE = 45


def get_cache_key(prefix, *args):
    """生成缓存键"""
    key_string = f"{prefix}:{'_'.join(map(str, args))}"
    return hashlib.md5(key_string.encode()).hexdigest()


def get_difficulty(difficulty):
    return DIFFICULTY_MAP.get(difficulty, "中等")


def get_grade(rank, submission_count):
    """
    根据排名和提交人数计算等级
    只有三分之一的人完成，直接给到 S
    """
    if not rank or rank <= 0 or submission_count <= 0:
        return "C"

    if submission_count < DEFAULT_CLASS_SIZE // 3:
        return "S"

    top_percent = round(rank / submission_count * 100)
    if top_percent < 20:
        return "S"
    elif top_percent < 50:
        return "A"
    elif top_percent < 85:
        return "B"
    else:
        return "C"


def get_class_user_ids(user):
    """获取班级用户ID列表"""
    if not user.class_name:
        return []

    cache_key = get_cache_key("class_users", user.class_name)
    user_ids = cache.get(cache_key)

    if user_ids is None:
        user_ids = list(
            User.objects.filter(class_name=user.class_name).values_list("id", flat=True)
        )
        cache.set(cache_key, user_ids, CACHE_TIMEOUT)

    return user_ids


def get_user_first_ac_submissions(
    user_id, start, end, class_user_ids=None, use_class_scope=False
):
    """获取用户首次AC提交记录"""
    base_qs = Submission.objects.filter(
        result=JudgeStatus.ACCEPTED,
        create_time__gte=start,
        create_time__lte=end,
    )

    if use_class_scope and class_user_ids:
        base_qs = base_qs.filter(user_id__in=class_user_ids)

    # 获取用户首次AC
    user_first_ac = list(
        base_qs.filter(user_id=user_id)
        .values("problem_id")
        .annotate(first_ac_time=Min("create_time"))
    )

    if not user_first_ac:
        return [], {}, []

    # 获取相关题目的所有首次AC记录用于排名
    problem_ids = [item["problem_id"] for item in user_first_ac]
    ranked_first_ac = list(
        base_qs.filter(problem_id__in=problem_ids)
        .values("user_id", "problem_id")
        .annotate(first_ac_time=Min("create_time"))
    )

    # 按题目分组并排序
    by_problem = defaultdict(list)
    for item in ranked_first_ac:
        by_problem[item["problem_id"]].append(item)

    for _, arr in by_problem.items():
        arr.sort(key=lambda x: (x["first_ac_time"], x["user_id"]))

    return user_first_ac, by_problem, problem_ids


class AIDetailDataAPI(APIView):
    @login_required
    def get(self, request):
        start = request.GET.get("start")
        end = request.GET.get("end")
        username = request.GET.get("username")

        if username:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                return self.error("User does not exist")
        else:
            user = request.user

        # 检查缓存
        cache_key = get_cache_key(
            "ai_detail", user.id, user.class_name or "", start, end
        )
        cached_result = cache.get(cache_key)
        if cached_result:
            return self.success(cached_result)

        # 获取班级用户ID
        class_user_ids = get_class_user_ids(user)
        use_class_scope = bool(user.class_name) and len(class_user_ids) > 1

        # 获取用户首次AC记录
        user_first_ac, by_problem, problem_ids = get_user_first_ac_submissions(
            user.id, start, end, class_user_ids, use_class_scope
        )

        if not user_first_ac:
            result = {
                "user": user.username,
                "class_name": user.class_name,
                "start": start,
                "end": end,
                "solved": [],
                "grade": "",
                "tags": {},
                "difficulty": {},
                "contest_count": 0,
            }
            cache.set(cache_key, result, CACHE_TIMEOUT)
            return self.success(result)

        # 优化的题目查询 - 一次性获取所有需要的数据
        problems = self._get_problems_with_data(problem_ids)

        # 构建解题记录
        solved, contest_ids = self._build_solved_records(
            user_first_ac, by_problem, problems, user.id
        )

        # 计算统计数据
        avg_grade = self._calculate_average_grade(solved)
        tags = self._calculate_top_tags(problems.values())
        difficulty = self._calculate_difficulty_distribution(problems.values())

        result = {
            "user": user.username,
            "class_name": user.class_name,
            "start": start,
            "end": end,
            "solved": solved,
            "grade": avg_grade,
            "tags": tags,
            "difficulty": difficulty,
            "contest_count": len(set(contest_ids)),
        }

        # 缓存结果
        cache.set(cache_key, result, CACHE_TIMEOUT)
        return self.success(result)

    def _get_problems_with_data(self, problem_ids):
        """优化的题目数据获取"""
        problem_qs = (
            Problem.objects.filter(id__in=problem_ids)
            .select_related("contest")
            .prefetch_related("tags")
        )
        return {p.id: p for p in problem_qs}

    def _build_solved_records(self, user_first_ac, by_problem, problems, user_id):
        """构建解题记录"""
        solved = []
        contest_ids = []

        for item in user_first_ac:
            pid = item["problem_id"]
            ranking_list = by_problem.get(pid, [])

            # 查找用户排名
            rank = None
            for idx, rec in enumerate(ranking_list):
                if rec["user_id"] == user_id:
                    rank = idx + 1
                    break

            problem = problems.get(pid)
            if not problem:
                continue

            grade = get_grade(rank, len(ranking_list))

            if problem.contest_id:
                contest_ids.append(problem.contest_id)

            solved.append(
                {
                    "problem": {
                        "display_id": problem._id,
                        "title": problem.title,
                        "contest_id": problem.contest_id,
                        "contest_title": getattr(problem.contest, "title", ""),
                    },
                    "ac_time": timezone.localtime(item["first_ac_time"]).isoformat(),
                    "rank": rank,
                    "ac_count": len(ranking_list),
                    "grade": grade,
                }
            )

        # 按AC时间排序
        solved.sort(key=lambda x: x["ac_time"])
        return solved, contest_ids

    def _calculate_average_grade(self, solved):
        """计算平均等级（出现次数最多的等级）"""
        if not solved:
            return ""

        grade_count = defaultdict(int)
        for s in solved:
            grade_count[s["grade"]] += 1

        return max(grade_count, key=grade_count.get)

    def _calculate_top_tags(self, problems):
        """计算标签TOP5"""
        tags_counter = defaultdict(int)
        for problem in problems:
            for tag in problem.tags.all():
                if tag.name:
                    tags_counter[tag.name] += 1

        top_tags = sorted(tags_counter.items(), key=lambda x: x[1], reverse=True)[:5]
        return {name: count for name, count in top_tags}

    def _calculate_difficulty_distribution(self, problems):
        """计算难度分布"""
        diff_counter = {"Low": 0, "Mid": 0, "High": 0}
        for problem in problems:
            key = problem.difficulty if problem.difficulty in diff_counter else "Mid"
            diff_counter[key] += 1

        diff_sorted = sorted(diff_counter.items(), key=lambda x: x[1], reverse=True)
        return {get_difficulty(k): v for k, v in diff_sorted}


class AIWeeklyDataAPI(APIView):
    @login_required
    def get(self, request):
        end_iso = request.GET.get("end")
        duration = request.GET.get("duration")
        username = request.GET.get("username")

        if username:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                return self.error("User does not exist")
        else:
            user = request.user

        # 检查缓存
        cache_key = get_cache_key(
            "ai_weekly", user.id, user.class_name or "", end_iso, duration
        )
        cached_result = cache.get(cache_key)
        if cached_result:
            return self.success(cached_result)

        # 获取班级用户ID
        class_user_ids = get_class_user_ids(user)
        use_class_scope = bool(user.class_name) and len(class_user_ids) > 1

        # 解析时间参数
        time_config = self._parse_duration(duration)
        start = datetime.fromisoformat(end_iso) - time_config["total_delta"]

        weekly_data = []
        for i in range(time_config["show_count"]):
            start = start + time_config["delta"]
            period_end = start + time_config["delta"]

            period_data = {
                "unit": time_config["show_unit"],
                "index": time_config["show_count"] - 1 - i,
                "start": start.isoformat(),
                "end": period_end.isoformat(),
                "problem_count": 0,
                "submission_count": 0,
                "grade": "",
            }

            # 获取提交数量
            submission_count = Submission.objects.filter(
                user_id=user.id,
                create_time__gte=start,
                create_time__lte=period_end,
            ).count()

            period_data["submission_count"] = submission_count

            if submission_count == 0:
                weekly_data.append(period_data)
                continue

            # 获取AC记录和等级
            user_first_ac, by_problem, problem_ids = get_user_first_ac_submissions(
                user.id,
                start.isoformat(),
                period_end.isoformat(),
                class_user_ids,
                use_class_scope,
            )

            if user_first_ac:
                period_data["problem_count"] = len(problem_ids)
                period_data["grade"] = self._calculate_period_grade(
                    user_first_ac, by_problem, user.id
                )

            weekly_data.append(period_data)

        # 缓存结果
        cache.set(cache_key, weekly_data, CACHE_TIMEOUT)
        return self.success(weekly_data)

    def _parse_duration(self, duration):
        unit, count = duration.split(":")
        count = int(count)

        # 默认配置
        show_count = 4
        show_unit = "weeks"
        total_delta = timedelta(weeks=show_count + 1)
        delta = timedelta(weeks=1)

        if unit == "months" and count == 2:
            # 过去八周
            show_count = 8
            total_delta = timedelta(weeks=9)
        elif unit == "months" and count == 6:
            # 过去六个月
            show_count = 6
            show_unit = "months"
            total_delta = relativedelta(months=7)
            delta = relativedelta(months=1)
        elif unit == "years":
            # 过去一年
            show_count = 12
            show_unit = "months"
            total_delta = relativedelta(months=13)
            delta = relativedelta(months=1)

        return {
            "show_count": show_count,
            "show_unit": show_unit,
            "total_delta": total_delta,
            "delta": delta,
        }

    def _calculate_period_grade(self, user_first_ac, by_problem, user_id):
        """计算周期内的等级"""
        grade_count = defaultdict(int)

        for item in user_first_ac:
            pid = item["problem_id"]
            ranking_list = by_problem.get(pid, [])

            # 查找用户排名
            rank = None
            for idx, rec in enumerate(ranking_list):
                if rec["user_id"] == user_id:
                    rank = idx + 1
                    break

            grade = get_grade(rank, len(ranking_list))
            grade_count[grade] += 1

        return max(grade_count, key=grade_count.get) if grade_count else ""


class AIAnalysisAPI(APIView):
    @login_required
    def post(self, request):
        user = request.user
        details = request.data.get("details")
        weekly = request.data.get("weekly")

        api_key = get_env("AI_KEY")

        if not api_key:
            return self.error("API_KEY is not set")

        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

        system_prompt = "你是一个风趣的编程老师，学生使用判题狗平台进行编程练习。请根据学生提供的详细数据和每周数据，给出用户的学习建议。请使用 markdown 格式输出，不要在代码块中输出。最后不要忘记写一句祝福语。"
        user_prompt = f"这段时间内的详细数据: {details} \n每周或每月的数据: {weekly}"

        analysis_chunks = []
        saved_instance = None
        completed = False

        def save_analysis():
            nonlocal saved_instance
            if analysis_chunks and not saved_instance:
                try:
                    saved_instance = AIAnalysis.objects.create(
                        user=user,
                        provider="deepseek",
                        model="deepseek-chat",
                        data={"details": details, "weekly": weekly},
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        analysis="".join(analysis_chunks).strip(),
                    )
                except Exception:
                    pass

        def stream_generator():
            nonlocal completed
            try:
                stream = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    stream=True,
                )
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
                yield "event: end\n\n"
                return

            yield "event: start\n\n"

            try:
                for chunk in stream:
                    if not chunk.choices:
                        continue

                    choice = chunk.choices[0]
                    if choice.finish_reason:
                        completed = True
                        save_analysis()
                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                        break

                    content = choice.delta.content
                    if content:
                        analysis_chunks.append(content)
                        yield f"data: {json.dumps({'type': 'delta', 'content': content})}\n\n"

            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            finally:
                save_analysis()
                if saved_instance and not completed:
                    try:
                        saved_instance.delete()
                    except Exception:
                        pass
                yield "event: end\n\n"

        response = StreamingHttpResponse(
            streaming_content=stream_generator(),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        return response
