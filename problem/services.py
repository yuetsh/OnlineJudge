from django.core.cache import cache
from django.db import IntegrityError, transaction

from utils.constants import CacheKey

from .models import ProblemTag


def clear_tag_cache():
    """标签列表接口按 keyword 分键缓存，标签一变就整批清掉"""
    cache.delete_pattern(f"{CacheKey.problem_tags}:*")


def find_tags(names):
    """按名字大小写不敏感查已有标签，查不到就跳过，不创建"""
    tags = []
    seen = set()
    for raw in names:
        name = (raw or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        tag = ProblemTag.objects.filter(name__iexact=name).first()
        if tag is not None:
            tags.append(tag)
    return tags


def resolve_tags(names):
    """把前端传来的标签名解析成 ProblemTag：去空格、大小写不敏感复用已有标签，没有才新建"""
    tags = []
    seen = set()
    created = False
    for raw in names:
        name = (raw or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        tag = ProblemTag.objects.filter(name__iexact=name).first()
        if tag is None:
            try:
                # 包一层 atomic：外层若在事务里，IntegrityError 会中止整个事务，
                # 导致下面的回查抛 TransactionManagementError
                with transaction.atomic():
                    tag = ProblemTag.objects.create(name=name)
                created = True
            except IntegrityError:
                # 并发下另一个请求刚建好同名标签，回查复用
                tag = ProblemTag.objects.filter(name__iexact=name).first()
                if tag is None:
                    continue
        tags.append(tag)
    if created:
        clear_tag_cache()
    return tags
