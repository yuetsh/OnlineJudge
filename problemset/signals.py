# 题单应用信号处理
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import ProblemSetProblem, ProblemSetProgress, ProblemSetBadge, UserBadge
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ProblemSetProblem)
def sync_progress_on_problem_change(sender, instance, created, **kwargs):
    """当题单题目发生变化时，同步所有用户的进度"""
    try:
        with transaction.atomic():
            # 获取该题单的所有用户进度
            progresses = ProblemSetProgress.objects.filter(
                problemset=instance.problemset
            )
            
            # 批量更新所有用户的进度
            for progress in progresses:
                progress.update_progress()
            
            # 重新计算该题单的所有徽章资格
            badges = ProblemSetBadge.objects.filter(problemset=instance.problemset)
            for badge in badges:
                badge.recalculate_user_badges()
                
            logger.info(f"已同步题单 {instance.problemset.id} 的所有用户进度和徽章资格")
            
    except Exception as e:
        logger.error(f"同步题单进度时出错: {e}")


@receiver(post_delete, sender=ProblemSetProblem)
def sync_progress_on_problem_delete(sender, instance, **kwargs):
    """当题单题目被删除时，同步所有用户的进度并清理相关提交记录"""
    try:
        with transaction.atomic():
            # 清理该题目在题单中的所有提交记录
            from .models import ProblemSetSubmission
            ProblemSetSubmission.objects.filter(
                problemset=instance.problemset,
                problem=instance.problem
            ).delete()
            
            # 获取该题单的所有用户进度
            progresses = ProblemSetProgress.objects.filter(
                problemset=instance.problemset
            )
            
            # 批量更新所有用户的进度
            for progress in progresses:
                progress.update_progress()
            
            # 重新计算该题单的所有徽章资格
            badges = ProblemSetBadge.objects.filter(problemset=instance.problemset)
            for badge in badges:
                badge.recalculate_user_badges()
                
            logger.info(f"已同步题单 {instance.problemset.id} 的所有用户进度和徽章资格（删除题目后）")
            
    except Exception as e:
        logger.error(f"同步题单进度时出错: {e}")


@receiver(post_save, sender=ProblemSetBadge)
def sync_badges_on_badge_change(sender, instance, created, **kwargs):
    """当题单奖章发生变化时，重新计算所有用户的奖章资格"""
    try:
        with transaction.atomic():
            # 重新计算该奖章的所有用户资格
            instance.recalculate_user_badges()
            logger.info(f"已重新计算题单 {instance.problemset.id} 的奖章 {instance.id} 的用户资格")
            
    except Exception as e:
        logger.error(f"重新计算奖章资格时出错: {e}")


@receiver(post_delete, sender=ProblemSetBadge)
def cleanup_badges_on_badge_delete(sender, instance, **kwargs):
    """当题单奖章被删除时，清理相关的用户奖章记录"""
    try:
        with transaction.atomic():
            # 删除该奖章的所有用户奖章记录
            UserBadge.objects.filter(badge=instance).delete()
            logger.info(f"已清理奖章 {instance.id} 的所有用户奖章记录")
            
    except Exception as e:
        logger.error(f"清理用户奖章记录时出错: {e}")
