from django.urls import re_path as url

from ..views.admin import SubmissionRejudgeAPI, SubmissionStatisticsAPI

urlpatterns = [
    url(r"^submission/rejudge?$", SubmissionRejudgeAPI.as_view(), name="submission_rejudge_api"),
    url(r"^submission/statistics?$", SubmissionStatisticsAPI.as_view(), name="submission_statistics_api"),
]
