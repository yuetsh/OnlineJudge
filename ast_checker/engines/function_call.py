from .base import BaseEngine

CALL_NODE_TYPES = {
    "Python3": "call",
    "C": "call_expression",
}


class _FunctionCallBase(BaseEngine):
    def _find_function_calls(self, root, func_name, language):
        call_type = CALL_NODE_TYPES.get(language, "call")
        calls = self.collect_nodes(root, call_type)
        matches = []
        for call in calls:
            func_node = call.child_by_field_name("function")
            if func_node and func_node.type == "identifier" and func_node.text.decode() == func_name:
                matches.append(call)
        return matches


class MustCallFunctionEngine(_FunctionCallBase):
    def _message(self, rule):
        return rule.get("message") or f"必须调用 {rule['target']}()"

    def check(self, tree, rule, language, mapping):
        if not self._find_function_calls(tree.root_node, rule["target"], language):
            return [self._message(rule)]
        return []

    def describe(self, rule, language, mapping):
        return self._message(rule)


class MustNotCallFunctionEngine(_FunctionCallBase):
    def _message(self, rule):
        return rule.get("message") or f"不能调用 {rule['target']}()"

    def check(self, tree, rule, language, mapping):
        if self._find_function_calls(tree.root_node, rule["target"], language):
            return [self._message(rule)]
        return []

    def describe(self, rule, language, mapping):
        return self._message(rule)


class CountFunctionCallEngine(_FunctionCallBase):
    def _message(self, rule, count):
        target = rule["target"]
        min_count = rule.get("min")
        max_count = rule.get("max")
        if min_count is not None and count < min_count:
            return rule.get("message") or f"{target}() 至少调用 {min_count} 次，当前 {count} 次"
        if max_count is not None and count > max_count:
            return rule.get("message") or f"{target}() 至多调用 {max_count} 次，当前 {count} 次"
        return None

    def check(self, tree, rule, language, mapping):
        count = len(self._find_function_calls(tree.root_node, rule["target"], language))
        msg = self._message(rule, count)
        return [msg] if msg else []

    def describe(self, rule, language, mapping):
        target = rule["target"]
        min_count = rule.get("min")
        max_count = rule.get("max")
        if rule.get("message"):
            return rule["message"]
        parts = []
        if min_count is not None:
            parts.append(f"至少 {min_count} 次")
        if max_count is not None:
            parts.append(f"至多 {max_count} 次")
        return f"{target}() " + "、".join(parts)
