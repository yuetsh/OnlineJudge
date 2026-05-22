from django.urls import path

from ..views.admin import ACMContestHelper, ContestAnnouncementAPI, ContestAPI, ContestCloneAPI, DownloadContestSubmissions

urlpatterns = [
    path("contest", ContestAPI.as_view()),
    path("contest/clone", ContestCloneAPI.as_view()),
    path("contest/announcement", ContestAnnouncementAPI.as_view()),
    path("contest/acm_helper", ACMContestHelper.as_view()),
    path("download_submissions", DownloadContestSubmissions.as_view()),
]
