from django.urls import path
from ..views.oj import (
    FlowchartSubmissionAPI,
    FlowchartSubmissionListAPI,
    FlowchartSubmissionRetryAPI,
    FlowchartSubmissionCurrentAPI,
    FlowchartSubmissionDetailAPI,
)

urlpatterns = [
    path('flowchart/submission', FlowchartSubmissionAPI.as_view()),
    path('flowchart/submissions', FlowchartSubmissionListAPI.as_view()),
    path('flowchart/submission/retry', FlowchartSubmissionRetryAPI.as_view()),
    path('flowchart/submission/detail', FlowchartSubmissionDetailAPI.as_view()),
    path('flowchart/submission/current', FlowchartSubmissionCurrentAPI.as_view()),
]
