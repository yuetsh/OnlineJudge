from django.urls import re_path as url

from ..views.oj import MessageAPI

urlpatterns = [
    url(r"^message/?$", MessageAPI.as_view(), name="message_api"),
]
