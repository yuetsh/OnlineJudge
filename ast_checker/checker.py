from tree_sitter import Parser

from .engines import get_engine
from .mappings import get_language, get_mapping


def check_ast(code: str, language: str, rules: list[dict]) -> tuple[bool, list[str]]:
    if not rules:
        return True, []

    ts_language = get_language(language)
    if ts_language is None:
        return True, []

    mapping = get_mapping(language)

    try:
        parser = Parser(ts_language)
        tree = parser.parse(code.encode("utf-8"))
    except Exception:
        return True, []

    errors = []
    for rule in rules:
        engine = get_engine(rule.get("engine", ""))
        if engine is None:
            continue
        rule_errors = engine.check(tree, rule, language, mapping)
        errors.extend(rule_errors)

    return len(errors) == 0, errors
