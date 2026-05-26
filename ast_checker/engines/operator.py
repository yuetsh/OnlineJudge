from .base import BaseEngine


class MustUseOperatorEngine(BaseEngine):
    def _message(self, rule):
        return rule.get("message") or f"必须使用 {rule['target']} 运算符"

    def check(self, tree, rule, language, mapping):
        mapped_op = mapping.get(rule["target"], rule["target"])
        if not self.has_node(tree.root_node, mapped_op):
            return [self._message(rule)]
        return []

    def describe(self, rule, language, mapping):
        return self._message(rule)
