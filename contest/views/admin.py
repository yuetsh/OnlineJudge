from datetime import datetime, timedelta
from ipaddress import ip_network

from django.utils.timezone import now

from account.decorators import ensure_created_by, teacher_admin_required
from problem.models import Problem
from utils.api import APIView, validate_serializer

from ..models import ACMContestRank, Contest
from ..serializers import (
    ACMContesHelperSerializer,
    ContestAdminSerializer,
    ContestCloneSerializer,
    CreateConetestSeriaizer,
    EditConetestSeriaizer,
)


class ContestAPI(APIView):
    @validate_serializer(CreateConetestSeriaizer)
    @teacher_admin_required
    def post(self, request):
        data = request.data
        # DRF 的 DateTimeField 已经校验并规范化过，这里拿到的必定是 ISO 8601 字符串
        data["start_time"] = datetime.fromisoformat(data["start_time"])
        data["end_time"] = datetime.fromisoformat(data["end_time"])
        data["created_by"] = request.user
        if data["end_time"] <= data["start_time"]:
            return self.error("Start time must occur earlier than end time")
        if data.get("password") and data["password"] == "":
            data["password"] = None
        for ip_range in data["allowed_ip_ranges"]:
            try:
                ip_network(ip_range, strict=False)
            except ValueError:
                return self.error(f"{ip_range} is not a valid cidr network")
        contest = Contest.objects.create(**data)
        return self.success(ContestAdminSerializer(contest).data)

    @validate_serializer(EditConetestSeriaizer)
    @teacher_admin_required
    def put(self, request):
        data = request.data
        try:
            contest = Contest.objects.get(id=data.pop("id"))
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")
        ensure_created_by(contest, request.user)
        # DRF 的 DateTimeField 已经校验并规范化过，这里拿到的必定是 ISO 8601 字符串
        data["start_time"] = datetime.fromisoformat(data["start_time"])
        data["end_time"] = datetime.fromisoformat(data["end_time"])
        if data["end_time"] <= data["start_time"]:
            return self.error("Start time must occur earlier than end time")
        if not data["password"]:
            data["password"] = None
        for ip_range in data["allowed_ip_ranges"]:
            try:
                ip_network(ip_range, strict=False)
            except ValueError:
                return self.error(f"{ip_range} is not a valid cidr network")
        for k, v in data.items():
            setattr(contest, k, v)
        contest.save()
        return self.success(ContestAdminSerializer(contest).data)

    @teacher_admin_required
    def get(self, request):
        contest_id = request.GET.get("id")
        if contest_id:
            try:
                contest = Contest.objects.get(id=contest_id)
                ensure_created_by(contest, request.user)
                return self.success(ContestAdminSerializer(contest).data)
            except Contest.DoesNotExist:
                return self.error("Contest does not exist")

        contests = Contest.objects.all().order_by("-create_time")
        if not request.user.is_super_admin():
            contests = contests.filter(created_by=request.user)

        keyword = request.GET.get("keyword")
        if keyword:
            contests = contests.filter(title__contains=keyword)
        return self.success(self.paginate_data(request, contests, ContestAdminSerializer))


class ACMContestHelper(APIView):
    @teacher_admin_required
    def get(self, request):
        contest_id = request.GET.get("contest_id")
        if not contest_id:
            return self.error("Parameter error, contest_id is required")
        try:
            contest = Contest.objects.get(id=contest_id, visible=True)
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")
        ensure_created_by(contest, request.user)

        problems = Problem.objects.filter(contest=contest).values("id", "_id")
        problem_id_map = {str(p["id"]): p["_id"] for p in problems}

        ranks = ACMContestRank.objects.filter(contest=contest, accepted_number__gt=0).values("id", "user__username", "user__userprofile__real_name", "submission_info")
        results = []
        for rank in ranks:
            for problem_id, info in rank["submission_info"].items():
                if info["is_ac"]:
                    results.append(
                        {
                            "id": rank["id"],
                            "username": rank["user__username"],
                            "real_name": rank["user__userprofile__real_name"],
                            "problem_id": problem_id,
                            "problem_display_id": problem_id_map.get(problem_id, problem_id),
                            "ac_info": info,
                            "checked": info.get("checked", False),
                        }
                    )
        results.sort(key=lambda x: -x["ac_info"]["ac_time"])
        return self.success(results)

    @teacher_admin_required
    @validate_serializer(ACMContesHelperSerializer)
    def put(self, request):
        data = request.data
        # 原来只按 pk 取，contest_id 明明在序列化器里、客户端一直在传，却完全没用上。
        # 于是任何老师都能改别人比赛里的检查标记 —— teacher_admin_required 只保证
        # "是老师"。同类的 get 是有 ensure_created_by 的，这里补齐。
        try:
            rank = ACMContestRank.objects.get(pk=data["rank_id"], contest_id=data["contest_id"])
        except ACMContestRank.DoesNotExist:
            return self.error("Rank id does not exist")
        ensure_created_by(rank.contest, request.user)
        problem_rank_status = rank.submission_info.get(data["problem_id"])
        if not problem_rank_status:
            return self.error("Problem id does not exist")
        problem_rank_status["checked"] = data["checked"]
        rank.save(update_fields=("submission_info",))
        return self.success()


class ContestCloneAPI(APIView):
    @validate_serializer(ContestCloneSerializer)
    @teacher_admin_required
    def post(self, request):
        try:
            original = Contest.objects.get(id=request.data["contest_id"])
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")

        duration = original.end_time - original.start_time
        new_start = now() + timedelta(minutes=10)
        new_end = new_start + duration

        new_contest = Contest.objects.create(
            title=original.title,
            description=original.description,
            tag=original.tag,
            password=original.password,
            visible=False,
            allowed_ip_ranges=original.allowed_ip_ranges,
            start_time=new_start,
            end_time=new_end,
            created_by=request.user,
        )

        for problem in Problem.objects.filter(contest=original):
            tags = problem.tags.all()
            problem.pk = None
            problem.contest = new_contest
            problem.submission_number = 0
            problem.accepted_number = 0
            problem.statistic_info = {}
            problem.created_by = request.user
            problem.save()
            problem.tags.set(tags)

        return self.success(ContestAdminSerializer(new_contest).data)
