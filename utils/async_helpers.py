from asgiref.sync import sync_to_async
from django.core.cache import cache


async def async_cache_get(key, default=None):
    return await sync_to_async(cache.get, thread_sensitive=True)(key, default)


async def async_cache_set(key, value, timeout=None):
    return await sync_to_async(cache.set, thread_sensitive=True)(key, value, timeout)


async def async_cache_delete(key):
    return await sync_to_async(cache.delete, thread_sensitive=True)(key)
