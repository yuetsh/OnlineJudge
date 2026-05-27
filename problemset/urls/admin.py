from django.urls import path

from problemset.views.admin import (
    ProblemSetAdminAPI,
    ProblemSetBadgeAdminAPI,
    ProblemSetDetailAdminAPI,
    ProblemSetProblemAdminAPI,
    ProblemSetProgressAdminAPI,
    ProblemSetStatusAPI,
    ProblemSetSyncAPI,
    ProblemSetVisibleAPI,
)

urlpatterns = [
    # 管理员题单管理API
    path("problemset", ProblemSetAdminAPI.as_view(), name="admin_problemset_api"),
    # 题单状态管理API — 必须在 <int:problem_set_id> 之前，否则被整数路由遮蔽
    path(
        "problemset/visible",
        ProblemSetVisibleAPI.as_view(),
        name="admin_problemset_visible_api",
    ),
    path(
        "problemset/status",
        ProblemSetStatusAPI.as_view(),
        name="admin_problemset_status_api",
    ),
    path(
        "problemset/<int:problem_set_id>",
        ProblemSetDetailAdminAPI.as_view(),
        name="admin_problemset_detail_api",
    ),
    path(
        "problemset/<int:problem_set_id>/problems",
        ProblemSetProblemAdminAPI.as_view(),
        name="admin_problemset_problems_api",
    ),
    path(
        "problemset/<int:problem_set_id>/problems/<int:problem_set_problem_id>",
        ProblemSetProblemAdminAPI.as_view(),
        name="admin_problemset_problem_detail_api",
    ),
    # 管理员奖章管理API
    path(
        "problemset/<int:problem_set_id>/badges",
        ProblemSetBadgeAdminAPI.as_view(),
        name="admin_problemset_badges_api",
    ),
    path(
        "problemset/<int:problem_set_id>/badges/<int:badge_id>",
        ProblemSetBadgeAdminAPI.as_view(),
        name="admin_problemset_badge_detail_api",
    ),
    # 管理员进度管理API
    path(
        "problemset/<int:problem_set_id>/progress",
        ProblemSetProgressAdminAPI.as_view(),
        name="admin_problemset_progress_api",
    ),
    path(
        "problemset/<int:problem_set_id>/progress/<int:user_id>",
        ProblemSetProgressAdminAPI.as_view(),
        name="admin_problemset_progress_detail_api",
    ),
    # 题单同步管理API
    path(  # DEPRECATED: 前端未调用
        "problemset/<int:problem_set_id>/sync",
        ProblemSetSyncAPI.as_view(),
        name="admin_problemset_sync_api",
    ),
]
