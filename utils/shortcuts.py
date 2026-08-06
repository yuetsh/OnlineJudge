import os
import random
import re

from django.utils.crypto import get_random_string

# 班级号的位数范围。学生用户名形如 ks<班级号><姓名>，班级号还要跟
# SysOptions.class_list 的条目、User.class_name 字段对得上。
# 改这里等于改全站规则，前端 ojnext/src/utils/constants.ts 里
# CLASS_NAME_DIGITS 是同一条规则的另一份，两边要一起改。
CLASS_NAME_MIN_DIGITS = 3
CLASS_NAME_MAX_DIGITS = 4
CLASS_NAME_RE = re.compile(rf"\d{{{CLASS_NAME_MIN_DIGITS},{CLASS_NAME_MAX_DIGITS}}}")


def is_valid_class_name(class_name):
    """班级号是否是合法位数的纯数字"""
    return bool(CLASS_NAME_RE.fullmatch(class_name))


def rand_str(length=32, type="lower_hex"):
    """
    生成指定长度的随机字符串或者数字, 可以用于密钥等安全场景
    :param length: 字符串或者数字的长度
    :param type: str 代表随机字符串，num 代表随机数字
    :return: 字符串
    """
    if type == "str":
        return get_random_string(length, allowed_chars="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")
    elif type == "lower_str":
        return get_random_string(length, allowed_chars="abcdefghijklmnopqrstuvwxyz0123456789")
    elif type == "lower_hex":
        return random.choice("123456789abcdef") + get_random_string(length - 1, allowed_chars="0123456789abcdef")
    else:
        return random.choice("123456789") + get_random_string(length - 1, allowed_chars="0123456789")


def build_query_string(kv_data, ignore_none=True):
    # {"a": 1, "b": "test"} -> "?a=1&b=test"
    query_string = ""
    for k, v in kv_data.items():
        if ignore_none is True and kv_data[k] is None:
            continue
        if query_string != "":
            query_string += "&"
        else:
            query_string = "?"
        query_string += k + "=" + str(v)
    return query_string


def strip_class_prefix(username, class_name):
    """
    去掉用户名里的 ks<班级号> 前缀，得到学生本人那一段。
    用户名形如 ks251张三，class_name 为 251 时返回 张三。

    用 removeprefix 而不是按长度切片：前缀对不上时原样返回，
    不会从中间截出乱码。
    """
    if not class_name:
        return username
    return username.removeprefix(f"ks{class_name}")


def datetime2str(value, format="iso-8601"):
    if format.lower() == "iso-8601":
        value = value.isoformat()
        if value.endswith("+00:00"):
            value = value[:-6] + "Z"
        return value
    return value.strftime(format)


def natural_sort_key(s, _nsre=re.compile(r"(\d+)")):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(_nsre, s)]


def get_env(name, default=""):
    return os.environ.get(name, default)


def DRAMATIQ_WORKER_ARGS(time_limit=3600_000, max_retries=0, max_age=7200_000):
    return {"max_retries": max_retries, "time_limit": time_limit, "max_age": max_age}


def check_is_id(value):
    try:
        return int(value) > 0
    except Exception:
        return False
