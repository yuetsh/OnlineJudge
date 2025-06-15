from django.urls import path
from ..views.admin import TutorialAdminAPI, TutorialVisibilityAPI

urlpatterns = [
    path("tutorial", TutorialAdminAPI.as_view()),
    path(
        "tutorial/visibility",
        TutorialVisibilityAPI.as_view(),
    ),
]
