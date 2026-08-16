import json
from pathlib import Path

# 本模块自己不再用它，但 judge/dispatcher.py 和 submission/views/oj.py 是
# `from utils.cache import cache` 拿的，删掉会连带炸两个模块
from django.core.cache import cache  # noqa: F401
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
    """只读 json 数据集的加载器（目前只有一言）。

    缓存放在进程内，不进 Redis：这些文件是随镜像/数据目录一起发布的只读数据，
    永远不会在运行期变化，没有跨进程共享的必要。原先塞 Redis 的写法，每次命中都要
    把整份 json（最大的一个分类 pickle 后 323KB）拉过网络再反序列化一遍 ——
    比直接读本地盘还慢，而且和 session 挤在同一个 Redis db 里。

    全部 12 个分类都加载后，每个 gunicorn worker 常驻约 6.6MB。
    """

    _cache = {}

    @classmethod
    def load_data(cls, dir, filename):
        cache_key = (str(dir), filename)
        if (cached := cls._cache.get(cache_key)) is not None:
            return cached

        file_path = Path(dir, filename)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                cls._cache[cache_key] = data
                return data
        except FileNotFoundError:
            raise ValueError(f"Data file {filename} not found")
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON format in {filename}")
