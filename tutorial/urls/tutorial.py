from django.urls import path

from ..views.oj import ExerciseAPI, TutorialAPI, TutorialTitlesAPI

urlpatterns = [
    path("tutorial", TutorialAPI.as_view()),
    path("tutorials", TutorialTitlesAPI.as_view()),
    path("exercises", ExerciseAPI.as_view()),
]
