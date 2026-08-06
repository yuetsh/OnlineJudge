from django.urls import path

from ..views import (
    SMTPAPI,
    DashboardInfoAPI,
    JudgeServerAPI,
    RandomUsernameAPI,
    SMTPTestAPI,
    TestCasePruneAPI,
    WebsiteConfigAPI,
)

urlpatterns = [
    path("smtp", SMTPAPI.as_view()),  # DEPRECATED: 前端未调用
    path("smtp_test", SMTPTestAPI.as_view()),  # DEPRECATED: 前端未调用
    path("website", WebsiteConfigAPI.as_view()),
    path("random_user", RandomUsernameAPI.as_view()),
    path("judge_server", JudgeServerAPI.as_view()),
    path("prune_test_case", TestCasePruneAPI.as_view()),
    path("dashboard_info", DashboardInfoAPI.as_view()),
]
