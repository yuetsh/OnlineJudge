"""
WebSocket URL Configuration for oj project.
"""

from django.urls import path

from conf.consumers import ConfigConsumer
from flowchart.consumers import FlowchartConsumer
from submission.consumers import SubmissionConsumer

websocket_urlpatterns = [
    path("ws/submission/", SubmissionConsumer.as_asgi()),
    path("ws/config/", ConfigConsumer.as_asgi()),
    path("ws/flowchart/", FlowchartConsumer.as_asgi()),
]
