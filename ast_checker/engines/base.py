class BaseEngine:
    @staticmethod
    def collect_nodes(node, node_type):
        results = []
        if node.type == node_type:
            results.append(node)
        for child in node.children:
            results.extend(BaseEngine.collect_nodes(child, node_type))
        return results

    @staticmethod
    def has_node(node, node_type):
        if node.type == node_type:
            return True
        return any(BaseEngine.has_node(child, node_type) for child in node.children)

    def check(self, tree, rule, language, mapping) -> list[str]:
        raise NotImplementedError
