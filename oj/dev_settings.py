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

ALLOWED_HOSTS = ["*"]

CSRF_TRUSTED_ORIGINS = ["http://localhost:5173", "https://ojtest.xuyue.cc"]

DATA_DIR = f"{BASE_DIR}/data"
