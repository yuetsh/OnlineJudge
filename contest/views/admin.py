import copy
import os
import zipfile
from datetime import timedelta
from ipaddress import ip_network

import dateutil.parser
from django.http import FileResponse
from django.utils.timezone import now

from account.decorators import super_admin_required
from account.models import User
from problem.models import Problem
from submission.models import JudgeStatus, Submission
from utils.api import APIView, validate_serializer
from utils.cache import cache
from utils.constants import CacheKey
from utils.shortcuts import rand_str
from utils.tasks import delete_files

from ..models import ACMContestRank, Contest, ContestAnnouncement
from ..serializers import (
    ACMContesHelperSerializer,
    ContestAdminSerializer,
    ContestAnnouncementSerializer,
    ContestCloneSerializer,
    CreateConetestSeriaizer,
    CreateContestAnnouncementSerializer,
    EditConetestSeriaizer,
    EditContestAnnouncementSerializer,
)


class ContestAPI(APIView):
    @validate_serializer(CreateConetestSeriaizer)
    @super_admin_required
    def post(self, request):
        data = request.data
        data["start_time"] = dateutil.parser.parse(data["start_time"])
        data["end_time"] = dateutil.parser.parse(data["end_time"])
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
    @super_admin_required
    def put(self, request):
        data = request.data
        try:
            contest = Contest.objects.get(id=data.pop("id"))
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")
        data["start_time"] = dateutil.parser.parse(data["start_time"])
        data["end_time"] = dateutil.parser.parse(data["end_time"])
        if data["end_time"] <= data["start_time"]:
            return self.error("Start time must occur earlier than end time")
        if not data["password"]:
            data["password"] = None
        for ip_range in data["allowed_ip_ranges"]:
            try:
                ip_network(ip_range, strict=False)
            except ValueError:
                return self.error(f"{ip_range} is not a valid cidr network")
        if not contest.real_time_rank and data.get("real_time_rank"):
            cache_key = f"{CacheKey.contest_rank_cache}:{contest.id}"
            cache.delete(cache_key)

        for k, v in data.items():
            setattr(contest, k, v)
        contest.save()
        return self.success(ContestAdminSerializer(contest).data)

    @super_admin_required
    def get(self, request):
        contest_id = request.GET.get("id")
        if contest_id:
            try:
                contest = Contest.objects.get(id=contest_id)
                return self.success(ContestAdminSerializer(contest).data)
            except Contest.DoesNotExist:
                return self.error("Contest does not exist")

        contests = Contest.objects.all().order_by("-create_time")

        keyword = request.GET.get("keyword")
        if keyword:
            contests = contests.filter(title__contains=keyword)
        return self.success(
            self.paginate_data(request, contests, ContestAdminSerializer)
        )


class ContestAnnouncementAPI(APIView):
    @validate_serializer(CreateContestAnnouncementSerializer)
    @super_admin_required
    def post(self, request):
        """
        Create one contest_announcement.
        """
        data = request.data
        try:
            contest = Contest.objects.get(id=data.pop("contest_id"))
            data["contest"] = contest
            data["created_by"] = request.user
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")
        announcement = ContestAnnouncement.objects.create(**data)
        return self.success(ContestAnnouncementSerializer(announcement).data)

    @validate_serializer(EditContestAnnouncementSerializer)
    @super_admin_required
    def put(self, request):
        """
        update contest_announcement
        """
        data = request.data
        try:
            contest_announcement = ContestAnnouncement.objects.get(id=data.pop("id"))
        except ContestAnnouncement.DoesNotExist:
            return self.error("Contest announcement does not exist")
        for k, v in data.items():
            setattr(contest_announcement, k, v)
        contest_announcement.save()
        return self.success()

    @super_admin_required
    def delete(self, request):
        """
        Delete one contest_announcement.
        """
        contest_announcement_id = request.GET.get("id")
        if contest_announcement_id:
            ContestAnnouncement.objects.filter(id=contest_announcement_id).delete()
        return self.success()

    @super_admin_required
    def get(self, request):
        """
        Get one contest_announcement or contest_announcement list.
        """
        contest_announcement_id = request.GET.get("id")
        if contest_announcement_id:
            try:
                contest_announcement = ContestAnnouncement.objects.get(
                    id=contest_announcement_id
                )
                return self.success(
                    ContestAnnouncementSerializer(contest_announcement).data
                )
            except ContestAnnouncement.DoesNotExist:
                return self.error("Contest announcement does not exist")

        contest_id = request.GET.get("contest_id")
        if not contest_id:
            return self.error("Parameter error")
        contest_announcements = ContestAnnouncement.objects.filter(
            contest_id=contest_id
        )
        keyword = request.GET.get("keyword")
        if keyword:
            contest_announcements = contest_announcements.filter(
                title__contains=keyword
            )
        return self.success(
            ContestAnnouncementSerializer(contest_announcements, many=True).data
        )


