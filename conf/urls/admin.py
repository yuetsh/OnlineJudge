from django.urls import path

from ..views import SMTPAPI, JudgeServerAPI, WebsiteConfigAPI, TestCasePruneAPI, SMTPTestAPI
from ..views import ReleaseNotesAPI, DashboardInfoAPI

urlpatterns = [
    path("smtp", SMTPAPI.as_view()),
    path("smtp_test", SMTPTestAPI.as_view()),
    path("website", WebsiteConfigAPI.as_view()),
    path("judge_server", JudgeServerAPI.as_view()),
    path("prune_test_case", TestCasePruneAPI.as_view()),
    path("versions", ReleaseNotesAPI.as_view()),
    path("dashboard_info", DashboardInfoAPI.as_view()),
]
