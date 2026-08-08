from django.urls import path

from ..views.admin import ACMContestHelper, ContestAPI, ContestCloneAPI

urlpatterns = [
    path("contest", ContestAPI.as_view()),
    path("contest/clone", ContestCloneAPI.as_view()),
    path("contest/acm_helper", ACMContestHelper.as_view()),
]
