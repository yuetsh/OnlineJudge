from .base import BaseEngine


class MustExistNodeEngine(BaseEngine):
    def check(self, tree, rule, language, mapping):
        target = rule["target"]
        node_type = mapping.get(target, target)
        if not self.has_node(tree.root_node, node_type):
            return [rule.get("message", f"必须使用 {target}")]
        return []


class MustNotExistNodeEngine(BaseEngine):
    def check(self, tree, rule, language, mapping):
        target = rule["target"]
        node_type = mapping.get(target, target)
        if self.has_node(tree.root_node, node_type):
            return [rule.get("message", f"不能使用 {target}")]
        return []
