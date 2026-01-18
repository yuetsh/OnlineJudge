from collections import defaultdict
from datetime import datetime, timedelta
import hashlib
import json

from dateutil.relativedelta import relativedelta
from django.core.cache import cache
from django.db.models import Min, Count
from django.db.models.functions import TruncDate
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from utils.api import APIView
from utils.openai import get_ai_client
from utils.shortcuts import datetime2str

from account.models import User
from problem.models import Problem
from submission.models import Submission, JudgeStatus
from flowchart.models import FlowchartSubmission, FlowchartSubmissionStatus
from account.decorators import login_required
from ai.models import AIAnalysis

CACHE_TIMEOUT = 300
DIFFICULTY_MAP = {"Low": "简单", "Mid": "中等", "High": "困难"}
DEFAULT_CLASS_SIZE = 45

# 评级阈值配置：(百分位上限, 评级)
GRADE_THRESHOLDS = [
    (10, "S"),  # 前10%: S级 - 卓越
    (35, "A"),  # 前35%: A级 - 优秀
    (75, "B"),  # 前75%: B级 - 良好
    (100, "C"),  # 其余: C级 - 及格
]

# 小规模参与惩罚配置：(最小人数, 等级降级映射)
SMALL_SCALE_PENALTY = {
    "threshold": 10,
    "downgrade": {"S": "A", "A": "B"},
}


def get_cache_key(prefix, *args):
    return hashlib.md5(f"{prefix}:{'_'.join(map(str, args))}".encode()).hexdigest()


def get_difficulty(difficulty):
    return DIFFICULTY_MAP.get(difficulty, "中等")


def get_grade(rank, submission_count):
    """
    计算题目完成评级

    评级标准：
    - S级：前10%，卓越水平（10%的人）
    - A级：前35%，优秀水平（25%的人）
    - B级：前75%，良好水平（40%的人）
    - C级：75%之后，及格水平（25%的人）

    特殊规则：
    - 参与人数少于10人时，S级降为A级，A级降为B级（避免因人少而评级虚高）

    Args:
        rank: 用户排名（1表示第一名）
        submission_count: 总AC人数

    Returns:
        评级字符串 ("S", "A", "B", "C")
    """
    # 边界检查
    if not rank or rank <= 0 or submission_count <= 0:
        return "C"

    # 计算百分位（0-100），使用 (rank-1) 使第一名的百分位为0
    percentile = (rank - 1) / submission_count * 100

    # 根据百分位确定基础评级
    base_grade = "C"
    for threshold, grade in GRADE_THRESHOLDS:
        if percentile < threshold:
            base_grade = grade
            break

    # 小规模参与惩罚：人数太少时降低评级
    if submission_count < SMALL_SCALE_PENALTY["threshold"]:
        base_grade = SMALL_SCALE_PENALTY["downgrade"].get(base_grade, base_grade)

    return base_grade


def get_class_user_ids(user):
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
    base_qs = Submission.objects.filter(
        result=JudgeStatus.ACCEPTED, create_time__gte=start, create_time__lte=end
    )
    if use_class_scope and class_user_ids:
        base_qs = base_qs.filter(user_id__in=class_user_ids)

    user_first_ac = list(
        base_qs.filter(user_id=user_id)
        .values("problem_id")
        .annotate(first_ac_time=Min("create_time"))
    )
    if not user_first_ac:
        return [], {}, []

    problem_ids = [item["problem_id"] for item in user_first_ac]
    ranked_first_ac = list(
        base_qs.filter(problem_id__in=problem_ids)
        .values("user_id", "problem_id")
        .annotate(first_ac_time=Min("create_time"))
    )

    by_problem = defaultdict(list)
    for item in ranked_first_ac:
        by_problem[item["problem_id"]].append(item)
    for submissions in by_problem.values():
        submissions.sort(key=lambda x: (x["first_ac_time"], x["user_id"]))

    return user_first_ac, by_problem, problem_ids


