TARGET_LABELS: dict[str, str] = {
    "for_loop": "for 循环",
    "while_loop": "while 循环",
    "if_statement": "if 条件",
    "else_clause": "else 子句",
    "function_definition": "函数定义",
    "return": "return 语句",
    "break": "break 语句",
    "continue": "continue 语句",
    "list_comprehension": "列表推导式",
    "list_literal": "列表",
    "dict_literal": "字典",
    "set_literal": "集合",
    "f_string": "f-string",
    "try_except": "try-except",
    "class_definition": "类定义",
}


def label(target: str) -> str:
    return TARGET_LABELS.get(target, target)
