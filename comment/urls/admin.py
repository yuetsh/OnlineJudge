from django.urls import path

from ..views.admin import CommentAPI


urlpatterns = [
    path("comment", CommentAPI.as_view()),
]
