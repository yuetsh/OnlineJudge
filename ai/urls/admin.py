from django.urls import path

from ..views.admin import AIAnalysisAdminAPI

urlpatterns = [
    path("ai/reports", AIAnalysisAdminAPI.as_view()),
]