class AIDetailDataAPI(APIView):
    @login_required
    def get(self, request):
        start = request.GET.get("start")
        end = request.GET.get("end")

        user = request.user

        cache_key = get_cache_key(
            "ai_detail", user.id, user.class_name or "", start, end
        )
        cached_result = cache.get(cache_key)
        if cached_result:
            return self.success(cached_result)

        class_user_ids = get_class_user_ids(user)
        use_class_scope = bool(user.class_name) and len(class_user_ids) > 1
        user_first_ac, by_problem, problem_ids = get_user_first_ac_submissions(
            user.id, start, end, class_user_ids, use_class_scope
        )

        result = {
            "user": user.username,
            "class_name": user.class_name,
            "start": start,
            "end": end,
            "solved": [],
            "flowcharts": [],
            "grade": "",
            "tags": {},
            "difficulty": {},
            "contest_count": 0,
        }

        if user_first_ac:
            problems = {
                p.id: p
                for p in Problem.objects.filter(id__in=problem_ids)
                .select_related("contest")
                .prefetch_related("tags")
            }
            solved, contest_ids = self._build_solved_records(
                user_first_ac, by_problem, problems, user.id
            )
            # 查找 flowchart submissions
            flowcharts_query = FlowchartSubmission.objects.filter(
                user_id=user,
                status=FlowchartSubmissionStatus.COMPLETED,
            )

            # 添加时间范围过滤
            if start:
                flowcharts_query = flowcharts_query.filter(create_time__gte=start)
            if end:
                flowcharts_query = flowcharts_query.filter(create_time__lte=end)

            flowcharts = flowcharts_query.select_related("problem").only(
                "id",
                "create_time",
                "ai_score",
                "ai_grade",
                "problem___id",
                "problem__title",
            )

            # 按problem分组
            problem_groups = defaultdict(list)
            for flowchart in flowcharts:
                problem_id = flowchart.problem._id
                problem_groups[problem_id].append(flowchart)

            flowcharts_data = []
            for problem_id, submissions in problem_groups.items():
                if not submissions:
                    continue

                # 获取第一个提交的基本信息
                first_submission = submissions[0]

                # 计算统计数据
                scores = [s.ai_score for s in submissions if s.ai_score is not None]
                times = [s.create_time for s in submissions]

                # 找到最高分和对应的等级
                best_score = max(scores) if scores else 0
                best_submission = next(
                    (s for s in submissions if s.ai_score == best_score), submissions[0]
                )
                best_grade = best_submission.ai_grade or ""

                # 计算平均分
                avg_score = sum(scores) / len(scores) if scores else 0

                # 最新提交时间
                latest_time = max(times) if times else first_submission.create_time

                merged_item = {
                    "problem__id": problem_id,
                    "problem_title": first_submission.problem.title,
                    "submission_count": len(submissions),
                    "best_score": best_score,
                    "best_grade": best_grade,
                    "latest_submission_time": latest_time.isoformat() if latest_time else None,
                    "avg_score": round(avg_score, 0),
                }

                flowcharts_data.append(merged_item)

            # 按最新提交时间排序
            flowcharts_data.sort(
                key=lambda x: x["latest_submission_time"] or "", reverse=True
            )

            result.update(
                {
                    "solved": solved,
                    "flowcharts": flowcharts_data,
                    "grade": self._calculate_average_grade(solved),
                    "tags": self._calculate_top_tags(problems.values()),
                    "difficulty": self._calculate_difficulty_distribution(
                        problems.values()
                    ),
                    "contest_count": len(set(contest_ids)),
                }
            )

        cache.set(cache_key, result, CACHE_TIMEOUT)
        return self.success(result)

    def _build_solved_records(self, user_first_ac, by_problem, problems, user_id):
        solved, contest_ids = [], []
        for item in user_first_ac:
            pid = item["problem_id"]
            problem = problems.get(pid)
            if not problem:
                continue

            ranking_list = by_problem.get(pid, [])
            rank = next(
                (
                    idx + 1
                    for idx, rec in enumerate(ranking_list)
                    if rec["user_id"] == user_id
                ),
                None,
            )

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
                    "grade": get_grade(rank, len(ranking_list)),
                    "difficulty": get_difficulty(problem.difficulty),
                }
            )

        return sorted(solved, key=lambda x: x["ac_time"]), contest_ids

    def _calculate_average_grade(self, solved):
        """
        计算平均等级，使用加权平均方法

        等级权重：S=4, A=3, B=2, C=1
        计算加权平均后，根据阈值确定最终等级

        Args:
            solved: 已解决的题目列表，每个包含grade字段

        Returns:
            平均等级字符串 ("S", "A", "B", "C")
        """
        if not solved:
            return ""

        # 等级权重映射
        grade_weights = {"S": 4, "A": 3, "B": 2, "C": 1}

        # 计算加权总分
        total_weight = 0
        total_score = 0

        for s in solved:
            grade = s["grade"]
            if grade in grade_weights:
                total_score += grade_weights[grade]
                total_weight += 1

        if total_weight == 0:
            return ""

        # 计算平均权重
        average_weight = total_score / total_weight

        # 根据平均权重确定等级
        # S级: 3.5-4.0, A级: 2.5-3.5, B级: 1.5-2.5, C级: 1.0-1.5
        if average_weight >= 3.5:
            return "S"
        elif average_weight >= 2.5:
            return "A"
        elif average_weight >= 1.5:
            return "B"
        else:
            return "C"

    def _calculate_top_tags(self, problems):
        tags_counter = defaultdict(int)
        for problem in problems:
            for tag in problem.tags.all():
                if tag.name:
                    tags_counter[tag.name] += 1
        return dict(sorted(tags_counter.items(), key=lambda x: x[1], reverse=True)[:5])

    def _calculate_difficulty_distribution(self, problems):
        diff_counter = {"Low": 0, "Mid": 0, "High": 0}
        for problem in problems:
            diff_counter[
                problem.difficulty if problem.difficulty in diff_counter else "Mid"
            ] += 1
        return {
            get_difficulty(k): v
            for k, v in sorted(diff_counter.items(), key=lambda x: x[1], reverse=True)
        }


