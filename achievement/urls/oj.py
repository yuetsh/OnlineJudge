from django.urls import path

from achievement.views.oj import AchievementListAPI, AchievementPendingAPI, AchievementSummaryAPI

urlpatterns = [
    path("achievements", AchievementListAPI.as_view(), name="achievement_list_api"),
    path("achievements/summary", AchievementSummaryAPI.as_view(), name="achievement_summary_api"),
    path("achievements/pending", AchievementPendingAPI.as_view(), name="achievement_pending_api"),
]
