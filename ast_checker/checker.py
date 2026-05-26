from tree_sitter import Parser

from .engines import get_engine
from .mappings import get_language, get_mapping


def check_ast(code: str, language: str, rules: list[dict]) -> tuple[bool, list[dict]]:
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

    results = []
    all_passed = True
    for rule in rules:
        engine = get_engine(rule.get("engine", ""))
        if engine is None:
            continue
        errors = engine.check(tree, rule, language, mapping)
        passed = len(errors) == 0
        if not passed:
            all_passed = False
        results.append({"description": engine.describe(rule, language, mapping), "passed": passed})

    return all_passed, results
