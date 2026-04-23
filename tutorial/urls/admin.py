from django.urls import path
from ..views.admin import TutorialAdminAPI, TutorialVisibilityAPI, ExerciseAdminAPI

urlpatterns = [
    path("tutorial", TutorialAdminAPI.as_view()),
    path("tutorial/visibility", TutorialVisibilityAPI.as_view()),
    path("exercise", ExerciseAdminAPI.as_view()),
]
