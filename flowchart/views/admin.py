import re
from collections import Counter

import jieba
from django.db.models import Avg, Count

from account.decorators import teacher_admin_required
from account.models import AdminType, User
from problem.models import Problem
from utils.api import APIView

from ..models import FlowchartSubmission, FlowchartSubmissionStatus

STOPWORDS = frozenset(
    "的 了 是 在 和 有 就 不 也 都 要 会 这 那 到 说 上 为 与 及 等 "
    "把 被 从 而 所 但 如 又 或 很 更 还 让 对 已 向 只 能 以 中 可以 "
    "可能 需要 没有 使用 进行 注意 建议 应该 考虑 "
    "一个 一些 一下 一定 一种 这个 所有 其他 ".split()
)


def get_real_name(username, class_name):
    if class_name and username.startswith("ks"):
        return username[len(f"ks{class_name}"):]
    return username


class FlowchartStatisticsAPI(APIView):
    @teacher_admin_required
    def get(self, request):
        start = request.GET.get("start")
        end = request.GET.get("end")

        if not end:
            return self.error("end is required")

        filters = {
            "status": FlowchartSubmissionStatus.COMPLETED,
            "create_time__lte": end,
        }
        if start:
            filters["create_time__gte"] = start

        submissions = FlowchartSubmission.objects.filter(**filters)

        problem_id = request.GET.get("problem_id")
        if problem_id:
            try:
                problem = Problem.objects.get(
                    _id__iexact=problem_id, contest_id__isnull=True, visible=True
                )
            except Problem.DoesNotExist:
                return self.error("Problem doesn't exist")
            submissions = submissions.filter(problem=problem)

        username = request.GET.get("username")
        all_users_dict = {}
        if username:
            submissions = submissions.filter(user__username__icontains=username)
            all_users_dict = {
                user["username"]: user["class_name"]
                for user in User.objects.filter(
                    username__icontains=username,
                    is_disabled=False,
                    admin_type=AdminType.REGULAR_USER,
                ).values("username", "class_name")
            }

        total_count = submissions.count()
        if total_count == 0:
            return self.success({
                "total_count": 0,
                "avg_score": 0,
                "grade_distribution": {},
                "criteria_averages": {},
                "person_count": len(all_users_dict),
                "completed_count": 0,
                "word_frequencies": [],
                "data_unaccepted": [],
            })

        # 1. Grade distribution
        grade_counts = dict(
            submissions.values_list("ai_grade")
            .annotate(count=Count("id"))
            .values_list("ai_grade", "count")
        )

        # 2. Average score
        avg_score = submissions.aggregate(avg=Avg("ai_score"))["avg"] or 0

        # 3. Criteria averages from ai_criteria_details JSON
        criteria_totals = Counter()
        criteria_counts = Counter()
        criteria_max = {}

        suggestions_texts = []

        for row in submissions.values_list(
            "ai_criteria_details", "ai_suggestions"
        ).iterator():
            details, suggestions = row
            if details and isinstance(details, dict):
                for key, val in details.items():
                    if isinstance(val, dict) and "score" in val:
                        criteria_totals[key] += val["score"]
                        criteria_counts[key] += 1
                        if key not in criteria_max:
                            criteria_max[key] = val.get("max", 100)
            if suggestions:
                suggestions_texts.append(suggestions)

        criteria_averages = {}
        for key in criteria_totals:
            criteria_averages[key] = {
                "avg": round(criteria_totals[key] / criteria_counts[key], 1),
                "max": criteria_max.get(key, 100),
            }

        # 4. Completion stats
        submitted_users = set(
            submissions.values_list("user__username", flat=True).distinct()
        )
        completed_count = len(submitted_users)

        # Unaccepted users
        unaccepted = []
        if all_users_dict:
            for uname in set(all_users_dict.keys()) - submitted_users:
                class_name = all_users_dict[uname]
                real_name = get_real_name(uname, class_name)
                unaccepted.append({"username": uname, "real_name": real_name})

        # 5. Word cloud from suggestions
        word_freq = self._build_word_frequencies(suggestions_texts)

        return self.success({
            "total_count": total_count,
            "avg_score": round(avg_score, 1),
            "grade_distribution": grade_counts,
            "criteria_averages": criteria_averages,
            "person_count": len(all_users_dict),
            "completed_count": completed_count,
            "word_frequencies": word_freq,
            "data_unaccepted": unaccepted,
        })

    @staticmethod
    def _build_word_frequencies(texts, top_n=80):
        counter = Counter()
        for text in texts:
            text = re.sub(r"【重点】", "", text)
            words = jieba.cut(text)
            for w in words:
                w = w.strip()
                if len(w) >= 2 and w not in STOPWORDS:
                    counter[w] += 1
        return [{"word": w, "count": c} for w, c in counter.most_common(top_n)]
