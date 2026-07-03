# SQL 题数据化展示实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SQL 题的题目页展示真实的数据表和期望结果（自动从测试点 1 + 标准答案生成），替代不适用的「输入/输出/例子」文本区块。

**Architecture:** 后端在 `judge/sql_runner.py` 新增 `build_display()`（内存 sqlite 跑初始化脚本 + 标准答案，导出结构化 JSON），管理端保存题目时在 `ProblemBase.common_checks` 中生成并写入新字段 `Problem.sql_display`。前端学生端用 `sql_config` 判断 SQL 题，隐藏输入/输出/例子区块，改渲染「数据表」「期望结果」表格；管理端编辑页对 SQL 题隐藏无意义的表单项。

**Tech Stack:** Django 6 + DRF（后端，`OnlineJudge/` 仓库）、Vue 3 + TypeScript + Naive UI（前端，`ojnext/` 仓库）。

**Spec:** `OnlineJudge/docs/superpowers/specs/2026-07-03-sql-problem-display-design.md`

## Global Constraints

- **不写任何新测试**（项目测试政策：Do not write new tests）。验证靠 `ruff check`、`python manage.py shell -c` 手动执行、`npm run build`。
- 两个子项目是**独立 git 仓库**：后端提交在 `OnlineJudge/`，前端提交在 `ojnext/`，根目录没有 git。
- 后端 lint：`ruff check .`（180 列，双引号）。前端格式化：`npm run fmt`。
- 展示行数上限 20 行（`DISPLAY_ROW_LIMIT = 20`）；判题行数上限沿用现有 `ROW_LIMIT = 10_000`。
- `sql_display` 只由服务端生成，客户端不可提交该字段（不加入 `CreateOrEditProblemSerializer`）。
- 错误消息用中文（与 `sql_runner.py` 现有消息一致），面向出题人。

---

### Task 1: 后端 `build_display()` 生成展示数据

**Files:**
- Modify: `OnlineJudge/judge/sql_runner.py`（文件末尾追加）

**Interfaces:**
- Consumes: 本文件已有的 `_new_db`、`_execute_trusted`、`_dump_tables`、`split_statements`、`_truncate`、`SQLCaseError`、`ROW_LIMIT`、`PROGRESS_STEP`
- Produces: `build_display(init_sql: str, ref_sql: str, mode: str, *, memory_limit_mb: int = 64) -> dict`，失败抛 `SQLCaseError`。返回结构：
  - `{"tables": [TableDump, ...], "expected": ExpectedQuery | ExpectedModify}`
  - `TableDump = {"name": str, "columns": [{"name": str, "type": str}], "rows": [[原始值]], "total_rows": int, "truncated": bool}`
  - `ExpectedQuery = {"columns": [str], "rows": [[原始值]], "total_rows": int, "truncated": bool}`（query 模式）
  - `ExpectedModify = {"changed_tables": [TableDump, ...]}`（modify 模式，只含执行标准答案后内容有变化的表）
  - 被标准答案 DROP 的表以 `{"dropped": true, "rows": [], "total_rows": 0}` 条目出现（columns 取初始结构）；标准答案未改任何表时抛 SQLCaseError

- [ ] **Step 1: 在 `sql_runner.py` 末尾追加展示数据生成代码**

在文件顶部常量区（`ERROR_MESSAGE_MAX_LEN = 200` 之后）加：

```python
# 题目页展示的行数上限（示例数据/期望结果）
DISPLAY_ROW_LIMIT = 20
```

在文件末尾追加：

```python
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
            expected = {"changed_tables": _dump_display_tables(conn, only=changed)}
        return {"tables": tables, "expected": expected}
    finally:
        conn.close()
```

