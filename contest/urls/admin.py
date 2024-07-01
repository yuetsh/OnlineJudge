from django.urls import path

from ..views.admin import ContestAnnouncementAPI, ContestAPI, ACMContestHelper, DownloadContestSubmissions

urlpatterns = [
    path("contest", ContestAPI.as_view()),
    path("contest/announcement", ContestAnnouncementAPI.as_view()),
    path("contest/acm_helper", ACMContestHelper.as_view()),
    path("download_submissions", DownloadContestSubmissions.as_view()),
]
