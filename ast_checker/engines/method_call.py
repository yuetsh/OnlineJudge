from .base import BaseEngine

CALL_NODE_TYPES = {
    "Python3": "call",
    "C": "call_expression",
}


class _MethodCallBase(BaseEngine):
    def _find_method_calls(self, root, method_name, language):
        if language == "C":
            return []
        call_type = CALL_NODE_TYPES.get(language, "call")
        calls = self.collect_nodes(root, call_type)
        matches = []
        for call in calls:
            func_node = call.child_by_field_name("function")
            if func_node and func_node.type == "attribute":
                attr_node = func_node.child_by_field_name("attribute")
                if attr_node and attr_node.text.decode() == method_name:
                    matches.append(call)
        return matches


class MustCallMethodEngine(_MethodCallBase):
    def _message(self, rule):
        return rule.get("message") or f"必须调用 .{rule['target']}()"

    def check(self, tree, rule, language, mapping):
        if not self._find_method_calls(tree.root_node, rule["target"], language):
            return [self._message(rule)]
        return []

    def describe(self, rule, language, mapping):
        return self._message(rule)


class MustNotCallMethodEngine(_MethodCallBase):
    def _message(self, rule):
        return rule.get("message") or f"不能调用 .{rule['target']}()"

    def check(self, tree, rule, language, mapping):
        if self._find_method_calls(tree.root_node, rule["target"], language):
            return [self._message(rule)]
        return []

    def describe(self, rule, language, mapping):
        return self._message(rule)