class AIDurationDataAPI(APIView):
    @login_required
    def get(self, request):
        end_iso = request.GET.get("end")
        duration = request.GET.get("duration")

        user = request.user

        cache_key = get_cache_key(
            "ai_duration", user.id, user.class_name or "", end_iso, duration
        )
        cached_result = cache.get(cache_key)
        if cached_result:
            return self.success(cached_result)

        class_user_ids = get_class_user_ids(user)
        use_class_scope = bool(user.class_name) and len(class_user_ids) > 1
        time_config = self._parse_duration(duration)
        start = datetime.fromisoformat(end_iso) - time_config["total_delta"]

        duration_data = []
        for i in range(time_config["show_count"]):
            start = start + time_config["delta"]
            period_end = start + time_config["delta"]

            submission_count = Submission.objects.filter(
                user_id=user.id, create_time__gte=start, create_time__lte=period_end
            ).count()

            period_data = {
                "unit": time_config["show_unit"],
                "index": time_config["show_count"] - 1 - i,
                "start": start.isoformat(),
                "end": period_end.isoformat(),
                "problem_count": 0,
                "submission_count": submission_count,
                "grade": "",
            }

            if submission_count > 0:
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

            duration_data.append(period_data)

        cache.set(cache_key, duration_data, CACHE_TIMEOUT)
        return self.success(duration_data)

    def _parse_duration(self, duration):
        unit, count = duration.split(":")
        count = int(count)

        configs = {
            ("months", 2): {
                "show_count": 8,
                "show_unit": "weeks",
                "total_delta": timedelta(weeks=9),
                "delta": timedelta(weeks=1),
            },
            ("months", 6): {
                "show_count": 6,
                "show_unit": "months",
                "total_delta": relativedelta(months=7),
                "delta": relativedelta(months=1),
            },
            ("years", 1): {
                "show_count": 12,
                "show_unit": "months",
                "total_delta": relativedelta(months=13),
                "delta": relativedelta(months=1),
            },
        }

        return configs.get(
            (unit, count),
            {
                "show_count": 4,
                "show_unit": "weeks",
                "total_delta": timedelta(weeks=5),
                "delta": timedelta(weeks=1),
            },
        )

    def _calculate_period_grade(self, user_first_ac, by_problem, user_id):
        """
        计算时间段内的平均等级，使用加权平均方法

        等级权重：S=4, A=3, B=2, C=1
        计算加权平均后，根据阈值确定最终等级

        Args:
            user_first_ac: 用户首次AC的提交记录
            by_problem: 按题目分组的排名数据
            user_id: 用户ID

        Returns:
            平均等级字符串 ("S", "A", "B", "C")
        """
        if not user_first_ac:
            return ""

        # 等级权重映射
        grade_weights = {"S": 4, "A": 3, "B": 2, "C": 1}

        # 计算加权总分
        total_weight = 0
        total_score = 0

        for item in user_first_ac:
            ranking_list = by_problem.get(item["problem_id"], [])
            rank = next(
                (
                    idx + 1
                    for idx, rec in enumerate(ranking_list)
                    if rec["user_id"] == user_id
                ),
                None,
            )
            if rank:
                grade = get_grade(rank, len(ranking_list))
                if grade in grade_weights:
                    total_score += grade_weights[grade]
                    total_weight += 1

        if total_weight == 0:
            return ""

        # 计算平均权重
        average_weight = total_score / total_weight

        # 根据平均权重确定等级
        # S级: 3.5-4.0, A级: 2.5-3.5, B级: 1.5-2.5, C级: 1.0-1.5
        if average_weight >= 3.5:
            return "S"
        elif average_weight >= 2.5:
            return "A"
        elif average_weight >= 1.5:
            return "B"
        else:
            return "C"



