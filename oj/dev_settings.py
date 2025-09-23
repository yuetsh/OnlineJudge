# coding=utf-8
import os
from utils.shortcuts import get_env

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": "150.158.29.156",
        "PORT": "5432",
        "NAME": "onlinejudge",
        "USER": "onlinejudge",
        "PASSWORD": "onlinejudge",
    }
}

REDIS_CONF = {
    "host": "150.158.29.156",
    "port": 6379,
}


DEBUG = True

ALLOWED_HOSTS = ["*"]

CSRF_TRUSTED_ORIGINS = ["http://localhost:5173"]

DATA_DIR = f"{BASE_DIR}/data"