- [ ] **Step 2: 手动验证 query 模式与 modify 模式**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge && python manage.py shell -c "
from judge.sql_runner import build_display
init = '''CREATE TABLE students(id INTEGER PRIMARY KEY, name TEXT, score REAL);
INSERT INTO students VALUES (1,'小明',95),(2,'小红',88),(3,'小刚',91);'''
import json
r = build_display(init, \"SELECT name, score FROM students WHERE score > 90;\", 'query')
print(json.dumps(r, ensure_ascii=False, indent=1))
r2 = build_display(init, \"DELETE FROM students WHERE score < 90;\", 'modify')
print(json.dumps(r2, ensure_ascii=False, indent=1))
"
```

Expected：
- query 输出 `tables` 含 students 表（3 行、columns 带 INTEGER/TEXT/REAL 类型），`expected.columns == ["name", "score"]`、`expected.rows == [["小明", 95.0], ["小刚", 91.0]]`
- modify 输出 `expected.changed_tables` 只含 students（2 行，小红被删）

再验证错误路径：

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge && python manage.py shell -c "
from judge.sql_runner import build_display, SQLCaseError
try:
    build_display('CREATE TABLE t(a);', 'SELEC bad;', 'query')
except SQLCaseError as e:
    print('OK:', e.message)
"
```

Expected：打印 `OK: 标准答案执行失败: ...syntax error...`

- [ ] **Step 3: Lint**

Run: `cd /home/xuyue/Projects/OJ/OnlineJudge && ruff check judge/sql_runner.py && ruff format --check judge/sql_runner.py`
Expected: 无报错（有格式问题就跑 `ruff format judge/sql_runner.py`）

- [ ] **Step 4: Commit（OnlineJudge 仓库）**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge && git add judge/sql_runner.py && git commit -m "feat: SQL 题展示数据生成 build_display

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: 后端 `sql_display` 字段 + 保存时生成

**Files:**
- Modify: `OnlineJudge/problem/models.py`（`sql_config` 字段之后，约 line 90）
- Create: `OnlineJudge/problem/migrations/`（makemigrations 自动生成）
- Modify: `OnlineJudge/problem/serializers.py:62-65`（放宽 input/output/samples 校验）
- Modify: `OnlineJudge/problem/views/admin.py`（`ProblemBase.common_checks`，约 line 192-216）

**Interfaces:**
- Consumes: Task 1 的 `build_display(init_sql, ref_sql, mode, *, memory_limit_mb=64)` 与 `SQLCaseError`（`e.message` 属性）
- Produces: `Problem.sql_display`（JSONField，null=True，结构即 Task 1 返回值）；随现有 `ProblemSerializer` / `ProblemSafeSerializer` / `ProblemAdminSerializer` 自动下发（三者均为 ModelSerializer 且未排除该字段）。`common_checks` 在 SQL 题保存时填充 `data["sql_display"]`，非 SQL 题置 None。

- [ ] **Step 1: 模型加字段**

`problem/models.py`，紧跟 `sql_config` 字段之后加：

```python
    # SQL 题展示数据（保存题目时由测试点1+标准答案自动生成，见 judge/sql_runner.build_display），非 SQL 题为 None
    sql_display = models.JSONField(null=True, blank=True, default=None)
```

- [ ] **Step 2: 生成并应用迁移**

Run: `cd /home/xuyue/Projects/OJ/OnlineJudge && python manage.py makemigrations problem && python manage.py migrate problem`
Expected: 生成一个 `Add field sql_display to problem` 迁移并应用成功

- [ ] **Step 3: 放宽序列化器校验**

`problem/serializers.py` 中 `CreateOrEditProblemSerializer` 的三个字段改为（原来 `input_description` / `output_description` 不允许空、`samples` 不允许空列表；SQL 题不填这些，改由 `common_checks` 对非 SQL 题保持强校验）：

```python
    input_description = serializers.CharField(allow_blank=True)
    output_description = serializers.CharField(allow_blank=True)
    samples = serializers.ListField(child=CreateSampleSerializer(), allow_empty=True)
```

- [ ] **Step 4: `common_checks` 接入生成逻辑**

`problem/views/admin.py` 顶部 import 区加：

```python
from judge.sql_runner import SQLCaseError, build_display
```

`ProblemBase` 类改为（替换现有 `common_checks` 的 SQL 分支，并新增 `_build_sql_display` 方法）：

```python
class ProblemBase(APIView):
    def common_checks(self, request):
        data = request.data
        if data["rule_type"] == ProblemRuleType.OI:
            total_score = 0
            for item in data["test_case_score"]:
                if item["score"] <= 0:
                    return "Invalid score"
                else:
                    total_score += item["score"]
            data["total_score"] = total_score
        data["languages"] = list(data["languages"])

        # SQL 题校验：.sql 测试点与 .in/.out 沙箱判题互斥，SQL 必须是唯一语言
        if "SQL" in data["languages"]:
            if data["languages"] != ["SQL"]:
                return "SQL problem cannot be mixed with other languages"
            if not data.get("sql_config"):
                return "SQL problem requires sql_config"
            has_sql_answer = any(item.get("language") == "SQL" and item.get("code", "").strip() for item in (data.get("answers") or []))
            if not has_sql_answer:
                return "SQL problem requires a SQL reference answer"
            return self._build_sql_display(data)
        else:
            # 序列化器已放宽（SQL 题不填这些），非 SQL 题在此保持原有强校验
            if not data["input_description"] or not data["output_description"]:
                return "Input and output description are required"
            if not data["samples"]:
                return "Samples are required"
            # 防脏数据：非 SQL 题不应携带 SQL 配置
            data["sql_config"] = None
            data["sql_display"] = None

    def _build_sql_display(self, data):
        """SQL 题：用测试点1的初始化脚本 + 标准答案生成题目页展示数据。返回错误信息字符串，成功返回 None。"""
        test_case_dir = os.path.join(settings.TEST_CASE_DIR, data["test_case_id"])
        try:
            with open(os.path.join(test_case_dir, "info"), encoding="utf-8") as f:
                info = json.load(f)
        except (OSError, json.JSONDecodeError):
            return "测试点信息读取失败，请重新上传测试点"
        if not info.get("sql"):
            return "测试点不是 SQL 类型，请重新上传 SQL 测试点压缩包"
        keys = sorted(info["test_cases"].keys(), key=natural_sort_key)
        if not keys:
            return "题目没有任何测试点"
        input_name = info["test_cases"][keys[0]]["input_name"]
        try:
            with open(os.path.join(test_case_dir, input_name), encoding="utf-8") as f:
                init_sql = f.read()
        except OSError:
            return f"测试点脚本 {input_name} 读取失败"
        ref_sql = next(item["code"] for item in data["answers"] if item.get("language") == "SQL" and item.get("code", "").strip())
        try:
            data["sql_display"] = build_display(init_sql, ref_sql, data["sql_config"]["mode"])
        except SQLCaseError as e:
            return f"SQL 展示数据生成失败: {e.message}"
```

说明：`os`、`json`、`settings`、`natural_sort_key` 均已在该文件 import。`post`（`Problem.objects.create(**data)`）和 `put`（`setattr` 循环）都直接消费 `data`，`sql_display` 无需再改动创建/更新代码。`ContestProblemAPI` 复用同一 `common_checks`，比赛 SQL 题自动生效。

- [ ] **Step 5: 手动验证 `_build_sql_display` 全链路**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge && python manage.py shell -c "
import json, os
from django.conf import settings
from problem.views.admin import ProblemBase

# 造一个假测试点目录
tcid = 'plan_verify_sql_display'
d = os.path.join(settings.TEST_CASE_DIR, tcid)
os.makedirs(d, exist_ok=True)
open(os.path.join(d, '1.sql'), 'w').write(\"CREATE TABLE t(a INTEGER, b TEXT); INSERT INTO t VALUES (1,'x'),(2,'y');\")
open(os.path.join(d, 'info'), 'w').write(json.dumps({'sql': True, 'test_cases': {'1': {'input_name': '1.sql', 'output_name': '1.sql'}}}))

data = {'test_case_id': tcid, 'answers': [{'language': 'SQL', 'code': 'SELECT b FROM t ORDER BY a;'}], 'sql_config': {'mode': 'query'}}
err = ProblemBase()._build_sql_display(data)
print('err:', err)
print(json.dumps(data['sql_display'], ensure_ascii=False))
import shutil; shutil.rmtree(d)
"
```

Expected: `err: None`，`sql_display` 含 `tables`（表 t，2 行）与 `expected`（columns `["b"]`，rows `[["x"],["y"]]`）

- [ ] **Step 6: Lint + Django 检查**

Run: `cd /home/xuyue/Projects/OJ/OnlineJudge && ruff check problem/ && python manage.py check`
Expected: 无报错

- [ ] **Step 7: Commit（OnlineJudge 仓库）**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge && git add problem/ && git commit -m "feat: 保存 SQL 题时自动生成 sql_display 展示数据

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: 学生端「数据表 / 期望结果」渲染

**Files:**
- Modify: `ojnext/src/utils/types.ts`（`SQLConfig` 接口之后，约 line 73；`Problem` 接口的 `sql_config` 字段之后，约 line 175）
- Create: `ojnext/src/oj/problem/components/SQLDataTable.vue`
- Modify: `ojnext/src/oj/problem/components/ProblemContent.vue`

**Interfaces:**
- Consumes: 后端 `problem.sql_display`（结构见 Task 1 Produces）、`problem.sql_config`
- Produces: `SQLDataTable.vue` 组件，props：`columns: { name: string; type?: string }[]`、`rows: (string | number | null)[][]`、`totalRows?: number`、`truncated?: boolean`；类型 `SQLDisplay`、`SQLDisplayTable`、`SQLDisplayColumn`（Task 4 不依赖，仅本任务内使用）

- [ ] **Step 1: types.ts 加类型**

`SQLConfig` 接口定义之后追加：

```typescript
export interface SQLDisplayColumn {
  name: string
  type?: string
}

export interface SQLDisplayTable {
  name: string
  columns: SQLDisplayColumn[]
  rows: (string | number | null)[][]
  total_rows: number
  truncated: boolean
}

export interface SQLDisplay {
  tables: SQLDisplayTable[]
  expected:
    | {
        columns: string[]
        rows: (string | number | null)[][]
        total_rows: number
        truncated: boolean
      }
    | { changed_tables: SQLDisplayTable[] }
}
```

`Problem` 接口中 `sql_config?: SQLConfig | null` 之后加：

```typescript
  // SQL 题展示数据（后端保存题目时自动生成）
  sql_display?: SQLDisplay | null
```

- [ ] **Step 2: 新建 `SQLDataTable.vue`**

```vue
<script setup lang="ts">
import type { SQLDisplayColumn } from "utils/types"

defineProps<{
  columns: SQLDisplayColumn[]
  rows: (string | number | null)[][]
  totalRows?: number
  truncated?: boolean
}>()
</script>

<template>
  <n-table class="sqlTable" size="small" :single-line="false">
    <thead>
      <tr>
        <th v-for="(col, i) in columns" :key="i">
          {{ col.name }}
          <span v-if="col.type" class="colType">{{ col.type }}</span>
        </th>
      </tr>
    </thead>
    <tbody>
      <tr v-if="rows.length === 0">
        <td :colspan="columns.length" class="nullCell">（空表）</td>
      </tr>
      <tr v-for="(row, i) in rows" :key="i">
        <td v-for="(v, j) in row" :key="j" :class="{ nullCell: v === null }">
          {{ v === null ? "NULL" : v }}
        </td>
      </tr>
    </tbody>
  </n-table>
  <p v-if="truncated" class="truncNote">
    共 {{ totalRows }} 行，仅展示前 {{ rows.length }} 行
  </p>
</template>

<style scoped>
.sqlTable {
  margin-bottom: 8px;
}

.colType {
  font-size: 12px;
  opacity: 0.55;
  margin-left: 4px;
  font-weight: normal;
}

.nullCell {
  opacity: 0.45;
  font-style: italic;
}

.truncNote {
  font-size: 13px;
  opacity: 0.65;
  margin: 0 0 8px;
}
</style>
```

（`n-table` 由 unplugin 自动导入，无需手动 import。）

- [ ] **Step 3: `ProblemContent.vue` 集成**

script 部分，在 `import { getSimilarProblems } from "oj/api"` 之后加：

```typescript
import SQLDataTable from "./SQLDataTable.vue"
```

在 `const problemSetId = ...` 附近加计算属性：

```typescript
// SQL 题：隐藏输入/输出/例子，改为渲染数据表与期望结果
const isSQL = computed(() => !!problem.value?.sql_config)
const sqlDisplay = computed(() => problem.value?.sql_display ?? null)
const sqlExpectedQuery = computed(() => {
  const exp = sqlDisplay.value?.expected
  return exp && "columns" in exp ? exp : null
})
const sqlChangedTables = computed(() => {
  const exp = sqlDisplay.value?.expected
  return exp && "changed_tables" in exp ? exp.changed_tables : []
})
```

template 部分三处修改：

(a) 「输入」「输出」两个区块（`<p class="title">…输入…</p>` + `MdPreview` 到 `…输出…` + `MdPreview`，现 line 272-294）整体包进 `<template v-if="!isSQL">…</template>`。

(b) 例子循环 `<div v-for="(sample, index) of samples" :key="index">…</div>`（现 line 337-380）整体包进 `<template v-if="!isSQL">…</template>`（注意 v-if 不能与 v-for 放同一元素上）。

(c) 在 (a) 的 `</template>` 之后（即描述区块后、提示区块前）插入 SQL 区块：

```html
    <template v-if="isSQL && sqlDisplay">
      <p class="title" :style="style">
        <n-flex align="center">
          <Icon icon="devicon:sqlite"></Icon>
          数据表
        </n-flex>
      </p>
      <div v-for="t in sqlDisplay.tables" :key="t.name">
        <p class="sqlTableName">{{ t.name }}</p>
        <SQLDataTable
          :columns="t.columns"
          :rows="t.rows"
          :total-rows="t.total_rows"
          :truncated="t.truncated"
        />
      </div>

      <p class="title" :style="style">
        <n-flex align="center">
          <Icon icon="streamline-ultimate-color:check-button"></Icon>
          期望结果
        </n-flex>
      </p>
      <template v-if="sqlExpectedQuery">
        <SQLDataTable
          :columns="sqlExpectedQuery.columns.map((name) => ({ name }))"
          :rows="sqlExpectedQuery.rows"
          :total-rows="sqlExpectedQuery.total_rows"
          :truncated="sqlExpectedQuery.truncated"
        />
        <p v-if="!problem.sql_config?.order_sensitive" class="sqlNote">
          结果顺序不限
        </p>
      </template>
      <div v-for="t in sqlChangedTables" :key="t.name">
        <p class="sqlTableName">执行后的 {{ t.name }} 表</p>
        <SQLDataTable
          :columns="t.columns"
          :rows="t.rows"
          :total-rows="t.total_rows"
          :truncated="t.truncated"
        />
      </div>
    </template>
```

style 部分追加：

```css
.sqlTableName {
  font-weight: 600;
  margin: 8px 0 4px;
  font-family: "Monaco";
}

.sqlNote {
  font-size: 13px;
  opacity: 0.65;
  margin: 0 0 8px;
}
```

- [ ] **Step 4: 构建验证**

Run: `cd /home/xuyue/Projects/OJ/ojnext && npm run build`
Expected: 构建成功、无 TypeScript 报错

- [ ] **Step 5: 格式化 + Commit（ojnext 仓库）**

```bash
cd /home/xuyue/Projects/OJ/ojnext && npm run fmt && git add src/utils/types.ts src/oj/problem/components/SQLDataTable.vue src/oj/problem/components/ProblemContent.vue && git commit -m "feat: SQL 题展示数据表与期望结果

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: 管理端编辑页隐藏 SQL 题无关表单

**Files:**
- Modify: `ojnext/src/admin/problem/detail.vue`

**Interfaces:**
- Consumes: 该文件已有的 `isSQLProblem` computed（line 184）、`validateProblem()`、`submit()`
- Produces: 无对外接口；SQL 题提交时 `samples` 置空数组、`input_description`/`output_description` 不做必填校验（后端 Task 2 已放宽）

- [ ] **Step 1: 模板隐藏三处表单**

(a) 「输入的描述」「输出的描述」两个 `TextEditor`（line 594-603）的 `v-if="ready"` 改为 `v-if="ready && !isSQLProblem"`。

(b) 样例编辑块与「添加用例」按钮（line 604-633，`<div class="box" v-for=...>` 和 `<n-button class="addSamples box" ...>`）整体包进 `<template v-if="!isSQLProblem">…</template>`。

- [ ] **Step 2: `validateProblem()` 跳过 SQL 题的相关校验**

题目描述校验（line 345-352）改为：

```typescript
  else if (
    !problem.value.description ||
    (!isSQLProblem.value &&
      (!problem.value.input_description || !problem.value.output_description))
  ) {
```

样例两处校验（line 354、359-363）分别加 `!isSQLProblem.value &&` 前缀：

```typescript
  else if (!isSQLProblem.value && problem.value.samples.length == 0) {
```

```typescript
  else if (
    !isSQLProblem.value &&
    problem.value.samples.some(
      (sample) => sample.output === "" || sample.input === "",
    )
  ) {
```

- [ ] **Step 3: 提交时清空 SQL 题的样例**

`filterAnswers()` 函数（line 429-433）之后加：

```typescript
function filterSamplesForSQL() {
  // SQL 题不展示样例；后端 CreateSampleSerializer 也不接受空字符串样例
  if (isSQLProblem.value) problem.value.samples = []
}
```

`submit()` 中在 `filterAnswers()` 调用之后加一行 `filterSamplesForSQL()`。

- [ ] **Step 4: 构建验证**

Run: `cd /home/xuyue/Projects/OJ/ojnext && npm run build`
Expected: 构建成功

- [ ] **Step 5: 格式化 + Commit（ojnext 仓库）**

```bash
cd /home/xuyue/Projects/OJ/ojnext && npm run fmt && git add src/admin/problem/detail.vue && git commit -m "feat: 管理端 SQL 题隐藏输入输出描述与样例表单

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: 端到端人工验收

**Files:** 无代码改动，纯验证。

**Interfaces:**
- Consumes: Task 1-4 全部成果；本地服务（`docker-compose up -d oj-postgres oj-redis`、`python dev.py`、`npm start`）

- [ ] **Step 1: 起服务**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge && docker-compose up -d oj-postgres oj-redis
cd /home/xuyue/Projects/OJ/OnlineJudge && python dev.py   # 后台/另开终端
cd /home/xuyue/Projects/OJ/ojnext && npm start            # 后台/另开终端
```

- [ ] **Step 2: 管理端建一道 SQL 查询题**

浏览器（或 agent-browser）操作 `http://localhost:5173`：
1. 管理后台新建题目，语言勾选 SQL → 确认「输入的描述」「输出的描述」「测试样例」表单已隐藏
2. 上传 SQL 测试点 zip（内含 `1.sql`：建表 + 插数据脚本），填写 SQL 标准答案，保存
3. Expected: 保存成功；故意把标准答案改成语法错误再保存，Expected: 报错「SQL 展示数据生成失败: 标准答案执行失败…」

- [ ] **Step 3: 学生端查看题目页**

打开该题：
- Expected: 无「输入/输出/例子」区块；有「数据表」区块（表名 + 列类型标注 + 数据行）和「期望结果」区块（结果表 + "结果顺序不限"提示）
- 提交正确 SQL，Expected: Accepted（确认判题链路未受影响）

- [ ] **Step 4: 建一道 modify 题验证 changed_tables**

同流程建 `mode=modify` 的题（标准答案为 UPDATE/DELETE），Expected: 题目页「期望结果」显示「执行后的 XX 表」，且只含被修改的表。
