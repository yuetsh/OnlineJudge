import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta
from django.core.cache import cache
from django.db.models import Count, Min
from django.db.models.functions import TruncDate
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from account.decorators import login_required, teacher_admin_required
from account.models import User
from ai.models import AIAnalysis
from ai.serializers import AIAnalysisDetailSerializer
from flowchart.models import FlowchartSubmission, FlowchartSubmissionStatus
from problem.models import Problem
from submission.models import JudgeStatus, Submission
from utils.api import APIView
from utils.openai import get_ai_client, get_async_ai_client
from utils.shortcuts import datetime2str

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

# 等级权重映射（用于加权平均计算）
GRADE_WEIGHTS = {"S": 4, "A": 3, "B": 2, "C": 1}

# 平均等级阈值：(最小权重, 等级)
AVERAGE_GRADE_THRESHOLDS = [(3.5, "S"), (2.5, "A"), (1.5, "B")]


def get_cache_key(prefix, *args):
    return hashlib.md5(f"{prefix}:{'_'.join(map(str, args))}".encode()).hexdigest()


def get_difficulty(difficulty):
    return DIFFICULTY_MAP.get(difficulty, "中等")


def get_grade(rank, submission_count, reference_count=None):
    """
    计算题目完成评级

    评级标准：
    - S级：前10%，卓越水平（10%的人）
    - A级：前35%，优秀水平（25%的人）
    - B级：前75%，良好水平（40%的人）
    - C级：75%之后，及格水平（25%的人）

    特殊规则：
    - 小规模惩罚用 reference_count（全时段人数）判断，避免同期窗口窄导致惩罚误触发
    - reference_count 未传时退化为 submission_count
    """
    if not rank or rank <= 0 or submission_count <= 0:
        return "C"

    percentile = (rank - 1) / submission_count * 100

    base_grade = "C"
    for threshold, grade in GRADE_THRESHOLDS:
        if percentile < threshold:
            base_grade = grade
            break

    penalty_count = reference_count if reference_count is not None else submission_count
    if penalty_count < SMALL_SCALE_PENALTY["threshold"]:
        base_grade = SMALL_SCALE_PENALTY["downgrade"].get(base_grade, base_grade)

    return base_grade


def calculate_average_grade(grades):
    """根据等级列表计算加权平均等级"""
    scores = [GRADE_WEIGHTS[g] for g in grades if g in GRADE_WEIGHTS]
    if not scores:
        return ""
    avg = sum(scores) / len(scores)
    for threshold, grade in AVERAGE_GRADE_THRESHOLDS:
        if avg >= threshold:
            return grade
    return "C"


def find_user_rank(ranking_list, user_id):
    """在排名列表中找到用户的排名（1-based），未找到返回 None"""
    return next(
        (idx + 1 for idx, rec in enumerate(ranking_list) if rec["user_id"] == user_id),
        None,
    )


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
    user_id, start, end, class_user_ids=None, use_class_scope=False, include_all_time=True
):
    # 用户自己的 AC 记录按时间范围过滤
    user_first_ac = list(
        Submission.objects.filter(
            result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED],
            user_id=user_id,
            create_time__gte=start,
            create_time__lte=end,
        )
        .values("problem_id")
        .annotate(first_ac_time=Min("create_time"))
    )
    if not user_first_ac:
        return [], {}, []

    problem_ids = [item["problem_id"] for item in user_first_ac]

    if not include_all_time:
        return user_first_ac, {}, problem_ids

    # 排名基于全局数据（不限时间），后注册的学生与所有人公平竞争
    rank_qs = Submission.objects.filter(
        result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED],
        problem_id__in=problem_ids,
    )
    if use_class_scope and class_user_ids:
        rank_qs = rank_qs.filter(user_id__in=class_user_ids)

    ranked_first_ac = list(
        rank_qs.values("user_id", "problem_id").annotate(first_ac_time=Min("create_time"))
    )

    by_problem = defaultdict(list)
    for item in ranked_first_ac:
        by_problem[item["problem_id"]].append(item)
    for submissions in by_problem.values():
        submissions.sort(key=lambda x: (x["first_ac_time"], x["user_id"]))

    return user_first_ac, by_problem, problem_ids


