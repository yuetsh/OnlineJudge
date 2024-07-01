from django.urls import path

from ..views.oj import SubmissionAPI, SubmissionListAPI, ContestSubmissionListAPI, SubmissionExistsAPI

urlpatterns = [
    path("submission", SubmissionAPI.as_view()),
    path("submissions", SubmissionListAPI.as_view()),
    path("submission_exists", SubmissionExistsAPI.as_view()),
    path("contest_submissions", ContestSubmissionListAPI.as_view()),
]
