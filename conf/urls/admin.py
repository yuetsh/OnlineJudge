from django.urls import path

from ..views import (
    DashboardInfoAPI,
    JudgeServerAPI,
    RandomUsernameAPI,
    TestCasePruneAPI,
    WebsiteConfigAPI,
)

urlpatterns = [
    path("website", WebsiteConfigAPI.as_view()),
    path("random_user", RandomUsernameAPI.as_view()),
    path("judge_server", JudgeServerAPI.as_view()),
    path("prune_test_case", TestCasePruneAPI.as_view()),
    path("dashboard_info", DashboardInfoAPI.as_view()),
]
