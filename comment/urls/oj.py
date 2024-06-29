from django.urls import re_path as url

from ..views.oj import CommentAPI


urlpatterns = [
    url(r"^comment/?$", CommentAPI.as_view(), name="comment_api"),
]
