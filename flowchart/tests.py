from types import SimpleNamespace
from unittest import TestCase

from .tasks import build_evaluation_prompt


class FlowchartEvaluationPromptTests(TestCase):
    def test_prompt_excludes_system_generated_mermaid_ids_and_limits_feedback(self):
        prompt = build_evaluation_prompt(SimpleNamespace())

        self.assertIn("Mermaid节点ID由系统生成", prompt)
        self.assertIn("不要评价节点ID", prompt)
        self.assertIn("不要因节点ID扣分", prompt)
        self.assertIn("feedback控制在0字以内", prompt)
        self.assertIn("suggestions最多3条", prompt)
        self.assertIn("重要建议必须以【重点】开头", prompt)
