# coding=utf-8
import os
from utils.shortcuts import get_env

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(BASE_DIR, "db.sqlite3"),
    }
}

REDIS_CONF = {
    "host": get_env("REDIS_HOST", "127.0.0.1"),
    "port": get_env("REDIS_PORT", "6380"),
}


DEBUG = True

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "10.13.114.114",
    "150.158.29.156",
    "oj.xuyue.cc",
    "ojtest.xuyue.cc",
]

CSRF_TRUSTED_ORIGINS = [
    "https://oj.xuyue.cc",
    "https://ojtest.xuyue.cc",
    "http://10.13.114.114:81",
    "http://150.158.29.156:8881",
    "http://localhost:5173",
]


DATA_DIR = f"{BASE_DIR}/data"
