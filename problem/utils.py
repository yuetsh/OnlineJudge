import json
import os
import re
from functools import lru_cache

from django.conf import settings

from judge.sql_runner import SQLCaseError, build_display
from utils.shortcuts import natural_sort_key

TEMPLATE_BASE = """//PREPEND BEGIN
{}
//PREPEND END

//TEMPLATE BEGIN
{}
//TEMPLATE END

//APPEND BEGIN
{}
//APPEND END"""


@lru_cache(maxsize=100)
def parse_problem_template(template_str):
    prepend = re.findall(r"//PREPEND BEGIN\n([\s\S]+?)//PREPEND END", template_str)
    template = re.findall(r"//TEMPLATE BEGIN\n([\s\S]+?)//TEMPLATE END", template_str)
    append = re.findall(r"//APPEND BEGIN\n([\s\S]+?)//APPEND END", template_str)
    return {"prepend": prepend[0] if prepend else "", "template": template[0] if template else "", "append": append[0] if append else ""}


def generate_sql_display(test_case_id, answers, sql_config):
    """SQL 题：用测试点1的初始化脚本 + 标准答案生成题目页展示数据。

    返回 (sql_display, error)：成功时 error 为 None，失败时 sql_display 为 None、error 为中文提示。
    """
    test_case_dir = os.path.join(settings.TEST_CASE_DIR, test_case_id)
    try:
        with open(os.path.join(test_case_dir, "info"), encoding="utf-8") as f:
            info = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None, "测试点信息读取失败，请重新上传测试点"
    if not info.get("sql"):
        return None, "测试点不是 SQL 类型，请重新上传 SQL 测试点压缩包"
    try:
        keys = sorted(info["test_cases"].keys(), key=natural_sort_key)
        if not keys:
            return None, "题目没有任何测试点"
        input_name = info["test_cases"][keys[0]]["input_name"]
    except (KeyError, AttributeError, TypeError):
        return None, "测试点信息损坏，请重新上传测试点"
    try:
        with open(os.path.join(test_case_dir, input_name), encoding="utf-8") as f:
            init_sql = f.read()
    except OSError:
        return None, f"测试点脚本 {input_name} 读取失败"
    ref_sql = next((item["code"] for item in answers or [] if item.get("language") == "SQL" and item.get("code", "").strip()), None)
    if ref_sql is None:
        return None, "题目缺少 SQL 标准答案"
    try:
        return build_display(init_sql, ref_sql, sql_config["mode"]), None
    except SQLCaseError as e:
        return None, f"SQL 展示数据生成失败: {e.message}"