async def stream_ai_response(client, system_prompt, user_prompt, on_complete=None):
    """SSE 流式响应异步生成器，on_complete(full_text) 在流结束时调用。

    必须是异步生成器：在 ASGI 下，同步生成器会被 Django 的
    StreamingHttpResponse 通过 sync_to_async(list) 一次性消费完才发送，
    导致整段内容生成完毕后才返回，失去流式效果。
    """
    try:
        stream = await client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=True,
            extra_body={"thinking": {"type": "disabled"}},
        )
    except Exception as exc:
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        yield "event: end\n\n"
        return

    yield "event: start\n\n"
    chunks = []
    try:
        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if choice.finish_reason:
                if on_complete:
                    await on_complete("".join(chunks).strip())
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                break
            content = choice.delta.content
            if content:
                chunks.append(content)
                yield f"data: {json.dumps({'type': 'delta', 'content': content})}\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
    finally:
        yield "event: end\n\n"


def make_sse_response(generator):
    """创建 SSE StreamingHttpResponse"""
    response = StreamingHttpResponse(
        streaming_content=generator,
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    # 关闭反向代理（如 nginx）对流式响应的缓冲
    response["X-Accel-Buffering"] = "no"
    return response


class AIDetailDataAPI(APIView):
    @login_required
    def get(self, request):
        start = request.GET.get("start")
        end = request.GET.get("end")
        username = request.GET.get("username")

        if not start or not end:
            return self.error("参数 start 和 end 不能为空")
        if not parse_datetime(start):
            return self.error("start 格式无效，请使用 ISO 8601 格式")
        if not parse_datetime(end):
            return self.error("end 格式无效，请使用 ISO 8601 格式")

        user = request.user
        if username and request.user.is_teacher_or_above():
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                return self.error("User not found")

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

        # 同期排名：只统计时间窗口内解题的人
        by_problem_period = defaultdict(list)
        if problem_ids:
            period_qs = Submission.objects.filter(
                result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED],
                problem_id__in=problem_ids,
                create_time__gte=start,
                create_time__lte=end,
            )
            if use_class_scope and class_user_ids:
                period_qs = period_qs.filter(user_id__in=class_user_ids)
            for item in period_qs.values("user_id", "problem_id").annotate(
                first_ac_time=Min("create_time")
            ):
                by_problem_period[item["problem_id"]].append(item)
            for lst in by_problem_period.values():
                lst.sort(key=lambda x: (x["first_ac_time"], x["user_id"]))

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
                user_first_ac, by_problem, by_problem_period, problems, user.id
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
                    "grade": calculate_average_grade([s["grade"] for s in solved]),
                    "tags": self._calculate_top_tags(problems.values()),
                    "difficulty": self._calculate_difficulty_distribution(
                        problems.values()
                    ),
                    "contest_count": len(set(contest_ids)),
                }
            )

        cache.set(cache_key, result, CACHE_TIMEOUT)
        return self.success(result)

    def _build_solved_records(self, user_first_ac, by_problem, by_problem_period, problems, user_id):
        solved, contest_ids = [], []
        for item in user_first_ac:
            pid = item["problem_id"]
            problem = problems.get(pid)
            if not problem:
                continue

            ranking_list = by_problem.get(pid, [])
            rank = find_user_rank(ranking_list, user_id)

            period_ranking_list = by_problem_period.get(pid, [])
            period_rank = find_user_rank(period_ranking_list, user_id)

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
                    "grade": get_grade(period_rank, len(period_ranking_list), reference_count=len(ranking_list)),
                    "period_rank": period_rank,
                    "period_ac_count": len(period_ranking_list),
                    "difficulty": get_difficulty(problem.difficulty),
                }
            )

        return sorted(solved, key=lambda x: x["ac_time"]), contest_ids

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
        username = request.GET.get("username")

        user = request.user
        if username and request.user.is_teacher_or_above():
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                return self.error("User not found")

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
                user_first_ac, _, problem_ids = get_user_first_ac_submissions(
                    user.id,
                    start.isoformat(),
                    period_end.isoformat(),
                    class_user_ids,
                    use_class_scope,
                    include_all_time=False,
                )
                if user_first_ac:
                    period_data["problem_count"] = len(problem_ids)
                    by_problem_period = defaultdict(list)
                    period_qs = Submission.objects.filter(
                        result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED],
                        problem_id__in=problem_ids,
                        create_time__gte=start,
                        create_time__lte=period_end,
                    )
                    if use_class_scope and class_user_ids:
                        period_qs = period_qs.filter(user_id__in=class_user_ids)
                    for row in period_qs.values("user_id", "problem_id").annotate(
                        first_ac_time=Min("create_time")
                    ):
                        by_problem_period[row["problem_id"]].append(row)
                    for lst in by_problem_period.values():
                        lst.sort(key=lambda x: (x["first_ac_time"], x["user_id"]))
                    grades = [
                        get_grade(
                            find_user_rank(by_problem_period.get(item["problem_id"], []), user.id),
                            len(by_problem_period.get(item["problem_id"], [])),
                        )
                        for item in user_first_ac
                    ]
                    period_data["grade"] = calculate_average_grade(grades)

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



