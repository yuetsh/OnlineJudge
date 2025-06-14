from utils.shortcuts import get_env

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": get_env("POSTGRES_HOST", "oj-postgres"),
        "PORT": get_env("POSTGRES_PORT", "5432"),
        "NAME": get_env("POSTGRES_DB"),
        "USER": get_env("POSTGRES_USER"),
        "PASSWORD": get_env("POSTGRES_PASSWORD"),
    }
}

REDIS_CONF = {
    "host": get_env("REDIS_HOST", "oj-redis"),
    "port": get_env("REDIS_PORT", "6379"),
}

DEBUG = False

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

DATA_DIR = "/data"
