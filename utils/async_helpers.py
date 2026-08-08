from django.core.cache import cache


async def async_cache_get(key, default=None):
    return await cache.aget(key, default)


async def async_cache_set(key, value, timeout=None):
    return await cache.aset(key, value, timeout)