class AILoginSummaryAPI(APIView):
    @login_required
    def get(self, request):
        user = request.user
        end_time = timezone.now()
        start_time = self._resolve_start_time(request, user, end_time)

        if end_time - start_time < timedelta(days=1):
            summary = {
                "start": datetime2str(start_time),
                "end": datetime2str(end_time),
                "new_problem_count": 0,
                "submission_count": 0,
                "accepted_count": 0,
                "solved_count": 0,
                "flowchart_submission_count": 0,
            }
            return self.success({"summary": summary, "analysis": ""})

        problems_qs = Problem.objects.filter(
            create_time__gte=start_time,
            create_time__lte=end_time,
            contest_id__isnull=True,
            visible=True,
        )
        new_problem_count = problems_qs.count()

        submissions_qs = Submission.objects.filter(
            user_id=user.id, create_time__gte=start_time, create_time__lte=end_time
        )
        submission_count = submissions_qs.count()
        accepted_count = submissions_qs.filter(result=JudgeStatus.ACCEPTED).count()
        solved_count = (
            submissions_qs.filter(result=JudgeStatus.ACCEPTED)
            .values("problem_id")
            .distinct()
            .count()
        )
        flowchart_submission_count = FlowchartSubmission.objects.filter(
            user_id=user.id, create_time__gte=start_time, create_time__lte=end_time
        ).count()

        summary = {
            "start": datetime2str(start_time),
            "end": datetime2str(end_time),
            "new_problem_count": new_problem_count,
            "submission_count": submission_count,
            "accepted_count": accepted_count,
            "solved_count": solved_count,
            "flowchart_submission_count": flowchart_submission_count,
        }

        analysis = ""
        analysis_error = ""
        if submission_count >= 3:
            analysis, analysis_error = self._get_ai_analysis(summary)

        data = {"summary": summary, "analysis": analysis}
        if analysis_error:
            data["analysis_error"] = analysis_error
        return self.success(data)

    def _resolve_start_time(self, request, user, end_time):
        start_raw = request.session.get("prev_login") or request.GET.get("start")
        start_time = parse_datetime(start_raw) if start_raw else None

        if start_time and timezone.is_naive(start_time):
            start_time = timezone.make_aware(
                start_time, timezone.get_current_timezone()
            )

        if not start_time:
            if user.last_login and user.last_login < end_time:
                start_time = user.last_login
            elif user.create_time:
                start_time = user.create_time
            else:
                start_time = end_time - timedelta(days=7)

        if start_time >= end_time:
            start_time = end_time - timedelta(days=1)

        return start_time

    def _get_ai_analysis(self, summary):
        try:
            client = get_ai_client()
        except Exception as exc:
            return "", str(exc)

        system_prompt = (
            "你是 OnlineJudge 的学习助教。"
            "请根据统计数据给出简短分析(1-2句)，再给出一行结论，"
            "结论用“结论：”开头。"
        )
        user_prompt = (
            f"时间范围：{summary['start']} 到 {summary['end']}\n"
            f"新题目数：{summary['new_problem_count']}\n"
            f"提交次数：{summary['submission_count']}\n"
            f"AC 次数：{summary['accepted_count']}\n"
            f"AC 题目数：{summary['solved_count']}\n"
            f"流程图提交数：{summary['flowchart_submission_count']}\n"
        )

        try:
            completion = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception as exc:
            return "", str(exc)

        if not completion.choices:
            return "", ""

        content = completion.choices[0].message.content or ""
        return content.strip(), ""

