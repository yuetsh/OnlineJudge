import json
import logging
import time

import dramatiq
from django.db import transaction
from django.utils import timezone

from utils.openai import get_ai_client
from utils.shortcuts import DRAMATIQ_WORKER_ARGS

from .models import FlowchartSubmission, FlowchartSubmissionStatus

logger = logging.getLogger(__name__)


@dramatiq.actor(**DRAMATIQ_WORKER_ARGS(max_retries=3))
def evaluate_flowchart_task(submission_id):
    """异步AI评分任务"""
    submission = None
    try:
        submission = FlowchartSubmission.objects.get(id=submission_id)

        # 更新状态为处理中
        submission.status = FlowchartSubmissionStatus.PROCESSING
        submission.save()

        start_time = time.time()

        # 使用固定评分标准
        system_prompt = build_evaluation_prompt(submission.problem)

        # 构建用户提示词，包含标准答案对比
        user_prompt = f"""
请对以下Mermaid流程图进行评分：

学生提交的流程图：
```mermaid
{submission.mermaid_code}
```
"""
        if submission.problem.mermaid_code:
            user_prompt += f"""
标准答案参考：
```mermaid
{submission.problem.mermaid_code}
```
"""
        else:
            user_prompt += "\n注意：此题没有标准答案，请根据题目描述和流程图的逻辑合理性进行评分。\n"

        if submission.problem.flowchart_hint:
            user_prompt += f"\n设计提示：{submission.problem.flowchart_hint}\n"

        user_prompt += "\n请按照评分标准进行详细评估，并给出0-100的分数。\n"

        # 调用AI进行评分
        client = get_ai_client()

        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0,
            extra_body={"thinking": {"type": "disabled"}},
        )

        ai_response = response.choices[0].message.content
        score_data = parse_ai_evaluation_response(ai_response)

        processing_time = time.time() - start_time

        # 保存评分结果
        with transaction.atomic():
            submission.ai_score = score_data["score"]
            submission.ai_grade = score_data["grade"]
            submission.ai_feedback = score_data["feedback"]
            submission.ai_suggestions = score_data.get("suggestions", "")
            submission.ai_criteria_details = score_data.get("criteria_details", {})
            submission.ai_provider = "deepseek"
            submission.ai_model = "deepseek-v4-flash"
            submission.processing_time = processing_time
            submission.status = FlowchartSubmissionStatus.COMPLETED
            submission.evaluation_time = timezone.now()
            submission.save()

        # 推送评分完成通知
        from utils.websocket import push_flowchart_evaluation_update

        push_flowchart_evaluation_update(
            submission_id=str(submission.id),
            user_id=submission.user_id,
            data={
                "type": "flowchart_evaluation_completed",
                "score": score_data["score"],
                "grade": score_data["grade"],
            },
        )

    except Exception as e:
        logger.exception("evaluate_flowchart_task failed for submission %s", submission_id)
        if submission is not None:
            submission.status = FlowchartSubmissionStatus.FAILED
            submission.save()

            from utils.websocket import push_flowchart_evaluation_update

            push_flowchart_evaluation_update(
                submission_id=str(submission.id),
                user_id=submission.user_id,
                data={
                    "type": "flowchart_evaluation_failed",
                    "submission_id": str(submission.id),
                    "error": str(e),
                },
            )
        raise e


def build_evaluation_prompt(problem):
    """构建AI评分提示词 - 使用固定标准"""

    # 使用固定的评分标准
    criteria_text = """
- 逻辑正确性 (权重: 1.0, 最高分: 40): 检查流程图的逻辑是否正确，包括条件判断、循环结构等
- 完整性 (权重: 0.8, 最高分: 30): 检查流程图是否包含所有必要的步骤和分支
- 规范性 (权重: 0.6, 最高分: 20): 检查流程图符号使用是否规范，是否符合标准；不要评价节点ID
- 清晰度 (权重: 0.4, 最高分: 10): 评估流程图的整体布局和连线情况；不要因节点ID扣分
"""

    return f"""
你是一个专业的编程教学助手，负责评估学生提交的Mermaid流程图。

评分标准：
{criteria_text}

评分要求：
1. 仔细分析流程图的逻辑正确性、完整性和清晰度
2. 检查是否涵盖了题目的所有要求
3. 评估流程图的规范性和可读性
4. 给出0-100的分数
5. Mermaid节点ID由系统生成，不是学生编写内容；不要评价节点ID，不要因节点ID扣分，不要建议修改节点ID
6. feedback控制在100字以内，只总结核心优点和主要问题
7. suggestions最多3条，每条单独一行；重要建议必须以【重点】开头，普通建议不要加前缀
   - 只针对学生流程图中真实存在的问题给建议；若流程图已符合要求，suggestions 留空字符串，禁止编造或凑数
   - 不要建议学生去做他已经做对的事（如顺序/分支已正确，就不要再建议调整该顺序/分支）
8. criteria_details 中的 comment 保持简短，每项不超过25字

评分等级：
- S级 (90-100分): 优秀，逻辑清晰，完全符合要求
- A级 (80-89分): 良好，基本符合要求，有少量改进空间
- B级 (70-79分): 及格，基本正确但存在一些问题
- C级 (0-69分): 需要改进，存在明显问题

请以JSON格式返回评分结果（以下仅为格式示例，feedback/suggestions 的内容必须依据学生实际提交的流程图生成，不要照搬示例文字，尤其不要在没有循环的流程图中提及循环）：
{{
    "score": 85,
    "grade": "A",
    "feedback": "<根据实际流程图填写，100字以内>",
    "suggestions": "<根据实际问题填写；若无明显问题可留空字符串>",
    "criteria_details": {{
        "逻辑正确性": {{"score": 35, "max": 40, "comment": "<简短说明>"}},
        "完整性": {{"score": 25, "max": 30, "comment": "<简短说明>"}},
        "规范性": {{"score": 18, "max": 20, "comment": "<简短说明>"}},
        "清晰度": {{"score": 8, "max": 10, "comment": "<简短说明>"}}
    }}
}}
"""


def parse_ai_evaluation_response(ai_response):
    """解析AI评分响应，解析失败时抛出异常由调用方处理"""
    import re

    # 优先匹配代码块中的 JSON，避免贪婪匹配误抓 reasoning 段落
    code_block = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", ai_response, re.DOTALL)
    if code_block:
        json_str = code_block.group(1)
    else:
        json_match = re.search(r"\{.*\}", ai_response, re.DOTALL)
        if not json_match:
            raise ValueError("AI响应中未找到JSON数据")
        json_str = json_match.group()

    data = json.loads(json_str)

    if "score" not in data or "grade" not in data:
        raise ValueError("AI响应缺少必要字段: score 或 grade")

    return data
