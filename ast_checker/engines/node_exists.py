from ast_checker.labels import label

from .base import BaseEngine


class MustExistNodeEngine(BaseEngine):
    def _message(self, rule):
        return rule.get("message") or f"必须使用 {rule.get('label') or label(rule['target'])}"

    def check(self, tree, rule, language, mapping):
        node_type = mapping.get(rule["target"], rule["target"])
        if not self.has_node(tree.root_node, node_type):
            return [self._message(rule)]
        return []

    def describe(self, rule, language, mapping):
        return self._message(rule)


class MustNotExistNodeEngine(BaseEngine):
    def _message(self, rule):
        return rule.get("message") or f"不能使用 {rule.get('label') or label(rule['target'])}"

    def check(self, tree, rule, language, mapping):
        node_type = mapping.get(rule["target"], rule["target"])
        if self.has_node(tree.root_node, node_type):
            return [self._message(rule)]
        return []

    def describe(self, rule, language, mapping):
        return self._message(rule)
