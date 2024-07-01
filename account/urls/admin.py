from django.urls import path

from ..views.admin import UserAdminAPI, GenerateUserAPI

urlpatterns = [
    path("user", UserAdminAPI.as_view()),
    path("generate_user", GenerateUserAPI.as_view()),
]
