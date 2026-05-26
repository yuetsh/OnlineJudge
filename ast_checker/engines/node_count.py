from .base import BaseEngine
from ast_checker.labels import label


class CountNodeEngine(BaseEngine):
    def _message(self, rule, count):
        name = rule.get("label") or label(rule["target"])
        exact = rule.get("exact")
        if exact is not None and count != exact:
            return rule.get("message") or f"{name} 需要出现 {exact} 次，当前 {count} 次"
        min_count = rule.get("min")
        max_count = rule.get("max")
        if min_count is not None and count < min_count:
            return rule.get("message") or f"{name} 至少出现 {min_count} 次，当前 {count} 次"
        if max_count is not None and count > max_count:
            return rule.get("message") or f"{name} 至多出现 {max_count} 次，当前 {count} 次"
        return None

    def check(self, tree, rule, language, mapping):
        target = rule["target"]
        node_type = mapping.get(target, target)
        count = len(self.collect_nodes(tree.root_node, node_type))
        msg = self._message(rule, count)
        return [msg] if msg else []

    def describe(self, rule, language, mapping):
        name = rule.get("label") or label(rule["target"])
        if rule.get("message"):
            return rule["message"]
        exact = rule.get("exact")
        if exact is not None:
            return f"{name} 出现 {exact} 次"
        parts = []
        if rule.get("min") is not None:
            parts.append(f"至少 {rule['min']} 次")
        if rule.get("max") is not None:
            parts.append(f"至多 {rule['max']} 次")
        return f"{name} " + "、".join(parts)
