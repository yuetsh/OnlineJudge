from .base import BaseEngine


class CountNodeEngine(BaseEngine):
    def _message(self, rule, count):
        target = rule["target"]
        min_count = rule.get("min")
        max_count = rule.get("max")
        if min_count is not None and count < min_count:
            return rule.get("message") or f"{target} 至少出现 {min_count} 次，当前 {count} 次"
        if max_count is not None and count > max_count:
            return rule.get("message") or f"{target} 至多出现 {max_count} 次，当前 {count} 次"
        return None

    def check(self, tree, rule, language, mapping):
        target = rule["target"]
        node_type = mapping.get(target, target)
        count = len(self.collect_nodes(tree.root_node, node_type))
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
        return f"{target} " + "、".join(parts)
