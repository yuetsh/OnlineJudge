import hashlib
import json
import logging
from datetime import timedelta
from urllib.parse import urljoin

import httpx
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from account.models import User
from conf.models import JudgeServer
from contest.models import ACMContestRank
from options.options import SysOptions
from problem.models import Problem
from problem.utils import parse_problem_template
from submission.models import JudgeStatus, Submission, is_accepted
from utils.cache import cache
from utils.constants import CacheKey
from utils.websocket import push_submission_update

logger = logging.getLogger(__name__)


# 继续处理在队列中的问题
def process_pending_task():
    if cache.llen(CacheKey.waiting_queue):
        # 防止循环引入
        from judge.tasks import judge_task

        tmp_data = cache.rpop(CacheKey.waiting_queue)
        if tmp_data:
            data = json.loads(tmp_data.decode("utf-8"))
            judge_task.send(**data)


class ChooseJudgeServer:
    def __init__(self):
        self.server = None

    def __enter__(self) -> [JudgeServer, None]:
        with transaction.atomic():
            cutoff = timezone.now() - timedelta(seconds=6)
            server = (
                JudgeServer.objects.select_for_update(skip_locked=True)
                .filter(
                    is_disabled=False,
                    last_heartbeat__gte=cutoff,
                    task_number__lte=F("cpu_core") * 2,
                )
                .order_by("task_number")
                .first()
            )
            if server:
                server.task_number = F("task_number") + 1
                server.save(update_fields=["task_number"])
                self.server = server
                return server
        return None

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.server:
            JudgeServer.objects.filter(id=self.server.id).update(task_number=F("task_number") - 1)


class DispatcherBase(object):
    def __init__(self):
        self.token = hashlib.sha256(SysOptions.judge_server_token.encode("utf-8")).hexdigest()

    def _request(self, url, data=None):
        kwargs = {"headers": {"X-Judge-Server-Token": self.token}}
        if data:
            kwargs["json"] = data
        try:
            # timeout=None 保持与原 requests 实现一致：判题请求是同步等结果的，不能被默认超时打断
            return httpx.post(url, timeout=None, **kwargs).json()
        except Exception as e:
            logger.exception(e)


