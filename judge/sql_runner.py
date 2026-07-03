"""SQL 题判题核心：在内存 SQLite 中分别执行标准答案和学生 SQL 并比对结果。

查询题（mode="query"）比对最后一条 SELECT 的结果集；
增删改题（mode="modify"）比对执行后所有用户表的最终状态。
学生 SQL 通过 authorizer（禁 ATTACH/PRAGMA，查询题只读）、
progress_handler（墙钟超时）和 max_page_count（内存上限）三重防护。
"""

import sqlite3
import time

from submission.models import JudgeStatus

# 单结果集/单表最大行数，防 CROSS JOIN 撑爆 worker 内存
ROW_LIMIT = 10_000
# progress_handler 检查粒度（SQLite VM 指令数）
PROGRESS_STEP = 1_000
ERROR_MESSAGE_MAX_LEN = 200

# 题目页展示的行数上限（示例数据/期望结果）
DISPLAY_ROW_LIMIT = 20

# prepare 阶段的语法类错误，映射为 COMPILE_ERROR
_SYNTAX_ERROR_MARKERS = ("syntax error", "unrecognized token", "incomplete input")

# 两种模式都禁止的授权码：挂载外部库 / 数据库参数
_DENIED_ALWAYS = {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH, sqlite3.SQLITE_PRAGMA}

# 查询题允许的授权码（白名单外一律拒绝，防先 INSERT 伪造数据再 SELECT）
_QUERY_MODE_ALLOWED = {getattr(sqlite3, name) for name in ("SQLITE_SELECT", "SQLITE_READ", "SQLITE_FUNCTION", "SQLITE_RECURSIVE", "SQLITE_TRANSACTION") if hasattr(sqlite3, name)}


class SQLCaseError(Exception):
    """携带 JudgeStatus 的判题异常。SYSTEM_ERROR 级别（出题配置问题）会传播到 dispatcher。"""

    def __init__(self, result, message):
        super().__init__(message)
        self.result = result
        self.message = message


def _truncate(message):
    message = str(message)
    if len(message) > ERROR_MESSAGE_MAX_LEN:
        return message[:ERROR_MESSAGE_MAX_LEN] + "..."
    return message


def split_statements(script):
    """用 sqlite3.complete_statement 累积切分多条语句，正确处理字符串/注释里的分号；末尾缺分号自动补。"""
    statements = []
    buf = ""
    for part in script.split(";"):
        buf += part + ";"
        if sqlite3.complete_statement(buf):
            stmt = buf.strip()
            buf = ""
            if stmt and stmt != ";":
                statements.append(stmt)
    # 残句（未闭合的引号/注释，或末尾缺分号但上面已补），交给 execute 报错或执行
    remainder = buf.strip()
    if remainder and remainder != ";":
        statements.append(remainder)
    return statements


def _canonical_value(v):
    """值归一化并打类型标签，防止 NULL/"NULL"、1/"1" 碰撞；数值统一比对（1 == 1.0，浮点 6 位有效数字）。"""
    if v is None:
        return ("null",)
    if isinstance(v, int):
        return ("num", str(v))
    if isinstance(v, float):
        if v.is_integer() and abs(v) < 2**53:
            return ("num", str(int(v)))
        return ("num", format(v, ".6g"))
    if isinstance(v, bytes):
        return ("blob", v.hex())
    return ("str", str(v))


def _canonical_row(row):
    return tuple(_canonical_value(v) for v in row)


def _new_db(memory_limit_mb):
    conn = sqlite3.connect(":memory:", isolation_level=None)  # autocommit，脚本行为可预期
    conn.execute("PRAGMA page_size=4096")
    # 4096B/页 × 256 页/MB，超限报 "database or disk is full"
    conn.execute(f"PRAGMA max_page_count={max(int(memory_limit_mb), 1) * 256}")
    return conn


def _execute_statements(conn, script, deadline=None):
    """逐条执行，返回最后一条产生结果集的语句的 (列数, 行列表)；无结果集返回 None。"""
    last_result = None
    for stmt in split_statements(script):
        if deadline is not None and time.monotonic() > deadline:
            raise sqlite3.OperationalError("interrupted")
        cursor = conn.execute(stmt)
        if cursor.description is not None:
            rows = cursor.fetchmany(ROW_LIMIT + 1)
            if len(rows) > ROW_LIMIT:
                raise SQLCaseError(JudgeStatus.MEMORY_LIMIT_EXCEEDED, f"查询结果超过 {ROW_LIMIT} 行")
            last_result = (len(cursor.description), [_canonical_row(r) for r in rows])
        cursor.close()
    return last_result


def _dump_tables(conn):
    """dump 所有用户表：{表名: (列数, 行多重集)}，行内排序，表状态天然无序。"""
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    tables = [r[0] for r in cursor.fetchall()]
    state = {}
    for table in tables:
        quoted = table.replace('"', '""')
        cur = conn.execute(f'SELECT * FROM "{quoted}"')
        rows = cur.fetchmany(ROW_LIMIT + 1)
        if len(rows) > ROW_LIMIT:
            raise SQLCaseError(JudgeStatus.MEMORY_LIMIT_EXCEEDED, f"表 {table} 超过 {ROW_LIMIT} 行")
        state[table] = (len(cur.description), sorted(_canonical_row(r) for r in rows))
    return state


