from django.urls import path

from utils.captcha.views import CaptchaAPIView

from ..views.oj import (
    SSOAPI,
    ApplyResetPasswordAPI,
    AvatarUploadAPI,
    Metrics,
    OpenAPIAppkeyAPI,
    ProfileProblemDisplayIDRefreshAPI,
    ResetPasswordAPI,
    SessionManagementAPI,
    UserActivityRankAPI,
    UserChangeEmailAPI,
    UserChangePasswordAPI,
    UserLoginAPI,
    UserLogoutAPI,
    UsernameOrEmailCheck,
    UserProblemRankAPI,
    UserProfileAPI,
    UserRankAPI,
    UserRegisterAPI,
)

urlpatterns = [
    path("login", UserLoginAPI.as_view()),
    path("logout", UserLogoutAPI.as_view()),
    path("register", UserRegisterAPI.as_view()),
    path("change_password", UserChangePasswordAPI.as_view()),  # DEPRECATED: 前端未调用
    path("change_email", UserChangeEmailAPI.as_view()),  # DEPRECATED: 前端未调用
    path("apply_reset_password", ApplyResetPasswordAPI.as_view()),  # DEPRECATED: 前端未调用
    path("reset_password", ResetPasswordAPI.as_view()),  # DEPRECATED: 前端未调用
    path("captcha", CaptchaAPIView.as_view()),
    path("check_username_or_email", UsernameOrEmailCheck.as_view()),  # DEPRECATED: 前端未调用
    path("profile", UserProfileAPI.as_view(), name="user_profile_api"),
    path("profile/fresh_display_id", ProfileProblemDisplayIDRefreshAPI.as_view()),
    path("metrics", Metrics.as_view()),
    path("upload_avatar", AvatarUploadAPI.as_view()),
    path("user_rank", UserRankAPI.as_view()),
    path("user_activity_rank", UserActivityRankAPI.as_view()),
    path("user_problem_rank", UserProblemRankAPI.as_view()),
    path("sessions", SessionManagementAPI.as_view()),  # DEPRECATED: 前端未调用
    path(
        "open_api_appkey",  # DEPRECATED: 前端未调用
        OpenAPIAppkeyAPI.as_view(),
    ),
    path("sso", SSOAPI.as_view()),  # DEPRECATED: 前端未调用
]
