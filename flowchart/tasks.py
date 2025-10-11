import dramatiq
import json
import time
from openai import OpenAI
from django.db import transaction
from django.utils import timezone
from utils.shortcuts import get_env, DRAMATIQ_WORKER_ARGS
from .models import FlowchartSubmission, FlowchartSubmissionStatus

@dramatiq.actor(**DRAMATIQ_WORKER_ARGS(max_retries=3))
def evaluate_flowchart_task(submission_id):
    """异步AI评分任务"""
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

        标准答案参考：
        ```mermaid
        {submission.problem.mermaid_code}
        ```
        """
        # 如果有流程图提示，添加到提示词中
        if submission.problem.flowchart_hint:
            user_prompt += f"""
        
        设计提示：{submission.problem.flowchart_hint}
        """
        
        user_prompt += """
        
        请按照评分标准进行详细评估，并给出0-100的分数。
        """
        
        # 调用AI进行评分
        api_key = get_env("AI_KEY")
        if not api_key:
            raise Exception("AI_KEY is not set")
            
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
        )
        
        ai_response = response.choices[0].message.content
        score_data = parse_ai_evaluation_response(ai_response)
        
        processing_time = time.time() - start_time
        
        # 保存评分结果
        with transaction.atomic():
            submission.ai_score = score_data['score']
            submission.ai_grade = score_data['grade']
            submission.ai_feedback = score_data['feedback']
            submission.ai_suggestions = score_data.get('suggestions', '')
            submission.ai_criteria_details = score_data.get('criteria_details', {})
            submission.ai_provider = 'deepseek'
            submission.ai_model = 'deepseek-chat'
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
                "submission_id": str(submission.id),
                "score": score_data['score'],
                "grade": score_data['grade'],
                "feedback": score_data['feedback']
            }
        )
        
    except Exception as e:
        # 处理失败
        submission.status = FlowchartSubmissionStatus.FAILED
        submission.save()
        
        # 推送错误通知
        from utils.websocket import push_flowchart_evaluation_update
        push_flowchart_evaluation_update(
            submission_id=str(submission.id),
            user_id=submission.user_id,
            data={
                "type": "flowchart_evaluation_failed",
                "submission_id": str(submission.id),
                "error": str(e)
            }
        )
        raise e

def build_evaluation_prompt(problem):
    """构建AI评分提示词 - 使用固定标准"""
    
    # 使用固定的评分标准
    criteria_text = """
- 逻辑正确性 (权重: 1.0, 最高分: 40): 检查流程图的逻辑是否正确，包括条件判断、循环结构等
- 完整性 (权重: 0.8, 最高分: 30): 检查流程图是否包含所有必要的步骤和分支
- 规范性 (权重: 0.6, 最高分: 20): 检查流程图符号使用是否规范，是否符合标准
- 清晰度 (权重: 0.4, 最高分: 10): 评估流程图的整体布局和可读性
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
5. 提供详细的反馈和改进建议

评分等级：
- S级 (90-100分): 优秀，逻辑清晰，完全符合要求
- A级 (80-89分): 良好，基本符合要求，有少量改进空间
- B级 (70-79分): 及格，基本正确但存在一些问题
- C级 (0-69分): 需要改进，存在明显问题

请以JSON格式返回评分结果：
{{
    "score": 85,
    "grade": "A",
    "feedback": "详细的反馈内容",
    "suggestions": "改进建议",
    "criteria_details": {{
        "逻辑正确性": {{"score": 35, "max": 40, "comment": "逻辑基本正确"}},
        "完整性": {{"score": 25, "max": 30, "comment": "缺少部分步骤"}},
        "规范性": {{"score": 18, "max": 20, "comment": "符号使用规范"}},
        "清晰度": {{"score": 8, "max": 10, "comment": "布局清晰"}}
    }}
}}
"""

def parse_ai_evaluation_response(ai_response):
    """解析AI评分响应"""
    try:
        import re
        json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
        else:
            data = {
                "score": 60,
                "grade": "C",
                "feedback": "AI评分解析失败，请重新提交",
                "suggestions": "",
                "criteria_details": {}
            }
        return data
    except Exception:
        return {
            "score": 60,
            "grade": "C", 
            "feedback": "AI评分解析失败，请重新提交",
            "suggestions": "",
            "criteria_details": {}
        }