def _execute_trusted(conn, script, deadline, error_prefix):
    """执行受信脚本，任何失败都是出题问题 → SYSTEM_ERROR。"""
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, PROGRESS_STEP)
    try:
        return _execute_statements(conn, script, deadline)
    except SQLCaseError as e:
        raise SQLCaseError(JudgeStatus.SYSTEM_ERROR, f"{error_prefix}: {e.message}")
    except sqlite3.Error as e:
        raise SQLCaseError(JudgeStatus.SYSTEM_ERROR, f"{error_prefix}: {_truncate(e)}")
    finally:
        conn.set_progress_handler(None, PROGRESS_STEP)


def _run_student(conn, script, mode, deadline):
    """带三重防护执行学生 SQL，异常映射为学生级 JudgeStatus。"""
    denied_hints = []

    def authorizer(action, arg1, arg2, db_name, trigger):
        if action in _DENIED_ALWAYS:
            denied_hints.append("禁止使用 ATTACH/DETACH/PRAGMA 等数据库管理语句")
            return sqlite3.SQLITE_DENY
        if mode == "query" and action not in _QUERY_MODE_ALLOWED:
            denied_hints.append("本题为查询题，禁止修改数据或表结构（INSERT/UPDATE/DELETE/CREATE 等）")
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    conn.set_authorizer(authorizer)
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, PROGRESS_STEP)
    try:
        last_result = _execute_statements(conn, script, deadline)
    except sqlite3.Error as e:
        # 注意：authorizer 拒绝抛的是 DatabaseError 基类而非 OperationalError，统一按消息映射
        msg = str(e)
        if "interrupted" in msg:
            raise SQLCaseError(JudgeStatus.CPU_TIME_LIMIT_EXCEEDED, "SQL 执行超时")
        if "database or disk is full" in msg:
            raise SQLCaseError(JudgeStatus.MEMORY_LIMIT_EXCEEDED, "数据量超出内存限制")
        if "not authorized" in msg or "prohibited" in msg:
            hint = denied_hints[-1] if denied_hints else "本题禁止使用该语句"
            raise SQLCaseError(JudgeStatus.RUNTIME_ERROR, hint)
        if any(marker in msg for marker in _SYNTAX_ERROR_MARKERS):
            raise SQLCaseError(JudgeStatus.COMPILE_ERROR, _truncate(msg))
        raise SQLCaseError(JudgeStatus.RUNTIME_ERROR, _truncate(msg))
    finally:
        conn.set_progress_handler(None, PROGRESS_STEP)
        conn.set_authorizer(None)

    if mode == "query":
        return last_result
    # dump 是我们自己的读取，不应吃学生的超时/授权限制（上面已清除）
    return _dump_tables(conn)


def _compare(expected, actual, mode, order_sensitive):
    if mode == "query":
        exp_cols, exp_rows = expected
        act_cols, act_rows = actual
        if exp_cols != act_cols:
            return False
        if order_sensitive:
            return exp_rows == act_rows
        return sorted(exp_rows) == sorted(act_rows)
    # modify: dump dict 里行已排序
    return expected == actual


def run_case(init_sql, ref_sql, student_sql, *, mode, order_sensitive, time_limit_ms, memory_limit_mb):
    """判一个测试点，返回与外部 judger 单测试点同构的 dict。

    学生错误（CE/WA/TLE/MLE/RE）体现在返回值里；
    出题配置错误（初始化/标准答案失败）抛 SQLCaseError(SYSTEM_ERROR)，由 dispatcher 处理。
    """
    time_limit_s = time_limit_ms / 1000
    # 受信脚本（初始化/标准答案）的运行上限放宽，避免出题数据较大时误报；仍防 worker 永久阻塞
    trusted_limit_s = max(time_limit_s * 5, 10)

    ref_conn = _new_db(memory_limit_mb)
    try:
        _execute_trusted(ref_conn, init_sql, time.monotonic() + trusted_limit_s, "初始化脚本执行失败")
        last_result = _execute_trusted(ref_conn, ref_sql, time.monotonic() + trusted_limit_s, "标准答案执行失败")
        if mode == "query":
            expected = last_result
        else:
            try:
                expected = _dump_tables(ref_conn)
            except SQLCaseError as e:
                raise SQLCaseError(JudgeStatus.SYSTEM_ERROR, f"标准答案结果超出限制: {e.message}")
    finally:
        ref_conn.close()
    if mode == "query" and expected is None:
        raise SQLCaseError(JudgeStatus.SYSTEM_ERROR, "标准答案未产生查询结果集")

    case = {
        "test_case": "",
        "result": JudgeStatus.ACCEPTED,
        "cpu_time": 0,
        "real_time": 0,
        "memory": 0,
        "signal": 0,
        "exit_code": 0,
        "error": 0,
        "output_md5": "",
        "error_message": None,
    }

    stu_conn = _new_db(memory_limit_mb)
    try:
        _execute_trusted(stu_conn, init_sql, time.monotonic() + trusted_limit_s, "初始化脚本执行失败")
        start = time.monotonic()
        try:
            actual = _run_student(stu_conn, student_sql, mode, start + time_limit_s)
        except SQLCaseError as e:
            elapsed = int((time.monotonic() - start) * 1000)
            case.update(result=e.result, error_message=e.message, cpu_time=elapsed, real_time=elapsed)
            return case
        elapsed = int((time.monotonic() - start) * 1000)
    finally:
        stu_conn.close()

    case["cpu_time"] = case["real_time"] = elapsed
    if mode == "query" and actual is None:
        case.update(result=JudgeStatus.WRONG_ANSWER, error_message="提交的 SQL 未产生查询结果集")
    elif not _compare(expected, actual, mode, order_sensitive):
        case["result"] = JudgeStatus.WRONG_ANSWER
    return case


