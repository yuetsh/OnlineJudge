from django.urls import path
from problemset.views.oj import (
    ProblemSetAPI,
    ProblemSetDetailAPI,
    ProblemSetProblemAPI,
    ProblemSetProgressAPI,
    UserBadgeAPI,
    UserProgressAPI,
    ProblemSetBadgeAPI,
    ProblemSetSubmissionAPI,
    ProblemSetStatisticsAPI,
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
    path(
        "problemset/<int:problem_set_id>/problems/<int:problem_id>",
        ProblemSetProblemAPI.as_view(),
        name="problemset_problem_detail_api",
    ),
    # 进度相关API
    path(
        "problemset/progress",
        ProblemSetProgressAPI.as_view(),
        name="problemset_progress_api",
    ),
    path(
        "problemset/<int:problem_set_id>/progress",
        ProblemSetProgressAPI.as_view(),
        name="problemset_progress_detail_api",
    ),
    path("user/progress", UserProgressAPI.as_view(), name="user_progress_api"),
    # 奖章相关API
    path("user/badges", UserBadgeAPI.as_view(), name="user_badges_api"),
    path(
        "user/badges/<int:badge_id>",
        UserBadgeAPI.as_view(),
        name="user_badge_detail_api",
    ),
    path(
        "problemset/<int:problem_set_id>/badges",
        ProblemSetBadgeAPI.as_view(),
        name="problemset_badges_api",
    ),
    # 提交记录相关API
    path(
        "problemset/<int:problem_set_id>/submissions",
        ProblemSetSubmissionAPI.as_view(),
        name="problemset_submissions_api",
    ),
    # 统计相关API
    path(
        "problemset/<int:problem_set_id>/statistics",
        ProblemSetStatisticsAPI.as_view(),
        name="problemset_statistics_api",
    ),
]