class JudgeDispatcher(DispatcherBase):
    # 是否占用 JudgeServer 槽位。判完后只有占过槽位的才需要唤醒等待队列，
    # 否则会把队首任务 pop 出来又原地退回（SQLJudgeDispatcher 在 worker 内判题，不占槽位）
    uses_judge_server = True

    def __init__(self, submission_id, problem_id):
        super().__init__()
        self.submission = Submission.objects.get(id=submission_id)
        self.contest_id = self.submission.contest_id
        self.last_result = self.submission.result if self.submission.info else None

        if self.contest_id:
            self.problem = Problem.objects.select_related("contest").get(id=problem_id, contest_id=self.contest_id)
            self.contest = self.problem.contest
        else:
            self.problem = Problem.objects.get(id=problem_id)

    def _push_status(self, result, status, extra=None):
        data = {
            "type": "submission_update",
            "submission_id": str(self.submission.id),
            "result": result,
            "status": status,
        }
        if extra:
            data.update(extra)
        try:
            push_submission_update(
                submission_id=str(self.submission.id),
                user_id=self.submission.user_id,
                data=data,
            )
        except Exception as e:
            logger.error(f"Failed to push submission update: {str(e)}")

    def _compute_statistic_info(self, resp_data):
        # 用时和内存占用保存为多个测试点中最长的那个
        self.submission.statistic_info["time_cost"] = max([x["cpu_time"] for x in resp_data])
        self.submission.statistic_info["memory_cost"] = max([x["memory"] for x in resp_data])

    def judge(self):
        language = self.submission.language
        sub_config = list(filter(lambda item: language == item["name"], SysOptions.languages))[0]

        if language in self.problem.template:
            template = parse_problem_template(self.problem.template[language])
            code = f"{template['prepend']}\n{self.submission.code}\n{template['append']}"
        else:
            code = self.submission.code

        data = {
            "language_config": sub_config["config"],
            "src": code,
            "max_cpu_time": self.problem.time_limit,
            "max_memory": 1024 * 1024 * self.problem.memory_limit,
            "test_case_id": self.problem.test_case_id,
            "output": False,
            "io_mode": {"io_mode": "Standard IO", "input": "input.txt", "output": "output.txt"},
        }

        with ChooseJudgeServer() as server:
            if not server:
                data = {"submission_id": self.submission.id, "problem_id": self.problem.id}
                cache.lpush(CacheKey.waiting_queue, json.dumps(data))
                # 推送排队状态
                self._push_status(JudgeStatus.PENDING, "pending")
                return
            Submission.objects.filter(id=self.submission.id).update(result=JudgeStatus.JUDGING)

            # 推送判题中状态
            self._push_status(JudgeStatus.JUDGING, "judging")

            resp = self._request(urljoin(server.service_url, "/judge"), data=data)

        if not resp:
            Submission.objects.filter(id=self.submission.id).update(result=JudgeStatus.SYSTEM_ERROR)
            # 推送系统错误状态
            self._push_status(JudgeStatus.SYSTEM_ERROR, "error")
            return

        self._process_judge_result(resp)

    def _process_judge_result(self, resp):
        """判题结果的统一后处理：状态聚合、AST 钩子、统计、排名、WebSocket 推送。

        resp 结构与外部 judger 返回一致：{"err": "CompileError"|None, "data": ...}；
        SQLJudgeDispatcher 组装同构 resp 后也走这里。
        """
        language = self.submission.language
        if resp["err"]:
            self.submission.result = JudgeStatus.COMPILE_ERROR
            self.submission.statistic_info["err_info"] = resp["data"]
            self.submission.statistic_info["score"] = 0
        else:
            resp["data"].sort(key=lambda x: int(x["test_case"]))
            self.submission.info = resp
            self._compute_statistic_info(resp["data"])
            error_test_case = list(filter(lambda case: case["result"] != 0, resp["data"]))
            # 多个测试点全部正确则AC，否则取第一个错误的测试点的状态
            if not error_test_case:
                self.submission.result = JudgeStatus.ACCEPTED
            else:
                self.submission.result = error_test_case[0]["result"]

            if self.submission.result == JudgeStatus.ACCEPTED:
                ast_rules = self.problem.ast_rules
                if ast_rules and language in ast_rules:
                    from ast_checker.checker import check_ast

                    passed, results = check_ast(self.submission.code, language, ast_rules[language])
                    if not passed:
                        self.submission.result = JudgeStatus.AST_CHECK_FAILED
                        self.submission.statistic_info["ast_results"] = results
        self.submission.save(update_fields=["result", "info", "statistic_info"])

        # 推送判题完成状态
        self._push_status(
            self.submission.result,
            "finished",
            extra={
                "time_cost": self.submission.statistic_info.get("time_cost"),
                "memory_cost": self.submission.statistic_info.get("memory_cost"),
                "score": self.submission.statistic_info.get("score", 0),
            },
        )

        if self.contest_id:
            # 以提交时刻（而非判题时刻）是否落在比赛时间窗内为准，
            # 避免临界提交因判题排队延迟到比赛结束后才处理而被丢弃
            in_contest = self.contest.start_time <= self.submission.create_time <= self.contest.end_time
            if not in_contest or User.objects.get(id=self.submission.user_id).is_contest_admin(self.contest):
                logger.info("Contest debug mode, id: " + str(self.contest_id) + ", submission id: " + self.submission.id)
                return
            with transaction.atomic():
                self.update_contest_problem_status()
                self.update_contest_rank()
        else:
            if self.last_result:
                self.update_problem_status_rejudge()
            else:
                self.update_problem_status()

        # 至此判题结束，释放了 JudgeServer 槽位，尝试处理任务队列中剩余的任务
        if self.uses_judge_server:
            process_pending_task()

    def update_problem_status_rejudge(self):
        result = str(self.submission.result)
        problem_id = str(self.problem.id)
        with transaction.atomic():
            # update problem status
            problem = Problem.objects.select_for_update().get(contest_id=self.contest_id, id=self.problem.id)
            if not is_accepted(self.last_result) and is_accepted(self.submission.result):
                problem.accepted_number = F("accepted_number") + 1
            problem_info = problem.statistic_info
            problem_info[self.last_result] = problem_info.get(self.last_result, 1) - 1
            problem_info[result] = problem_info.get(result, 0) + 1
            problem.save(update_fields=["accepted_number", "statistic_info"])

            profile = User.objects.select_for_update().get(id=self.submission.user_id).userprofile
            acm_problems_status = profile.acm_problems_status.get("problems", {})
            if not is_accepted(acm_problems_status[problem_id]["status"]):
                acm_problems_status[problem_id]["status"] = JudgeStatus.ACCEPTED if is_accepted(self.submission.result) else self.submission.result
                if is_accepted(self.submission.result):
                    profile.accepted_number += 1
            profile.acm_problems_status["problems"] = acm_problems_status
            profile.save(update_fields=["accepted_number", "acm_problems_status"])

    def update_problem_status(self):
        result = str(self.submission.result)
        problem_id = str(self.problem.id)
        with transaction.atomic():
            # update problem status
            problem = Problem.objects.select_for_update().get(contest_id=self.contest_id, id=self.problem.id)
            problem.submission_number = F("submission_number") + 1
            if is_accepted(self.submission.result):
                problem.accepted_number = F("accepted_number") + 1
            problem_info = problem.statistic_info
            problem_info[result] = problem_info.get(result, 0) + 1
            problem.save(update_fields=["accepted_number", "submission_number", "statistic_info"])

            # update_userprofile
            user = User.objects.select_for_update().get(id=self.submission.user_id)
            user_profile = user.userprofile
            user_profile.submission_number = F("submission_number") + 1
            profile_status = JudgeStatus.ACCEPTED if is_accepted(self.submission.result) else self.submission.result
            acm_problems_status = user_profile.acm_problems_status.get("problems", {})
            if problem_id not in acm_problems_status:
                acm_problems_status[problem_id] = {"status": profile_status, "_id": self.problem._id}
                if is_accepted(self.submission.result):
                    user_profile.accepted_number += 1
            elif not is_accepted(acm_problems_status[problem_id]["status"]):
                acm_problems_status[problem_id]["status"] = profile_status
                if is_accepted(self.submission.result):
                    user_profile.accepted_number += 1
            user_profile.acm_problems_status["problems"] = acm_problems_status
            user_profile.save(update_fields=["submission_number", "accepted_number", "acm_problems_status"])

    def update_contest_problem_status(self):
        with transaction.atomic():
            user = User.objects.select_for_update().get(id=self.submission.user_id)
            user_profile = user.userprofile
            problem_id = str(self.problem.id)
            profile_status = JudgeStatus.ACCEPTED if is_accepted(self.submission.result) else self.submission.result
            contest_problems_status = user_profile.acm_problems_status.get("contest_problems", {})
            if problem_id not in contest_problems_status:
                contest_problems_status[problem_id] = {"status": profile_status, "_id": self.problem._id}
            elif not is_accepted(contest_problems_status[problem_id]["status"]):
                contest_problems_status[problem_id]["status"] = profile_status
            else:
                # 如果已AC， 直接跳过 不计入任何计数器
                return
            user_profile.acm_problems_status["contest_problems"] = contest_problems_status
            user_profile.save(update_fields=["acm_problems_status"])

            problem = Problem.objects.select_for_update().get(contest_id=self.contest_id, id=self.problem.id)
            result = str(self.submission.result)
            problem_info = problem.statistic_info
            problem_info[result] = problem_info.get(result, 0) + 1
            problem.submission_number = F("submission_number") + 1
            if is_accepted(self.submission.result):
                problem.accepted_number = F("accepted_number") + 1
            problem.save(update_fields=["submission_number", "accepted_number", "statistic_info"])

    def update_contest_rank(self):
        def get_rank():
            return ACMContestRank.objects.select_for_update().get(user_id=self.submission.user_id, contest=self.contest)

        try:
            rank = get_rank()
        except ACMContestRank.DoesNotExist:
            try:
                ACMContestRank.objects.create(user_id=self.submission.user_id, contest=self.contest)
                rank = get_rank()
            except IntegrityError:
                rank = get_rank()
        self._update_acm_contest_rank(rank)

    def _update_acm_contest_rank(self, rank):
        info = rank.submission_info.get(str(self.submission.problem_id))
        # 因前面更改过，这里需要重新获取
        problem = Problem.objects.select_for_update().get(contest_id=self.contest_id, id=self.problem.id)
        # 此题提交过
        if info:
            if info["is_ac"]:
                return

            rank.submission_number += 1
            if is_accepted(self.submission.result):
                rank.accepted_number += 1
                info["is_ac"] = True
                info["ac_time"] = int((self.submission.create_time - self.contest.start_time).total_seconds())
                rank.total_time += info["ac_time"] + info["error_number"] * 20 * 60

                if problem.accepted_number == 1:
                    info["is_first_ac"] = True
            elif self.submission.result != JudgeStatus.COMPILE_ERROR:
                info["error_number"] += 1

        # 第一次提交
        else:
            rank.submission_number += 1
            info = {"is_ac": False, "ac_time": 0, "error_number": 0, "is_first_ac": False}
            if is_accepted(self.submission.result):
                rank.accepted_number += 1
                info["is_ac"] = True
                info["ac_time"] = int((self.submission.create_time - self.contest.start_time).total_seconds())
                rank.total_time += info["ac_time"]

                if problem.accepted_number == 1:
                    info["is_first_ac"] = True

            elif self.submission.result != JudgeStatus.COMPILE_ERROR:
                info["error_number"] = 1
        rank.submission_info[str(self.submission.problem_id)] = info
        rank.save(update_fields=["submission_info", "total_time", "accepted_number", "submission_number"])
