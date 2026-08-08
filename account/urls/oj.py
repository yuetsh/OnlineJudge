from django.urls import path

from ..views.oj import (
    AvatarUploadAPI,
    Metrics,
    ProfileProblemDisplayIDRefreshAPI,
    UserActivityRankAPI,
    UserLoginAPI,
    UserLogoutAPI,
    UserProblemRankAPI,
    UserProfileAPI,
    UserRankAPI,
    UserRegisterAPI,
)

urlpatterns = [
    path("login", UserLoginAPI.as_view()),
    path("logout", UserLogoutAPI.as_view()),
    path("register", UserRegisterAPI.as_view()),
    path("profile", UserProfileAPI.as_view(), name="user_profile_api"),
    path("profile/fresh_display_id", ProfileProblemDisplayIDRefreshAPI.as_view()),
    path("metrics", Metrics.as_view()),
    path("upload_avatar", AvatarUploadAPI.as_view()),
    path("user_rank", UserRankAPI.as_view()),
    path("user_activity_rank", UserActivityRankAPI.as_view()),
    path("user_problem_rank", UserProblemRankAPI.as_view()),
]
