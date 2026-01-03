from django.urls import path

from ..views.oj import ClassRankAPI, UserClassRankAPI, ClassPKAPI

urlpatterns = [
    path("class_rank", ClassRankAPI.as_view()),
    path("user_class_rank", UserClassRankAPI.as_view()),
    path("class_pk", ClassPKAPI.as_view()),
]

