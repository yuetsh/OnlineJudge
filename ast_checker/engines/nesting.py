from ast_checker.labels import label

from .base import BaseEngine


class MustHaveNestingEngine(BaseEngine):
    def _has_inner_in_subtree(self, node, inner_type):
        for child in node.children:
            if self.has_node(child, inner_type):
                return True
        return False

    def _message(self, rule):
        if rule.get("message"):
            return rule["message"]
        outer = rule.get("outer", "")
        inner = rule.get("inner", "")
        outer_label = label(outer)
        inner_label = label(inner)
        if outer == inner:
            return f"必须使用 {outer_label} 嵌套"
        return f"必须在 {outer_label} 中嵌套使用 {inner_label}"

    def check(self, tree, rule, language, mapping):
        outer_type = mapping.get(rule["outer"], rule["outer"])
        inner_type = mapping.get(rule["inner"], rule["inner"])
        outer_nodes = self.collect_nodes(tree.root_node, outer_type)
        for outer_node in outer_nodes:
            if self._has_inner_in_subtree(outer_node, inner_type):
                return []
        return [self._message(rule)]

    def describe(self, rule, language, mapping):
        return self._message(rule)
