import logging

import dramatiq

from account.models import User
from achievement import checker
from achievement.notify import notify_achievements
from submission.models import Submission
from utils.shortcuts import DRAMATIQ_WORKER_ARGS

logger = logging.getLogger(__name__)


@dramatiq.actor(**DRAMATIQ_WORKER_ARGS())
def check_achievements(user_id, submission_id):
    """判题完成后的成就判定。

    所有异常在此吞掉：成就算错绝不能影响判题结果，这也是选异步的意义。
    """
    try:
        user = User.objects.get(id=user_id)
        submission = Submission.objects.get(id=submission_id)
        records = checker.run_for_submission(user, submission)
        notify_achievements(user_id, records)
    except Exception as e:
        logger.exception(f"check_achievements failed: user_id={user_id}, submission_id={submission_id}, error={e}")
