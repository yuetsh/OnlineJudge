import math
import statistics
from datetime import datetime

from django.db.models import Avg, Sum
from django.utils import timezone

from account.decorators import login_required
from account.models import AdminType, User, UserProfile
from submission.models import JudgeStatus, Submission
from utils.api import APIView


class ClassRankAPI(APIView):
    """获取班级排名列表"""

    def get(self, request):
        # 获取年级参数
        grade = int(request.GET.get("grade"))
        # 获取所有有用户的班级
        classes = (
            User.objects.filter(
                class_name__isnull=False,
                is_disabled=False,
                admin_type__in=[AdminType.REGULAR_USER, AdminType.ADMIN],
                class_name__startswith=str(grade),
            )
            .values("class_name")
            .distinct()
        )

        class_stats = []
        for class_info in classes:
            class_name = class_info["class_name"]
            users = User.objects.filter(
                class_name=class_name,
                is_disabled=False,
                admin_type__in=[AdminType.REGULAR_USER, AdminType.ADMIN],
            )
            user_ids = list(users.values_list("id", flat=True))

            profiles = UserProfile.objects.filter(user_id__in=user_ids)

            total_ac = profiles.aggregate(total=Sum("accepted_number"))["total"] or 0
            total_submission = (
                profiles.aggregate(total=Sum("submission_number"))["total"] or 0
            )
            avg_ac = profiles.aggregate(avg=Avg("accepted_number"))["avg"] or 0

            user_count = users.count()

            class_stats.append(
                {
                    "class_name": class_name,
                    "user_count": user_count,
                    "total_ac": int(total_ac),
                    "total_submission": int(total_submission),
                    "avg_ac": round(avg_ac, 2),
                    "ac_rate": round(total_ac / total_submission * 100, 2)
                    if total_submission > 0
                    else 0,
                }
            )

        # 按总AC数排序
        class_stats.sort(key=lambda x: (-x["total_ac"], x["total_submission"]))

        # 添加排名
        for i, stat in enumerate(class_stats):
            stat["rank"] = i + 1

        return self.success(class_stats)


class UserClassRankAPI(APIView):
    """获取用户在班级中的排名"""

    @login_required
    def get(self, request):
        user = request.user
        if not user.class_name:
            return self.error("用户没有班级信息")
        scope = request.GET.get("scope", "").lower()
        show_all = scope == "all"
        try:
            limit = int(request.GET.get("limit", "10"))
        except ValueError:
            limit = 10
        if limit <= 0 or limit > 250:
            limit = 10
        try:
            offset = int(request.GET.get("offset", "0"))
        except ValueError:
            offset = 0
        if offset < 0:
            offset = 0

        # 获取同班所有用户
        class_users = User.objects.filter(
            class_name=user.class_name,
            is_disabled=False,
            admin_type__in=[AdminType.REGULAR_USER, AdminType.ADMIN],
        ).select_related("userprofile")

        user_ranks = []
        for class_user in class_users:
            profile = class_user.userprofile
            user_ranks.append(
                {
                    "user_id": class_user.id,
                    "username": class_user.username,
                    "accepted_number": profile.accepted_number,
                    "submission_number": profile.submission_number,
                }
            )

        # 按AC数排序
        user_ranks.sort(key=lambda x: (-x["accepted_number"], x["submission_number"]))

        # 添加排名
        my_rank = -1
        for i, rank_info in enumerate(user_ranks):
            rank_info["rank"] = i + 1
            if rank_info["user_id"] == user.id:
                my_rank = i + 1

        trimmed_ranks = user_ranks
        if not show_all and my_rank > 0 and len(user_ranks) > 10:
            center_index = my_rank - 1
            start = max(0, center_index - 5)
            end = start + 10
            if end > len(user_ranks):
                end = len(user_ranks)
                start = max(0, end - 10)
            trimmed_ranks = user_ranks[start:end]
        elif show_all:
            trimmed_ranks = user_ranks[offset : offset + limit]

        return self.success(
            {
                "class_name": user.class_name,
                "my_rank": my_rank,
                "total": len(user_ranks),
                "ranks": trimmed_ranks,
            }
        )


