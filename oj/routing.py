"""
WebSocket URL Configuration for oj project.
"""

from django.urls import path
from submission.consumers import SubmissionConsumer
from conf.consumers import ConfigConsumer

websocket_urlpatterns = [
    path("ws/submission/", SubmissionConsumer.as_asgi()),
    path("ws/config/", ConfigConsumer.as_asgi()),
]

