from django.urls import path

from ..views.oj import (ApplyResetPasswordAPI, ResetPasswordAPI,
                        UserChangePasswordAPI, UserRegisterAPI, UserChangeEmailAPI,
                        UserLoginAPI, UserLogoutAPI, UsernameOrEmailCheck,
                        AvatarUploadAPI, TwoFactorAuthAPI, UserProfileAPI,
                        UserRankAPI, CheckTFARequiredAPI, SessionManagementAPI,
                        ProfileProblemDisplayIDRefreshAPI, OpenAPIAppkeyAPI, SSOAPI)

from utils.captcha.views import CaptchaAPIView

urlpatterns = [
    path("login", UserLoginAPI.as_view()),
    path("logout", UserLogoutAPI.as_view()),
    path("register", UserRegisterAPI.as_view()),
    path("change_password", UserChangePasswordAPI.as_view()),
    path("change_email", UserChangeEmailAPI.as_view()),
    path("apply_reset_password", ApplyResetPasswordAPI.as_view()),
    path("reset_password", ResetPasswordAPI.as_view()),
    path("captcha", CaptchaAPIView.as_view()),
    path("check_username_or_email", UsernameOrEmailCheck.as_view()),
    path("profile", UserProfileAPI.as_view(), name="user_profile_api"),
    path("profile/fresh_display_id", ProfileProblemDisplayIDRefreshAPI.as_view()),
    path("upload_avatar", AvatarUploadAPI.as_view()),
    path("tfa_required", CheckTFARequiredAPI.as_view()),
    path("two_factor_auth", TwoFactorAuthAPI.as_view(),),
    path("user_rank", UserRankAPI.as_view()),
    path("sessions", SessionManagementAPI.as_view()),
    path("open_api_appkey", OpenAPIAppkeyAPI.as_view(),),
    path("sso", SSOAPI.as_view())
]
