from django.urls import path

from ..views.oj import ReactionAPI

urlpatterns = [
    path("reaction", ReactionAPI.as_view()),
]
