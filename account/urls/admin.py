from django.urls import path

from ..views.admin import GenerateUserAPI, ResetUserPasswordAPI, UserAdminAPI

urlpatterns = [
    path("user", UserAdminAPI.as_view()),
    path("generate_user", GenerateUserAPI.as_view()),
    path("reset_password", ResetUserPasswordAPI.as_view()),
]
