from django.urls import path

from ..views.admin import ReactionStatsAPI

urlpatterns = [
    path("reaction", ReactionStatsAPI.as_view()),
]