def _display_value(v):
    """转为 JSON 可序列化的展示值；bytes 转 hex，None/数值/字符串原样。"""
    if isinstance(v, bytes):
        return v.hex()
    return v


def _dump_display_tables(conn, only=None):
    """按建表顺序 dump 用户表的原始行用于展示（区别于 _dump_tables 的归一化判题态）。

    only 为表名集合时只导出这些表。
    """
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [r[0] for r in cursor.fetchall()]
    result = []
    for table in tables:
        if only is not None and table not in only:
            continue
        quoted = table.replace('"', '""')
        columns = [{"name": r[1], "type": r[2] or ""} for r in conn.execute(f'PRAGMA table_info("{quoted}")').fetchall()]
        total = conn.execute(f'SELECT COUNT(*) FROM "{quoted}"').fetchone()[0]
        rows = conn.execute(f'SELECT * FROM "{quoted}" LIMIT {DISPLAY_ROW_LIMIT}').fetchall()
        result.append(
            {
                "name": table,
                "columns": columns,
                "rows": [[_display_value(v) for v in row] for row in rows],
                "total_rows": total,
                "truncated": total > DISPLAY_ROW_LIMIT,
            }
        )
    return result


def build_display(init_sql, ref_sql, mode, *, memory_limit_mb=64):
    """生成题目页展示数据：初始数据表 + 期望结果。

    供管理端保存题目时调用；任何失败抛 SQLCaseError（出题配置问题，调用方转为报错信息）。
    """
    trusted_limit_s = 10
    conn = _new_db(memory_limit_mb)
    try:
        _execute_trusted(conn, init_sql, time.monotonic() + trusted_limit_s, "初始化脚本执行失败")
        tables = _dump_display_tables(conn)
        if mode == "query":
            expected = None
            deadline = time.monotonic() + trusted_limit_s
            conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, PROGRESS_STEP)
            try:
                for stmt in split_statements(ref_sql):
                    cursor = conn.execute(stmt)
                    if cursor.description is not None:
                        columns = [d[0] for d in cursor.description]
                        rows = cursor.fetchmany(ROW_LIMIT + 1)
                        if len(rows) > ROW_LIMIT:
                            raise SQLCaseError(JudgeStatus.SYSTEM_ERROR, f"标准答案结果超过 {ROW_LIMIT} 行")
                        expected = {
                            "columns": columns,
                            "rows": [[_display_value(v) for v in row] for row in rows[:DISPLAY_ROW_LIMIT]],
                            "total_rows": len(rows),
                            "truncated": len(rows) > DISPLAY_ROW_LIMIT,
                        }
                    cursor.close()
            except sqlite3.Error as e:
                msg = "超时" if "interrupted" in str(e) else _truncate(e)
                raise SQLCaseError(JudgeStatus.SYSTEM_ERROR, f"标准答案执行失败: {msg}")
            finally:
                conn.set_progress_handler(None, PROGRESS_STEP)
            if expected is None:
                raise SQLCaseError(JudgeStatus.SYSTEM_ERROR, "标准答案未产生查询结果集")
        else:
            before = _dump_tables(conn)
            _execute_trusted(conn, ref_sql, time.monotonic() + trusted_limit_s, "标准答案执行失败")
            after = _dump_tables(conn)
            changed = {name for name in set(before) | set(after) if before.get(name) != after.get(name)}
            if not changed:
                raise SQLCaseError(JudgeStatus.SYSTEM_ERROR, "标准答案未修改任何表数据，请检查题目配置")
            changed_tables = _dump_display_tables(conn, only=changed)
            # 被标准答案 DROP 的表已不在库中，用初始展示数据补齐条目（前端据 dropped 提示“表已删除”）
            existing = {t["name"] for t in changed_tables}
            for t in tables:
                if t["name"] in changed and t["name"] not in existing:
                    changed_tables.append({"name": t["name"], "columns": t["columns"], "rows": [], "total_rows": 0, "truncated": False, "dropped": True})
            expected = {"changed_tables": changed_tables}
        return {"tables": tables, "expected": expected}
    finally:
        conn.close()
