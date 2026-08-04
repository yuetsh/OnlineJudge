import dramatiq

from account.models import User
from achievement.tasks import check_achievements
from judge.dispatcher import JudgeDispatcher
from judge.sql_dispatcher import SQLJudgeDispatcher
from submission.models import Submission
from utils.shortcuts import DRAMATIQ_WORKER_ARGS


@dramatiq.actor(**DRAMATIQ_WORKER_ARGS())
def judge_task(submission_id, problem_id):
    submission = Submission.objects.get(id=submission_id)
    if User.objects.get(id=submission.user_id).is_disabled:
        return
    # SQL 题不依赖 JudgeServer 沙箱，在 worker 内用 sqlite3 判题
    if submission.language == "SQL":
        SQLJudgeDispatcher(submission_id, problem_id).judge()
    else:
        JudgeDispatcher(submission_id, problem_id).judge()

    # 判题结束后异步判定成就；投递失败不影响判题结果
    check_achievements.send(submission.user_id, submission_id)
