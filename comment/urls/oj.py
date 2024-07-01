from django.urls import path

from ..views.oj import CommentAPI, CommentStatisticsAPI


urlpatterns = [
    path("comment", CommentAPI.as_view()),
    path("comment/statistics", CommentStatisticsAPI.as_view()),
]
