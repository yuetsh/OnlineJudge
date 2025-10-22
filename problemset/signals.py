from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import ProblemSetProgress, ProblemSetBadge, UserBadge
from submission.models import Submission


@receiver(post_save, sender=Submission)
def update_problemset_progress(sender, instance, created, **kwargs):
    """当提交状态更新时，自动更新题单进度"""
    if not created:  # 只处理更新，不处理新建
        return

    # 检查该提交是否属于某个题单中的题目
    try:
        from .models import ProblemSetProblem

        problemset_problems = ProblemSetProblem.objects.filter(problem=instance.problem)

        for psp in problemset_problems:
            # 获取或创建用户在该题单中的进度记录
            progress, created = ProblemSetProgress.objects.get_or_create(
                problemset=psp.problemset, user=instance.user
            )

            # 更新详细进度
            problem_id = str(instance.problem.id)
            progress.progress_detail[problem_id] = {
                "status": "completed"
                if instance.result == 0
                else "attempted",  # 0表示AC
                "score": instance.score if hasattr(instance, "score") else 0,
                "submit_time": timezone.now().isoformat(),
            }

            # 更新进度
            progress.update_progress()

            # 检查是否获得奖章
            check_and_award_badges(progress)

    except Exception as e:
        # 记录错误但不影响主流程
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"更新题单进度时出错: {e}")


def check_and_award_badges(progress):
    """检查并颁发奖章"""
    badges = ProblemSetBadge.objects.filter(problemset=progress.problemset)

    for badge in badges:
        # 检查是否已经获得该奖章
        if UserBadge.objects.filter(user=progress.user, badge=badge).exists():
            continue

        # 检查是否满足获得条件
        should_award = False

        if badge.condition_type == "all_problems":
            should_award = (
                progress.completed_problems_count == progress.total_problems_count
            )
        elif badge.condition_type == "problem_count":
            should_award = progress.completed_problems_count >= badge.condition_value
        elif badge.condition_type == "score":
            should_award = progress.total_score >= badge.condition_value

        if should_award:
            UserBadge.objects.create(user=progress.user, badge=badge)