class AILoginSummaryAPI(APIView):
    @login_required
    def get(self, request):
        user = request.user
        end_time = timezone.now()
        start_time = self._resolve_start_time(request, user, end_time)

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
        accepted_count = submissions_qs.filter(result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED]).count()
        solved_count = (
            submissions_qs.filter(result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED])
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
                model="deepseek-v4-flash",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                extra_body={"thinking": {"type": "disabled"}},
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

        client = get_async_ai_client()

        system_prompt = (
            "你是一个风趣的编程老师，学生使用判题狗平台进行编程练习。"
            "请根据学生提供的详细数据和每周数据，给出用户的学习建议，最后写一句鼓励学生的话。"
            "请使用 markdown 格式输出，不要在代码块中输出。"
        )
        user_prompt = f"这段时间内的详细数据: {details}\n(其中部分字段含义是 flowcharts:流程图的提交,solved:代码的提交)\n每周或每月的数据: {duration}"

        user = request.user

        async def on_complete(full_text):
            await AIAnalysis.objects.acreate(
                user=user,
                provider="deepseek",
                model="deepseek-v4-flash",
                data={"details": details, "duration": duration},
                system_prompt=system_prompt,
                user_prompt="这段时间内的详细数据，每周或每月的数据。",
                analysis=full_text,
            )

        return make_sse_response(
            stream_ai_response(client, system_prompt, user_prompt, on_complete)
        )


