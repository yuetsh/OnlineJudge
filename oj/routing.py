"""
WebSocket URL Configuration for oj project.
"""

from django.urls import path
from submission.consumers import SubmissionConsumer

websocket_urlpatterns = [
    path("ws/submission/", SubmissionConsumer.as_asgi()),
]

