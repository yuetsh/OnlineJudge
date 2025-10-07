"""
ASGI config for oj project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from utils.shortcuts import get_env

production_env = get_env("OJ_ENV", "dev") == "production"
if production_env:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oj.production_settings")
else:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oj.dev_settings")

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

# Import routing after Django setup
from oj.routing import websocket_urlpatterns

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)

