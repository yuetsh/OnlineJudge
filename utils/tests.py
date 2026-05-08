from types import SimpleNamespace
from unittest import TestCase

from django.conf import settings

if not settings.configured:
    settings.configure(
        DJANGO_REDIS_CONNECTION_FACTORY="django_redis.pool.ConnectionFactory",
    )

from utils.cache import MyRedisClient
from utils.throttling import TokenBucket


class FakeRedis:
    def __init__(self):
        self.hashes = {}

    def hset(self, name, key, value):
        self.hashes.setdefault(str(name), {})[str(key)] = value
        return 1

    def hget(self, name, key):
        return self.hashes.get(str(name), {}).get(str(key))


def make_client():
    backend = SimpleNamespace(
        key_prefix="",
        version=1,
        key_func=lambda key, key_prefix, version: key,
    )
    client = MyRedisClient("redis://localhost:6379/0", {}, backend)
    fake_redis = FakeRedis()
    client.get_client = lambda write=True: fake_redis
    return client


class TokenBucketCacheTests(TestCase):
    def test_token_bucket_reads_values_written_through_django_redis_hash_api(self):
        bucket = TokenBucket(
            key="submission:user:1",
            capacity=2,
            fill_rate=0.1,
            default_capacity=2,
            redis_conn=make_client(),
        )

        self.assertEqual(bucket.consume(), (True, 0))
        self.assertEqual(bucket.consume(), (True, 0))
