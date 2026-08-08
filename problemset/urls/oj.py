from django.urls import path

from problemset.views.oj import (
    ProblemSetAPI,
    ProblemSetBadgeAPI,
    ProblemSetDetailAPI,
    ProblemSetProblemAPI,
    ProblemSetProgressAPI,
    ProblemSetUserProgressAPI,
    UserBadgeAPI,
)

urlpatterns = [
    # 题单相关API
    path("problemset", ProblemSetAPI.as_view(), name="problemset_api"),
    path(
        "problemset/<int:problem_set_id>",
        ProblemSetDetailAPI.as_view(),
        name="problemset_detail_api",
    ),
    path(
        "problemset/<int:problem_set_id>/problems",
        ProblemSetProblemAPI.as_view(),
        name="problemset_problems_api",
    ),
    # 进度相关API
    path(
        "problemset/progress",
        ProblemSetProgressAPI.as_view(),
        name="problemset_progress_api",
    ),
    # 奖章相关API
    path("user/badges", UserBadgeAPI.as_view(), name="user_badges_api"),
    path(
        "problemset/<int:problem_set_id>/badges",
        ProblemSetBadgeAPI.as_view(),
        name="problemset_badges_api",
    ),
    path(
        "problemset/<int:problem_set_id>/users_progress",
        ProblemSetUserProgressAPI.as_view(),
        name="problemset_user_progress_api",
    ),
]
