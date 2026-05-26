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
    def check(self, tree, rule, language, mapping):
        target = rule["target"]
        if not self._find_function_calls(tree.root_node, target, language):
            return [rule.get("message", f"必须调用 {target}()")]
        return []


class MustNotCallFunctionEngine(_FunctionCallBase):
    def check(self, tree, rule, language, mapping):
        target = rule["target"]
        if self._find_function_calls(tree.root_node, target, language):
            return [rule.get("message", f"不能调用 {target}()")]
        return []


class CountFunctionCallEngine(_FunctionCallBase):
    def check(self, tree, rule, language, mapping):
        target = rule["target"]
        count = len(self._find_function_calls(tree.root_node, target, language))
        min_count = rule.get("min")
        max_count = rule.get("max")
        if min_count is not None and count < min_count:
            return [rule.get("message", f"{target}() 至少调用 {min_count} 次，当前 {count} 次")]
        if max_count is not None and count > max_count:
            return [rule.get("message", f"{target}() 至多调用 {max_count} 次，当前 {count} 次")]
        return []
