from django.urls import path

from ..views.oj import (
    AIAnalysisAPI,
    AIDetailDataAPI,
    AIWeeklyDataAPI,
    AIHeatmapDataAPI,
)

urlpatterns = [
    path("ai/detail", AIDetailDataAPI.as_view()),
    path("ai/weekly", AIWeeklyDataAPI.as_view()),
    path("ai/analysis", AIAnalysisAPI.as_view()),
    path("ai/heatmap", AIHeatmapDataAPI.as_view()),
]
