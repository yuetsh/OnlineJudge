"""SQL 题判题调度：不走 JudgeServer 沙箱，在 dramatiq worker 内用 sqlite3 直接判题。

复用 JudgeDispatcher 的 _process_judge_result 完成状态聚合、统计、排名和 WebSocket 推送，
因此比赛排名、rejudge、题目统计的语义与沙箱判题完全一致。
"""

import json
import logging
import os

from django.conf import settings

from judge.dispatcher import JudgeDispatcher
from judge.sql_runner import SQLCaseError, run_case
from submission.models import JudgeStatus, Submission
from utils.shortcuts import natural_sort_key

logger = logging.getLogger(__name__)


class SQLProblemConfigError(Exception):
    pass


class SQLJudgeDispatcher(JudgeDispatcher):
    # 在 worker 内用 sqlite3 判题，不经过 ChooseJudgeServer，也就没有槽位可释放
    uses_judge_server = False

    def judge(self):
        Submission.objects.filter(id=self.submission.id).update(result=JudgeStatus.JUDGING)
        self._push_status(JudgeStatus.JUDGING, "judging")

        try:
            ref_sql, mode, order_sensitive, init_scripts = self._load_problem_config()
        except SQLProblemConfigError as e:
            self._system_error(str(e))
            return

        cases = []
        for index, init_sql in enumerate(init_scripts, start=1):
            try:
                case = run_case(
                    init_sql,
                    ref_sql,
                    self.submission.code,
                    mode=mode,
                    order_sensitive=order_sensitive,
                    time_limit_ms=self.problem.time_limit,
                    memory_limit_mb=self.problem.memory_limit,
                )
            except SQLCaseError as e:
                # 初始化/标准答案执行失败，属出题配置问题
                self._system_error(e.message)
                return
            case["test_case"] = str(index)
            # 语法错误与数据无关，首个测试点即可确认，整题按编译错误处理（ACM 不罚时，前端展示 err_info）
            if index == 1 and case["result"] == JudgeStatus.COMPILE_ERROR:
                self._process_judge_result({"err": "CompileError", "data": case["error_message"]})
                return
            cases.append(case)

        # 判题给出的中文提示（授权拒绝/超时/内存/无结果集）只存在测试点的 error_message 里，
        # 前端只读 statistic_info.err_info，这里把首个失败测试点的提示提上来，否则学生看不到原因
        failed = next((c for c in cases if c["result"] != JudgeStatus.ACCEPTED), None)
        if failed and failed["error_message"]:
            self.submission.statistic_info["err_info"] = failed["error_message"]
        else:
            # rejudge 时清掉上一轮的残留提示
            self.submission.statistic_info.pop("err_info", None)

        self._process_judge_result({"err": None, "data": cases})

    def _system_error(self, message):
        logger.error(f"SQL judge system error, submission {self.submission.id}, problem {self.problem.id}: {message}")
        Submission.objects.filter(id=self.submission.id).update(result=JudgeStatus.SYSTEM_ERROR, statistic_info={"err_info": message})
        self._push_status(JudgeStatus.SYSTEM_ERROR, "error")

    def _load_problem_config(self):
        """校验并加载 SQL 题配置，返回 (标准答案, mode, order_sensitive, 各测试点初始化脚本)。"""
        sql_config = self.problem.sql_config or {}
        mode = sql_config.get("mode")
        if mode not in ("query", "modify"):
            raise SQLProblemConfigError("题目缺少 SQL 配置（题型）")

        ref_sql = None
        for item in self.problem.answers or []:
            if item.get("language") == "SQL" and item.get("code", "").strip():
                ref_sql = item["code"]
                break
        if not ref_sql:
            raise SQLProblemConfigError("题目缺少 SQL 标准答案")

        test_case_dir = os.path.join(settings.TEST_CASE_DIR, self.problem.test_case_id)
        try:
            with open(os.path.join(test_case_dir, "info"), encoding="utf-8") as f:
                info = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise SQLProblemConfigError(f"测试点信息读取失败: {e}")
        if not info.get("sql"):
            raise SQLProblemConfigError("测试点不是 SQL 类型，请重新上传 SQL 测试点压缩包")

        init_scripts = []
        # 按 "1","2",… 自然序遍历，保证测试点顺序稳定
        for key in sorted(info["test_cases"].keys(), key=natural_sort_key):
            input_name = info["test_cases"][key]["input_name"]
            try:
                with open(os.path.join(test_case_dir, input_name), encoding="utf-8") as f:
                    init_scripts.append(f.read())
            except OSError as e:
                raise SQLProblemConfigError(f"测试点脚本 {input_name} 读取失败: {e}")
        if not init_scripts:
            raise SQLProblemConfigError("题目没有任何测试点")
        return ref_sql, mode, sql_config.get("order_sensitive", False), init_scripts
