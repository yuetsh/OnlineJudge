from django.urls import path

from ..views.oj import (
    AIAnalysisAPI,
    AIDetailDataAPI,
    AIDurationDataAPI,
    AIHeatmapDataAPI,
    AIHintAPI,
    AILoginSummaryAPI,
    AIPinnedReportAPI,
    ClassPKAnalysisAPI,
    SingleClassAnalysisAPI,
)

urlpatterns = [
    path("ai/detail", AIDetailDataAPI.as_view()),
    path("ai/duration", AIDurationDataAPI.as_view()),
    path("ai/analysis", AIAnalysisAPI.as_view()),
    path("ai/hint", AIHintAPI.as_view()),
    path("ai/heatmap", AIHeatmapDataAPI.as_view()),
    path("ai/login_summary", AILoginSummaryAPI.as_view()),
    path("ai/pinned", AIPinnedReportAPI.as_view()),
    path("ai/class_pk", ClassPKAnalysisAPI.as_view()),
    path("ai/class_single", SingleClassAnalysisAPI.as_view()),
]
