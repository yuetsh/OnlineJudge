import io

import xlsxwriter
from asgiref.sync import sync_to_async
from django.http import HttpResponse
from django.utils.timezone import now

from account.decorators import (
    check_contest_password,
    check_contest_permission,
    login_required,
)
from account.models import AdminType
from problem.models import Problem
from utils.api import AsyncAPIView, validate_serializer
from utils.constants import CONTEST_PASSWORD_SESSION_KEY, ContestStatus
from utils.shortcuts import check_is_id, datetime2str

from ..models import ACMContestRank, Contest, ContestAnnouncement
from ..serializers import ACMContestRankSerializer, ContestAnnouncementSerializer, ContestPasswordVerifySerializer, ContestSerializer


# DEPRECATED: 前端未调用 (2026-05-26)
class ContestAnnouncementListAPI(AsyncAPIView):
    @check_contest_permission(check_type="announcements")
    async def get(self, request):
        contest_id = request.GET.get("contest_id")
        if not contest_id:
            return self.error("Invalid parameter, contest_id is required")
        qs = ContestAnnouncement.objects.select_related("created_by").filter(
            contest_id=contest_id, visible=True
        )
        max_id = request.GET.get("max_id")
        if max_id:
            qs = qs.filter(id__gt=max_id)
        data = await self.async_serialize_data(ContestAnnouncementSerializer, [item async for item in qs], many=True)
        return self.success(data)


class ContestAPI(AsyncAPIView):
    async def get(self, request):
        id = request.GET.get("id")
        if not id or not check_is_id(id):
            return self.error("Invalid parameter, id is required")
        try:
            contest = await (
                Contest.objects.select_related("created_by")
                .filter(id=id, visible=True)
                .afirst()
            )
            if contest is None:
                raise Contest.DoesNotExist
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")
        data = await self.async_serialize_data(ContestSerializer, contest)
        data["now"] = datetime2str(now())
        return self.success(data)


class ContestListAPI(AsyncAPIView):
    async def get(self, request):
        contests = Contest.objects.select_related("created_by").filter(visible=True)
        keyword = request.GET.get("keyword")
        status = request.GET.get("status")
        tag = request.GET.get("tag")
        if keyword:
            contests = contests.filter(title__icontains=keyword)
        if tag:
            contests = contests.filter(tag=tag)
        if status:
            cur = now()
            if status == ContestStatus.CONTEST_NOT_START:
                contests = contests.filter(start_time__gt=cur)
            elif status == ContestStatus.CONTEST_ENDED:
                contests = contests.filter(end_time__lt=cur)
            else:
                contests = contests.filter(start_time__lte=cur, end_time__gte=cur)
        return self.success(await self.async_paginate_data(request, contests, ContestSerializer))


class ContestPasswordVerifyAPI(AsyncAPIView):
    @validate_serializer(ContestPasswordVerifySerializer)
    @login_required
    async def post(self, request):
        data = request.data
        try:
            contest = await Contest.objects.aget(
                id=data["contest_id"], visible=True, password__isnull=False
            )
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")
        if not check_contest_password(data["password"], contest.password):
            return self.error("Wrong password or password expired")

        if CONTEST_PASSWORD_SESSION_KEY not in request.session:
            request.session[CONTEST_PASSWORD_SESSION_KEY] = {}
        request.session[CONTEST_PASSWORD_SESSION_KEY][contest.id] = data["password"]
        request.session.modified = True
        return self.success(True)


class ContestAccessAPI(AsyncAPIView):
    @login_required
    async def get(self, request):
        contest_id = request.GET.get("contest_id")
        if not contest_id:
            return self.error()
        try:
            contest = await Contest.objects.aget(
                id=contest_id, visible=True, password__isnull=False
            )
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")
        session_pass = request.session.get(CONTEST_PASSWORD_SESSION_KEY, {}).get(
            contest.id
        )
        return self.success(
            {"access": check_contest_password(session_pass, contest.password)}
        )


class ContestRankAPI(AsyncAPIView):
    def get_rank(self):
        return (
            ACMContestRank.objects.filter(
                contest=self.contest,
                user__admin_type__in=[AdminType.REGULAR_USER, AdminType.STUDENT_ADMIN],
                user__is_disabled=False,
            )
            .select_related("user")
            .order_by("-accepted_number", "total_time")
        )

    def column_string(self, n):
        string = ""
        while n > 0:
            n, remainder = divmod(n - 1, 26)
            string = chr(65 + remainder) + string
        return string

    def _build_xlsx(self, data, contest_problems):
        problem_id_to_col = {p.id: i for i, p in enumerate(contest_problems)}
        f = io.BytesIO()
        workbook = xlsxwriter.Workbook(f)
        worksheet = workbook.add_worksheet()
        worksheet.write("A1", "User ID")
        worksheet.write("B1", "Username")
        worksheet.write("C1", "Real Name")
        worksheet.write("D1", "AC")
        worksheet.write("E1", "Total Submission")
        worksheet.write("F1", "Total Time")
        for i, p in enumerate(contest_problems):
            worksheet.write(self.column_string(7 + i) + "1", p.title)

        for index, item in enumerate(data):
            worksheet.write_string(index + 1, 0, str(item["user"]["id"]))
            worksheet.write_string(index + 1, 1, item["user"]["username"])
            worksheet.write_string(
                index + 1, 2, item["user"]["real_name"] or ""
            )
            worksheet.write_string(index + 1, 3, str(item["accepted_number"]))
            worksheet.write_string(index + 1, 4, str(item["submission_number"]))
            worksheet.write_string(index + 1, 5, str(item["total_time"]))
            for k, v in item["submission_info"].items():
                worksheet.write_string(
                    index + 1, 6 + problem_id_to_col[int(k)], str(v["is_ac"])
                )

        workbook.close()
        f.seek(0)
        return f.read()

    @check_contest_permission(check_type="ranks")
    async def get(self, request):
        download_csv = request.GET.get("download_csv")
        is_contest_admin = (
            request.user.is_authenticated
            and request.user.is_contest_admin(self.contest)
        )

        qs = self.get_rank()

        if download_csv:
            rank_list = [item async for item in qs]
            data = await self.async_serialize_data(
                ACMContestRankSerializer, rank_list, many=True, is_contest_admin=is_contest_admin
            )
            contest_problems = await sync_to_async(
                lambda: list(Problem.objects.filter(contest=self.contest, visible=True).order_by("_id"))
            )()
            xlsx_bytes = await sync_to_async(self._build_xlsx)(data, contest_problems)
            response = HttpResponse(xlsx_bytes)
            response["Content-Disposition"] = (
                f"attachment; filename=content-{self.contest.id}-rank.xlsx"
            )
            response["Content-Type"] = "application/xlsx"
            return response

        page_qs = await self.async_paginate_data(request, qs)
        page_qs["results"] = await self.async_serialize_data(
            ACMContestRankSerializer,
            page_qs["results"], many=True, is_contest_admin=is_contest_admin
        )
        return self.success(page_qs)
