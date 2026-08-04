from django.urls import path

from achievement.views.admin import AchievementAdminAPI, AchievementMetricAdminAPI

urlpatterns = [
    path("achievement", AchievementAdminAPI.as_view(), name="achievement_admin_api"),
    path("achievement/metrics", AchievementMetricAdminAPI.as_view(), name="achievement_metric_admin_api"),
]