class ACMContestHelper(APIView):
    @super_admin_required
    def get(self, request):
        contest_id = request.GET.get("contest_id")
        if not contest_id:
            return self.error("Parameter error, contest_id is required")
        try:
            contest = Contest.objects.get(id=contest_id, visible=True)
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")

        problems = Problem.objects.filter(contest=contest).values("id", "_id")
        problem_id_map = {str(p["id"]): p["_id"] for p in problems}

        ranks = ACMContestRank.objects.filter(
            contest=contest, accepted_number__gt=0
        ).values(
            "id", "user__username", "user__userprofile__real_name", "submission_info"
        )
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
                            "problem_display_id": problem_id_map.get(
                                problem_id, problem_id
                            ),
                            "ac_info": info,
                            "checked": info.get("checked", False),
                        }
                    )
        results.sort(key=lambda x: -x["ac_info"]["ac_time"])
        return self.success(results)

    @super_admin_required
    @validate_serializer(ACMContesHelperSerializer)
    def put(self, request):
        data = request.data
        try:
            rank = ACMContestRank.objects.get(pk=data["rank_id"])
        except ACMContestRank.DoesNotExist:
            return self.error("Rank id does not exist")
        problem_rank_status = rank.submission_info.get(data["problem_id"])
        if not problem_rank_status:
            return self.error("Problem id does not exist")
        problem_rank_status["checked"] = data["checked"]
        rank.save(update_fields=("submission_info",))
        return self.success()


class DownloadContestSubmissions(APIView):
    def _dump_submissions(self, contest, exclude_admin=True):
        problem_ids = contest.problem_set.all().values_list("id", "_id")
        id2display_id = {k[0]: k[1] for k in problem_ids}
        ac_map = {k[0]: False for k in problem_ids}
        submissions = Submission.objects.filter(
            contest=contest, result=JudgeStatus.ACCEPTED
        ).order_by("-create_time")
        user_ids = submissions.values_list("user_id", flat=True)
        users = User.objects.filter(id__in=user_ids)
        path = f"/tmp/{rand_str()}.zip"
        with zipfile.ZipFile(path, "w") as zip_file:
            for user in users:
                if user.is_admin_role() and exclude_admin:
                    continue
                user_ac_map = copy.deepcopy(ac_map)
                user_submissions = submissions.filter(user_id=user.id)
                for submission in user_submissions:
                    problem_id = submission.problem_id
                    if user_ac_map[problem_id]:
                        continue
                    file_name = (
                        f"{user.username}_{id2display_id[submission.problem_id]}.txt"
                    )
                    compression = zipfile.ZIP_DEFLATED
                    zip_file.writestr(
                        zinfo_or_arcname=f"{file_name}",
                        data=submission.code,
                        compress_type=compression,
                    )
                    user_ac_map[problem_id] = True
        return path

    @super_admin_required
    def get(self, request):
        contest_id = request.GET.get("contest_id")
        if not contest_id:
            return self.error("Parameter error")
        try:
            contest = Contest.objects.get(id=contest_id)
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")

        exclude_admin = request.GET.get("exclude_admin") == "1"
        zip_path = self._dump_submissions(contest, exclude_admin)
        delete_files.send_with_options(args=(zip_path,), delay=300_000)
        resp = FileResponse(open(zip_path, "rb"))
        resp["Content-Type"] = "application/zip"
        resp["Content-Disposition"] = (
            f"attachment;filename={os.path.basename(zip_path)}"
        )
        return resp


class ContestCloneAPI(APIView):
    @validate_serializer(ContestCloneSerializer)
    @super_admin_required
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
            rule_type=original.rule_type,
            password=original.password,
            real_time_rank=original.real_time_rank,
            visible=original.visible,
            allowed_ip_ranges=original.allowed_ip_ranges,
            start_time=new_start,
            end_time=new_end,
            created_by=request.user,
        )

        for problem in Problem.objects.filter(contest=original):
            new_problem = Problem.objects.create(
                _id=problem._id,
                contest=new_contest,
                is_public=problem.is_public,
                title=problem.title,
                description=problem.description,
                input_description=problem.input_description,
                output_description=problem.output_description,
                samples=problem.samples,
                test_case_id=problem.test_case_id,
                test_case_score=problem.test_case_score,
                hint=problem.hint,
                languages=problem.languages,
                template=problem.template,
                created_by=request.user,
                time_limit=problem.time_limit,
                memory_limit=problem.memory_limit,
                io_mode=problem.io_mode,
                rule_type=problem.rule_type,
                visible=problem.visible,
                difficulty=problem.difficulty,
                source=problem.source,
                prompt=problem.prompt,
                answers=problem.answers,
                total_score=problem.total_score,
                share_submission=problem.share_submission,
                allow_flowchart=problem.allow_flowchart,
                mermaid_code=problem.mermaid_code,
                flowchart_data=problem.flowchart_data,
                flowchart_hint=problem.flowchart_hint,
                show_flowchart=problem.show_flowchart,
            )
            new_problem.tags.set(problem.tags.all())

        return self.success(ContestAdminSerializer(new_contest).data)
