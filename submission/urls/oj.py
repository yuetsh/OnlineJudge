from django.urls import path

from ..views.oj import (
    ContestSubmissionListAPI,
    FormatCodeAPI,
    SubmissionAPI,
    SubmissionListAPI,
    SubmissionsTodayCount,
)

urlpatterns = [
    path("submission", SubmissionAPI.as_view()),
    path("submissions", SubmissionListAPI.as_view()),
    path("submissions/today_count", SubmissionsTodayCount.as_view()),
    path("contest_submissions", ContestSubmissionListAPI.as_view()),
    path("format_code", FormatCodeAPI.as_view()),
]
