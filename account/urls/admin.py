from django.urls import path

from ..views.admin import ResetUserPasswordAPI, UserAdminAPI

urlpatterns = [
    path("user", UserAdminAPI.as_view()),
    path("reset_password", ResetUserPasswordAPI.as_view()),
]