class AIAnalysisAPI(APIView):
    @login_required
    def post(self, request):
        details = request.data.get("details")
        duration = request.data.get("duration")

        client = get_ai_client()

        system_prompt = "你是一个风趣的编程老师，学生使用判题狗平台进行编程练习。请根据学生提供的详细数据和每周数据，给出用户的学习建议，最后写一句鼓励学生的话。请使用 markdown 格式输出，不要在代码块中输出。"
        user_prompt = f"这段时间内的详细数据: {details}\n(其中部分字段含义是 flowcharts:流程图的提交,solved:代码的提交)\n每周或每月的数据: {duration}"

        analysis_chunks = []
        saved_instance = None
        completed = False

        def save_analysis():
            nonlocal saved_instance
            if analysis_chunks and not saved_instance:
                saved_instance = AIAnalysis.objects.create(
                    user=request.user,
                    provider="deepseek",
                    model="deepseek-chat",
                    data={"details": details, "duration": duration},
                    system_prompt=system_prompt,
                    user_prompt="这段时间内的详细数据，每周或每月的数据。",
                    analysis="".join(analysis_chunks).strip(),
                )

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


class AIHeatmapDataAPI(APIView):
    @login_required
    def get(self, request):
        user = request.user
        cache_key = get_cache_key("ai_heatmap", user.id, user.class_name or "")
        cached_result = cache.get(cache_key)
        if cached_result:
            return self.success(cached_result)

        end = datetime.now()
        start = end - timedelta(days=365)

        # 使用单次查询获取所有数据，按日期分组统计
        submission_counts = (
            Submission.objects.filter(
                user_id=user.id, create_time__gte=start, create_time__lte=end
            )
            .annotate(date=TruncDate("create_time"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        # 将查询结果转换为字典，便于快速查找
        submission_dict = {item["date"]: item["count"] for item in submission_counts}

        # 生成365天的热力图数据
        heatmap_data = []
        current_date = start.date()
        for i in range(365):
            day_date = current_date + timedelta(days=i)
            submission_count = submission_dict.get(day_date, 0)
            heatmap_data.append(
                {
                    "timestamp": int(
                        datetime.combine(day_date, datetime.min.time()).timestamp()
                        * 1000
                    ),
                    "value": submission_count,
                }
            )

        cache.set(cache_key, heatmap_data, CACHE_TIMEOUT)
        return self.success(heatmap_data)
