import asyncio
import hashlib
import os
import random
import re
import shutil
from datetime import timedelta

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone

from account.decorators import super_admin_required
from account.models import User
from contest.models import Contest
from judge.dispatcher import process_pending_task
from options.options import SysOptions
from problem.models import Problem
from submission.models import Submission
from utils.api import APIView, AsyncAPIView, CSRFExemptAPIView, validate_serializer
from utils.cache import JsonDataLoader
from utils.shortcuts import get_env, strip_class_prefix
from utils.websocket import push_config_update
from utils.xss_filter import XSSHtml

from .models import JudgeServer
from .serializers import (
    CreateEditWebsiteConfigSerializer,
    EditJudgeServerSerializer,
    JudgeServerHeartbeatSerializer,
    JudgeServerSerializer,
)


class WebsiteConfigAPI(AsyncAPIView):
    async def get(self, request):
        ret = await SysOptions.aget_many(
            "website_base_url",
            "website_name",
            "website_name_shortcut",
            "website_footer",
            "allow_register",
            "submission_list_show_all",
            "class_list",
            "enable_maxkb",
        )
        return self.success(ret)

    @super_admin_required
    @validate_serializer(CreateEditWebsiteConfigSerializer)
    async def post(self, request):
        @sync_to_async
        def _update_config(data):
            for k, v in data.items():
                if k == "website_footer":
                    with XSSHtml() as parser:
                        v = parser.clean(v)
                setattr(SysOptions, k, v)
                push_config_update(k, v)

        await _update_config(request.data)
        return self.success()


class JudgeServerAPI(APIView):
    @super_admin_required
    def get(self, request):
        servers = JudgeServer.objects.all().order_by("-last_heartbeat")
        return self.success(
            {
                "token": SysOptions.judge_server_token,
                "servers": JudgeServerSerializer(servers, many=True).data,
            }
        )

    @super_admin_required
    def delete(self, request):
        hostname = request.GET.get("hostname")
        if hostname:
            JudgeServer.objects.filter(hostname=hostname).delete()
        return self.success()

    @validate_serializer(EditJudgeServerSerializer)
    @super_admin_required
    def put(self, request):
        is_disabled = request.data.get("is_disabled", False)
        JudgeServer.objects.filter(id=request.data["id"]).update(is_disabled=is_disabled)
        if not is_disabled:
            process_pending_task()
        return self.success()


class JudgeServerHeartbeatAPI(CSRFExemptAPIView):
    @validate_serializer(JudgeServerHeartbeatSerializer)
    def post(self, request):
        data = request.data
        client_token = request.META.get("HTTP_X_JUDGE_SERVER_TOKEN")
        if hashlib.sha256(SysOptions.judge_server_token.encode("utf-8")).hexdigest() != client_token:
            return self.error("Invalid token")

        try:
            server = JudgeServer.objects.get(hostname=data["hostname"])
            server.judger_version = data["judger_version"]
            server.cpu_core = data["cpu_core"]
            server.memory_usage = data["memory"]
            server.cpu_usage = data["cpu"]
            server.service_url = data["service_url"]
            server.ip = request.ip
            server.last_heartbeat = timezone.now()
            server.save(
                update_fields=[
                    "judger_version",
                    "cpu_core",
                    "memory_usage",
                    "service_url",
                    "ip",
                    "last_heartbeat",
                ]
            )
        except JudgeServer.DoesNotExist:
            JudgeServer.objects.create(
                hostname=data["hostname"],
                judger_version=data["judger_version"],
                cpu_core=data["cpu_core"],
                memory_usage=data["memory"],
                cpu_usage=data["cpu"],
                ip=request.META["REMOTE_ADDR"],
                service_url=data["service_url"],
                last_heartbeat=timezone.now(),
            )
        # 新server上线 处理队列中的，防止没有新的提交而导致一直waiting
        process_pending_task()

        return self.success()


# DEPRECATED: 前端未调用 (2026-05-26)
class LanguagesAPI(APIView):
    def get(self, request):
        return self.success(
            {
                "languages": SysOptions.languages,
            }
        )


class TestCasePruneAPI(APIView):
    @super_admin_required
    def get(self, request):
        """
        return orphan test_case list
        """
        ret_data = []
        dir_to_be_removed = self.get_orphan_ids()

        # return an iterator
        for d in os.scandir(settings.TEST_CASE_DIR):
            if d.name in dir_to_be_removed:
                ret_data.append({"id": d.name, "create_time": d.stat().st_mtime})
        return self.success(ret_data)

    @super_admin_required
    def delete(self, request):
        test_case_id = request.GET.get("id")
        if test_case_id:
            self.delete_one(test_case_id)
            return self.success()
        for id in self.get_orphan_ids():
            self.delete_one(id)
        return self.success()

    @staticmethod
    def get_orphan_ids():
        db_ids = Problem.objects.all().values_list("test_case_id", flat=True)
        disk_ids = os.listdir(settings.TEST_CASE_DIR)
        test_case_re = re.compile(r"^[a-zA-Z0-9]{32}$")
        disk_ids = filter(lambda f: test_case_re.match(f), disk_ids)
        return list(set(disk_ids) - set(db_ids))

    @staticmethod
    def delete_one(id):
        test_case_dir = os.path.join(settings.TEST_CASE_DIR, id)
        if os.path.isdir(test_case_dir):
            shutil.rmtree(test_case_dir, ignore_errors=True)


class DashboardInfoAPI(AsyncAPIView):
    async def get(self, request):
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        (
            user_count,
            today_submission_count,
            recent_contest_count,
            judge_servers,
        ) = await asyncio.gather(
            User.objects.acount(),
            Submission.objects.filter(create_time__gte=today_start).acount(),
            Contest.objects.exclude(end_time__lt=timezone.now()).acount(),
            JudgeServer.objects.filter(last_heartbeat__gte=timezone.now() - timedelta(seconds=6)).acount(),
        )
        return self.success(
            {
                "user_count": user_count,
                "recent_contest_count": recent_contest_count,
                "today_submission_count": today_submission_count,
                "judge_server_count": judge_servers,
                "env": {
                    "FORCE_HTTPS": get_env("FORCE_HTTPS", default=False),
                    "STATIC_CDN_HOST": get_env("STATIC_CDN_HOST", default=""),
                },
            }
        )


class RandomUsernameAPI(AsyncAPIView):
    async def get(self, request):
        classroom = request.GET.get("classroom", "")
        if not classroom:
            return self.error("需要班级号")
        usernames = [u async for u in User.objects.filter(username__istartswith=classroom).values_list("username", flat=True).order_by("?")[:10]]
        return self.success(usernames)


class HitokotoAPI(AsyncAPIView):
    async def get(self, request):
        try:
            categories = JsonDataLoader.load_data(settings.HITOKOTO_DIR, "categories.json")
            path = random.choice(categories).get("path")
            sentences = JsonDataLoader.load_data(settings.HITOKOTO_DIR, path)
            sentence = random.choice(sentences)
            return self.success(sentence)
        except Exception:
            return self.error("获取一言失败，请稍后再试")


class ClassUsernamesAPI(AsyncAPIView):
    async def get(self, request):
        classroom = request.GET.get("classroom", "")
        if not classroom:
            return self.error("需要班级号")
        names = [strip_class_prefix(user.username, classroom) async for user in User.objects.filter(class_name=classroom).order_by("-create_time")]
        return self.success(names)
