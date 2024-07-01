from django.urls import path

from ..views.oj import ContestAnnouncementListAPI
from ..views.oj import ContestPasswordVerifyAPI, ContestAccessAPI
from ..views.oj import ContestListAPI, ContestAPI
from ..views.oj import ContestRankAPI

urlpatterns = [
    path("contests", ContestListAPI.as_view()),
    path("contest", ContestAPI.as_view()),
    path("contest/password", ContestPasswordVerifyAPI.as_view()),
    path("contest/announcement", ContestAnnouncementListAPI.as_view()),
    path("contest/access", ContestAccessAPI.as_view()),
    path("contest_rank", ContestRankAPI.as_view()),
]