class ClassPKAnalysisAPI(APIView):
    @teacher_admin_required
    def post(self, request):
        comparisons = request.data.get("comparisons")
        time_range_label = request.data.get("time_range_label", "全部时间")

        if not comparisons or len(comparisons) < 2:
            return self.error("至少需要2个班级的数据")

        client = get_async_ai_client()

        system_prompt = (
            "你是一位经验丰富的编程教育数据分析专家，专注于职业院校计算机编程教学效果评估。"
            "请根据在线评测系统（OJ）提供的班级对比数据，给出深入、专业的分析报告。"
            "请使用 markdown 格式输出，不要在代码块中输出。"
        )
        user_prompt = self._build_prompt(comparisons, time_range_label)

        return make_sse_response(stream_ai_response(client, system_prompt, user_prompt))

    def _build_prompt(self, comparisons, time_range_label):
        def fmt_class(name):
            return f"{name[:2]}计算机{name[2:]}班"

        lines = [
            f"时间范围：{time_range_label}",
            "",
            "## 指标说明",
            "- 总AC数：班级累计通过的题目总数",
            '- 平均AC / 中位数AC：平均受尖子生影响，中位数反映"典型学生"的真实水平',
            "- 前10%/中间80%/后10%均值：梯队分层，判断是尖子班还是均衡班",
            "- 优秀率 / 及格率：达到优秀线、及格线的学生比例",
            "- 参与度：有过任意提交的学生比例（反映主动性）",
            "- AC率：提交通过率（反映代码编写质量）",
            "- 综合分：综合多项指标计算的总评分（满分100）",
            "",
            "## 班级数据",
        ]

        for i, c in enumerate(comparisons):
            class_display = fmt_class(c["class_name"])
            lines.append(f"\n### 第{i + 1}名：{class_display}（综合分 {c['composite_score']:.1f}）")
            lines.append(f"- 人数：{c['user_count']}")
            lines.append(
                f"- 总AC数：{c['total_ac']}，总提交数：{c['total_submission']}，AC率：{c['ac_rate']:.1f}%"
            )
            lines.append(
                f"- 平均AC：{c['avg_ac']:.2f}，中位数AC：{c['median_ac']:.2f}"
            )
            lines.append(
                f"- Q1：{c['q1_ac']:.2f}，Q3：{c['q3_ac']:.2f}，"
                f"IQR（四分位距）：{c['iqr']:.2f}，标准差：{c['std_dev']:.2f}"
            )
            lines.append(
                f"- 前10%均值：{c['top_10_avg']:.2f}，中间80%均值：{c['middle_80_avg']:.2f}，"
                f"后10%均值：{c['bottom_10_avg']:.2f}"
            )
            lines.append(
                f"- 优秀率：{c['excellent_rate']:.1f}%，及格率：{c['pass_rate']:.1f}%，"
                f"参与度：{c['active_rate']:.1f}%"
            )

            if c.get("recent_total_ac") is not None:
                lines.append(
                    f"- 时间段内新增：总AC {c['recent_total_ac']}，"
                    f"平均AC {c.get('recent_avg_ac', 0):.2f}，"
                    f"中位数AC {c.get('recent_median_ac', 0):.2f}，"
                    f"前10%平均 {c.get('recent_top_10_avg', 0):.2f}，"
                    f"活跃学生数 {c.get('recent_active_count', 0)}"
                )

        lines += [
            "",
            "## 请从以下7个维度分析，输出中文报告：",
            "",
            "**1. 总体排名**：直接给出排名，说明各班综合分差距大小。",
            "",
            "**2. 参与积极性**：对比参与度和总提交数，谁的班学生更积极主动？",
            "",
            '**3. 典型学生水平**：重点用中位数AC数对比（而非平均值），'
            '分析谁班的"普通学生"更强。若均值明显高于中位数，说明均值被少数强者拉高，需指出。',
            "",
            '**4. 班级内部均衡性**：结合标准差、IQR、前10%与后10%差距，'
            '判断哪个班是"均衡型"，哪个班是"两极型"。',
            "",
            "**5. 梯队深度对比**：对比各班前10%均值（尖子生天花板）和后10%均值（薄弱学生水平），"
            "分析各班在培养尖子生和帮扶后进生上的差异。",
            "",
            '**6. 代码提交质量**：对比AC率，是否有班级存在"凑提交次数但不思考"的问题？',
            "",
            "**7. 综合结论与建议**：用1句话明确说明胜负；"
            "对落后班级给出2~3条具体可操作的改进建议；点出领先班级1条值得借鉴的做法。",
            "",
            "分析对象是班级任课教师，语言专业但不过分学术。",
        ]

        return "\n".join(lines)


class SingleClassAnalysisAPI(APIView):
    @login_required
    def post(self, request):
        comparison = request.data.get("comparison")
        if not comparison:
            return self.error("缺少班级数据")

        client = get_async_ai_client()

        class_name = comparison.get("class_name", "")
        class_display = f"{class_name[:2]}计算机{class_name[2:]}班"

        system_prompt = (
            "你是一位经验丰富的编程教育数据分析专家，专注于职业院校计算机编程教学效果评估。"
            "请根据在线评测系统（OJ）提供的班级数据，给出深入、专业的分析报告。"
            "请使用 markdown 格式输出，不要在代码块中输出。"
        )

        lines = [
            f"## 班级：{class_display}",
            "",
            "## 指标说明",
            "- 总AC数：班级累计通过的题目总数",
            '- 平均AC / 中位数AC：平均受尖子生影响，中位数反映"典型学生"的真实水平',
            "- 前10%/中间80%/后10%均值：梯队分层",
            "- 优秀率 / 及格率：分别基于班级内部Q3/Q1阈值统计",
            "- 参与度：有过任意提交的学生比例",
            "- AC率：提交通过率",
            "- 综合分：综合多项指标计算的总评分（满分100）",
            "",
            "## 班级数据",
            f"- 人数：{comparison['user_count']}",
            f"- 总AC数：{comparison['total_ac']}，总提交数：{comparison['total_submission']}，AC率：{comparison['ac_rate']:.1f}%",
            f"- 平均AC：{comparison['avg_ac']:.2f}，中位数AC：{comparison['median_ac']:.2f}",
            f"- Q1：{comparison['q1_ac']:.2f}，Q3：{comparison['q3_ac']:.2f}，IQR：{comparison['iqr']:.2f}，标准差：{comparison['std_dev']:.2f}",
            f"- 前10%均值：{comparison['top_10_avg']:.2f}，中间80%均值：{comparison['middle_80_avg']:.2f}，后10%均值：{comparison['bottom_10_avg']:.2f}",
            f"- 优秀率：{comparison['excellent_rate']:.1f}%，及格率：{comparison['pass_rate']:.1f}%，参与度：{comparison['active_rate']:.1f}%",
            f"- 综合分：{comparison['composite_score']:.1f}",
            "",
            "## 请从以下5个维度分析，输出中文报告：",
            "",
            "**1. 整体水平**：基于总AC数、均值与中位数，评价班级的整体编程水平。若均值明显高于中位数，需指出被少数强者拉高的情况。",
            "",
            "**2. 参与积极性**：结合参与度和AC率，评价学生的学习主动性和代码质量。",
            "",
            '**3. 班级内部均衡性**：结合标准差、IQR、前10%与后10%差距，判断是"均衡型"还是"两极型"班级。',
            "",
            "**4. 梯队分析**：分析前10%（尖子生）、中间80%（中坚力量）、后10%（需帮扶学生）的水平差异，给出针对性建议。",
            "",
            "**5. 改进建议**：结合优秀率、及格率等数据，给出3条具体可操作的教学改进建议。最后用一句话鼓励这个班级。",
            "",
            "分析对象是班级任课教师，语言专业但不过分学术。",
        ]

        user_prompt = "\n".join(lines)

        return make_sse_response(stream_ai_response(client, system_prompt, user_prompt))


