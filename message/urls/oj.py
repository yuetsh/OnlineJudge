from django.urls import path

from ..views.oj import MessageAPI

urlpatterns = [
    path("message", MessageAPI.as_view()),
]
