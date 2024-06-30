from django.urls import re_path as url

from ..views.oj import CommentAPI, CommentStatisticsAPI


urlpatterns = [
    url(r"^comment/?$", CommentAPI.as_view(), name="comment_api"),
    url(r"^comment/statistics?$", CommentStatisticsAPI.as_view(), name="comment_statistics_api"),
]
