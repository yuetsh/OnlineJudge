from .base import BaseEngine


class MustUseOperatorEngine(BaseEngine):
    def check(self, tree, rule, language, mapping):
        target = rule["target"]
        mapped_op = mapping.get(target, target)
        if not self.has_node(tree.root_node, mapped_op):
            return [rule.get("message", f"必须使用 {target} 运算符")]
        return []
