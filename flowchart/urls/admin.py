from django.urls import path

from ..views.admin import FlowchartStatisticsAPI

urlpatterns = [
    path("flowchart/statistics", FlowchartStatisticsAPI.as_view()),
]
