from django.urls import re_path as url

from ..views.oj import AnnouncementAPI, MessageAPI

urlpatterns = [
    url(r"^announcement/?$", AnnouncementAPI.as_view(), name="announcement_api"),
    url(r"^message/?$", MessageAPI.as_view(), name="message_api"),
]
