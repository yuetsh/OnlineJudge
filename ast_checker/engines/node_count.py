from .base import BaseEngine


class CountNodeEngine(BaseEngine):
    def check(self, tree, rule, language, mapping):
        target = rule["target"]
        node_type = mapping.get(target, target)
        nodes = self.collect_nodes(tree.root_node, node_type)
        count = len(nodes)
        min_count = rule.get("min")
        max_count = rule.get("max")
        if min_count is not None and count < min_count:
            return [rule.get("message", f"{target} 至少出现 {min_count} 次，当前 {count} 次")]
        if max_count is not None and count > max_count:
            return [rule.get("message", f"{target} 至多出现 {max_count} 次，当前 {count} 次")]
        return []
