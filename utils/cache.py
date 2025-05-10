import json
from pathlib import Path
from django.core.cache import cache

from django_redis.cache import RedisCache
from django_redis.client.default import DefaultClient


class MyRedisClient(DefaultClient):
    def __getattr__(self, item):
        client = self.get_client(write=True)
        return getattr(client, item)

    def redis_incr(self, key, count=1):
        """
        django 默认的 incr 在 key 不存在时候会抛异常
        """
        client = self.get_client(write=True)
        return client.incr(key, count)


class MyRedisCache(RedisCache):
    def __init__(self, server, params):
        super().__init__(server, params)
        self._client_cls = MyRedisClient

    def __getattr__(self, item):
        return getattr(self.client, item)


class JsonDataLoader:
    @classmethod
    def load_data(cls, dir, filename):
        cache_key = f"json_data_{filename}"
        if cached := cache.get(cache_key):
            return cached

        file_path = Path(dir, filename)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                cache.set(cache_key, data, timeout=7200)
                return data
        except FileNotFoundError:
            raise ValueError(f"Data file {filename} not found")
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON format in {filename}")