class AIPinnedReportAPI(APIView):
    @login_required
    def get(self, request):
        try:
            report = AIAnalysis.objects.get(user=request.user, is_pinned=True)
        except AIAnalysis.DoesNotExist:
            return self.success(None)
        return self.success(AIAnalysisDetailSerializer(report).data)


class AIHintAPI(APIView):
    @login_required
    def post(self, request):
        submission_id = request.data.get("submission_id")
        if not submission_id:
            return self.error("submission_id is required")

        try:
            submission = Submission.objects.get(id=submission_id, user_id=request.user.id)
        except Submission.DoesNotExist:
            return self.error("Submission not found")

        problem = submission.problem
        client = get_async_ai_client()

        # 获取参考答案（同语言优先，否则取第一个）
        answers = problem.answers or []
        ref_answer = next(
            (a["code"] for a in answers if a["language"] == submission.language),
            answers[0]["code"] if answers else "",
        )

        system_prompt = (
            "你是编程助教。你知道题目的参考答案，请按照以下规则给学生提示：\n\n"
            "【核心规则】\n"
            "- 【绝对禁止】直接给出答案或核心算法代码，也不能暗示完整解法。\n"
            "- 提示要循序渐进：先指出问题所在的方向，再给出一个小的思考点，让学生自己推导。\n"
            "- 对照参考答案分析学生代码，找出最关键的一个问题重点提示，不要一次列出所有问题。\n\n"
            "【输入处理例外】\n"
            "- 如果学生的代码在【读取输入】部分有错误（例如：输入格式解析错误、"
            "未正确读取多组输入、split/scanf 使用有误等），"
            "则【直接给出正确的输入读取代码片段】，并解释为什么这样写。"
            "输入处理不属于算法核心，可以直接告诉学生。\n\n"
            "【回复格式】\n"
            "语气鼓励，使用 Markdown 格式，回复简洁（不超过6句话）。"
        )
        user_prompt = (
            f"题目：{problem.title}\n"
            f"题目描述：{problem.description[:500]}\n"
            f"参考答案（仅供你分析，不可透露给学生）：\n```\n{ref_answer[:2000]}\n```\n"
            f"学生提交语言：{submission.language}\n"
            f"判题结果：{submission.result}\n"
            f"错误信息：{submission.statistic_info.get('err_info', '无')}\n"
            f"学生代码：\n```\n{submission.code[:2000]}\n```"
        )

        return make_sse_response(
            stream_ai_response(client, system_prompt, user_prompt)
        )


class AIHeatmapDataAPI(APIView):
    @login_required
    def get(self, request):
        username = request.GET.get("username")
        user = request.user
        if username and request.user.is_teacher_or_above():
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                return self.error("User not found")
        end = timezone.now()
        today = end.date().isoformat()
        cache_key = get_cache_key("ai_heatmap", user.id, user.class_name or "", today)
        cached_result = cache.get(cache_key)
        if cached_result:
            return self.success(cached_result)
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
