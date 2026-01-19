from django.urls import path

from ..views import (
    HitokotoAPI,
    JudgeServerHeartbeatAPI,
    LanguagesAPI,
    WebsiteConfigAPI,
    ClassUsernamesAPI,
)

urlpatterns = [
    path("website", WebsiteConfigAPI.as_view()),
    # 这里必须要有 /
    path("judge_server_heartbeat/", JudgeServerHeartbeatAPI.as_view()),
    path("languages", LanguagesAPI.as_view()),
    path("hitokoto", HitokotoAPI.as_view()),
    path("class_usernames", ClassUsernamesAPI.as_view()),
]
