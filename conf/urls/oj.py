from django.urls import path

from ..views import JudgeServerHeartbeatAPI, LanguagesAPI, WebsiteConfigAPI

urlpatterns = [
    path("website", WebsiteConfigAPI.as_view()),
    # 这里必须要有 /
    path("judge_server_heartbeat/", JudgeServerHeartbeatAPI.as_view()),
    path("languages", LanguagesAPI.as_view())
]
