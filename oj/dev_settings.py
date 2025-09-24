# coding=utf-8
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": "10.13.114.114",
        "PORT": "5433",
        "NAME": "onlinejudge",
        "USER": "onlinejudge",
        "PASSWORD": "onlinejudge",
    }
}

REDIS_CONF = {
    "host": "10.13.114.114",
    "port": 6379,
}


DEBUG = True

ALLOWED_HOSTS = ["*"]

CSRF_TRUSTED_ORIGINS = ["http://localhost:5173"]

DATA_DIR = f"{BASE_DIR}/data"
