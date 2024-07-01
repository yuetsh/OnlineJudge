from django.urls import path

from ..views.admin import SubmissionRejudgeAPI, SubmissionStatisticsAPI

urlpatterns = [
    path("submission/rejudge", SubmissionRejudgeAPI.as_view()),
    path("submission/statistics", SubmissionStatisticsAPI.as_view()),
]