class ClassPKAPI(APIView):
    """班级PK比较 - 多维度教育评价"""

    def post(self, request):
        class_names = request.data.get("class_name", [])
        if not class_names or len(class_names) < 2:
            return self.error("至少需要选择2个班级进行比较")

        # 获取时间段参数
        start_time = request.data.get("start_time")
        end_time = request.data.get("end_time")

        # 将时间字符串转换为datetime对象
        # 处理空字符串、None 或 undefined 的情况
        if start_time and isinstance(start_time, str) and start_time.strip():
            try:
                start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                if timezone.is_naive(start_time):
                    start_time = timezone.make_aware(start_time)
            except (ValueError, AttributeError):
                start_time = None
        else:
            start_time = None

        if end_time and isinstance(end_time, str) and end_time.strip():
            try:
                end_time = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                if timezone.is_naive(end_time):
                    end_time = timezone.make_aware(end_time)
            except (ValueError, AttributeError):
                end_time = None
        else:
            end_time = None

        class_comparisons = []

        # 预计算全局阈值（所有参与PK班级的学生AC数合并）
        all_user_ids = list(
            User.objects.filter(
                class_name__in=class_names,
                is_disabled=False,
                admin_type__in=[AdminType.REGULAR_USER, AdminType.ADMIN],
            ).values_list("id", flat=True)
        )
        all_ac_list = sorted(
            [p.accepted_number for p in UserProfile.objects.filter(user_id__in=all_user_ids)],
            reverse=True,
        )
        if len(all_ac_list) > 1:
            _quantiles = statistics.quantiles(all_ac_list, n=4)
            global_q1 = _quantiles[0]
            global_q3 = _quantiles[2]
        else:
            global_q1 = all_ac_list[0] if all_ac_list else 0
            global_q3 = all_ac_list[0] if all_ac_list else 0

        for class_name in class_names:
            users = User.objects.filter(
                class_name=class_name,
                is_disabled=False,
                admin_type__in=[AdminType.REGULAR_USER, AdminType.ADMIN],
            )
            user_ids = list(users.values_list("id", flat=True))

            # 获取所有学生的AC数列表（用于统计计算）
            profiles = UserProfile.objects.filter(user_id__in=user_ids)
            ac_list = sorted([p.accepted_number for p in profiles], reverse=True)
            submission_list = sorted(
                [p.submission_number for p in profiles], reverse=True
            )

            user_count = len(ac_list)
            if user_count == 0:
                continue

            # 基础统计
            total_ac = sum(ac_list)
            total_submission = sum(submission_list)
            avg_ac = statistics.mean(ac_list) if ac_list else 0

            # 中位数和分位数
            median_ac = statistics.median(ac_list) if ac_list else 0
            q1_ac = statistics.quantiles(ac_list, n=4)[0] if len(ac_list) > 1 else 0
            q3_ac = statistics.quantiles(ac_list, n=4)[2] if len(ac_list) > 1 else 0
            iqr = q3_ac - q1_ac

            # 标准差
            std_dev = statistics.stdev(ac_list) if len(ac_list) > 1 else 0

            # 前10%和后10%统计
            top_10_count = max(1, math.ceil(user_count * 0.10))
            bottom_10_count = max(1, math.ceil(user_count * 0.10))
            top_10_avg = (
                statistics.mean(ac_list[:top_10_count]) if top_10_count > 0 else 0
            )
            bottom_10_avg = (
                statistics.mean(ac_list[-bottom_10_count:])
                if bottom_10_count > 0
                else 0
            )

            # 中间80%均值（截尾均值，去掉前10%和后10%）
            if top_10_count + bottom_10_count < user_count:
                middle_list = ac_list[top_10_count:-bottom_10_count]
            else:
                middle_list = ac_list
            middle_80_avg = statistics.mean(middle_list) if middle_list else avg_ac

            # 优秀率（AC数 >= 全局Q3，即超过PK组所有学生的前25%）
            excellent_count = sum(1 for ac in ac_list if ac >= global_q3)
            excellent_rate = (
                (excellent_count / user_count * 100) if user_count > 0 else 0
            )

            # 及格率（AC数 >= 全局Q1，即超过PK组所有学生的后25%）
            pass_count = sum(1 for ac in ac_list if ac >= global_q1)
            pass_rate = (pass_count / user_count * 100) if user_count > 0 else 0

            # 参与度（有提交记录的学生比例）
            active_count = sum(1 for sub in submission_list if sub > 0)
            active_rate = (active_count / user_count * 100) if user_count > 0 else 0

            # 时间段内的统计（如果提供了时间段）
            recent_stats = {}
            if start_time and end_time:
                submissions = Submission.objects.filter(
                    user_id__in=user_ids,
                    create_time__gte=start_time,
                    create_time__lte=end_time,
                )
                recent_ac = (
                    submissions.filter(result=JudgeStatus.ACCEPTED)
                    .values("user_id", "problem_id")
                    .distinct()
                    .count()
                )
                recent_submission = submissions.count()

                # 时间段内的用户AC数列表
                recent_user_ac = {}
                for user_id in user_ids:
                    user_recent_ac = (
                        submissions.filter(user_id=user_id, result=JudgeStatus.ACCEPTED)
                        .values("problem_id")
                        .distinct()
                        .count()
                    )
                    recent_user_ac[user_id] = user_recent_ac

                recent_ac_list = sorted(recent_user_ac.values(), reverse=True)
                if recent_ac_list:
                    recent_stats = {
                        "recent_total_ac": recent_ac,
                        "recent_total_submission": recent_submission,
                        "recent_avg_ac": statistics.mean(recent_ac_list),
                        "recent_median_ac": statistics.median(recent_ac_list),
                        "recent_top_10_avg": statistics.mean(
                            recent_ac_list[: max(1, math.ceil(len(recent_ac_list) * 0.10))]
                        )
                        if recent_ac_list
                        else 0,
                        "recent_active_count": sum(
                            1 for ac in recent_ac_list if ac > 0
                        ),
                    }

            class_comparisons.append(
                {
                    "class_name": class_name,
                    "user_count": user_count,
                    # 基础统计
                    "total_ac": int(total_ac),
                    "total_submission": int(total_submission),
                    "avg_ac": round(avg_ac, 2),
                    # 中位数和分位数
                    "median_ac": round(median_ac, 2),
                    "q1_ac": round(q1_ac, 2),
                    "q3_ac": round(q3_ac, 2),
                    "iqr": round(iqr, 2),
                    # 标准差
                    "std_dev": round(std_dev, 2),
                    # 分层统计
                    "top_10_avg": round(top_10_avg, 2),
                    "middle_80_avg": round(middle_80_avg, 2),
                    "bottom_10_avg": round(bottom_10_avg, 2),
                    # 比率统计
                    "excellent_rate": round(excellent_rate, 2),
                    "pass_rate": round(pass_rate, 2),
                    "active_rate": round(active_rate, 2),
                    # 正确率
                    "ac_rate": round(total_ac / total_submission * 100, 2)
                    if total_submission > 0
                    else 0,
                    # 时间段统计（如果有）
                    **recent_stats,
                }
            )

        # 计算综合分（需要所有班级数据就绪后才能归一化）
        max_median = max((c["median_ac"] for c in class_comparisons), default=1) or 1
        max_middle = max((c["middle_80_avg"] for c in class_comparisons), default=1) or 1

        for c in class_comparisons:
            score = (
                0.40 * (c["median_ac"] / max_median * 100)
                + 0.15 * (c["middle_80_avg"] / max_middle * 100)
                + 0.20 * c["active_rate"]
                + 0.15 * c["pass_rate"]
                + 0.10 * c["excellent_rate"]
            )
            c["composite_score"] = round(score, 1)

        # 按综合分排序（主），中位数（次）
        class_comparisons.sort(
            key=lambda x: (-x["composite_score"], -x["median_ac"])
        )

        return self.success(
            {
                "comparisons": class_comparisons,
                "has_time_range": bool(start_time and end_time),
            }
        )
