from account.decorators import super_admin_required
from judge.tasks import judge_task

from utils.api import APIView
from ..models import Submission, JudgeStatus
from account.models import User, AdminType
from problem.models import Problem
from django.db.models import Count, Q


def get_real_name(username, class_name):
    if class_name and username.startswith("ks"):
        return username[len(f"ks{class_name}"):]
    return username


class SubmissionRejudgeAPI(APIView):
    @super_admin_required
    def get(self, request):
        id = request.GET.get("id")
        if not id:
            return self.error("Parameter error, id is required")
        try:
            submission = Submission.objects.select_related("problem").get(
                id=id, contest_id__isnull=True
            )
        except Submission.DoesNotExist:
            return self.error("Submission does not exists")
        submission.statistic_info = {}
        submission.save()

        judge_task.send(submission.id, submission.problem.id)
        return self.success()


class SubmissionStatisticsAPI(APIView):
    @super_admin_required
    def get(self, request):
        start = request.GET.get("start")
        end = request.GET.get("end")

        if not start or not end:
            return self.error("start and end is required")

        submissions = Submission.objects.filter(
            contest_id__isnull=True, create_time__gte=start, create_time__lte=end
        ).select_related("problem__created_by")

        problem_id = request.GET.get("problem_id")

        if problem_id:
            try:
                problem = Problem.objects.get(
                    _id=problem_id, contest_id__isnull=True, visible=True
                )
            except Problem.DoesNotExist:
                return self.error("Problem doesn't exist")
            submissions = submissions.filter(problem=problem)

        username = request.GET.get("username")

        all_users_dict = {}
        if username:
            submissions = submissions.filter(username__icontains=username)
            all_users_dict = {
                user["username"]: user["class_name"]
                for user in User.objects.filter(
                    username__icontains=username,
                    is_disabled=False,
                    admin_type=AdminType.REGULAR_USER,
                ).values("username", "class_name")
            }

        # 优化：一次性获取所有统计数据
        submission_stats = submissions.aggregate(
            total_count=Count("id"),
            accepted_count=Count("id", filter=Q(result=JudgeStatus.ACCEPTED)),
        )
        submission_count = submission_stats["total_count"]
        accepted_count = submission_stats["accepted_count"]
        correct_rate = (
            round(accepted_count / submission_count * 100, 2) if submission_count else 0
        )

        # 优化：获取用户提交统计
        user_submissions = (
            submissions.values("username")
            .annotate(
                submission_count=Count("id"),
                accepted_count=Count("id", filter=Q(result=JudgeStatus.ACCEPTED)),
            )
            .order_by("-submission_count")
        )

        # 获取所有有提交记录的用户的class_name信息
        submitted_usernames = {item["username"] for item in user_submissions}
        if submitted_usernames:
            submitted_users_dict = {
                user["username"]: user["class_name"]
                for user in User.objects.filter(
                    username__in=submitted_usernames
                ).values("username", "class_name")
            }
        else:
            submitted_users_dict = {}

        # 处理有提交记录的用户
        accepted = []

        for item in user_submissions:
            username_key = item["username"]

            if item["accepted_count"] > 0:
                rate = round(item["accepted_count"] / item["submission_count"] * 100, 2)
                accepted.append(
                    {
                        "username": username_key,
                        "class_name": submitted_users_dict.get(username_key),
                        "submission_count": item["submission_count"],
                        "accepted_count": item["accepted_count"],
                        "correct_rate": f"{rate}%",
                    }
                )

        # 处理无提交记录的用户，只返回姓名列表
        unaccepted = []
        if all_users_dict:
            unaccepted_usernames = set(all_users_dict.keys()) - submitted_usernames
            for username in unaccepted_usernames:
                class_name = all_users_dict[username]
                real_name = get_real_name(username, class_name)
                unaccepted.append(real_name)

        # 计算人数完成率
        person_count = len(all_users_dict) if all_users_dict else 0
        person_rate = 0
        if person_count:
            person_rate = min(100, round(len(accepted) / person_count * 100, 2))
            # 处理已删除用户但提交记录仍存在的情况
            if person_count < len(accepted):
                person_count = len(accepted)

        return self.success(
            {
                "submission_count": submission_count,
                "accepted_count": accepted_count,
                "correct_rate": f"{correct_rate}%",
                "person_count": person_count,
                "person_rate": f"{person_rate}%",
                "data": accepted,
                "data_unaccepted": unaccepted,
            }
        )
