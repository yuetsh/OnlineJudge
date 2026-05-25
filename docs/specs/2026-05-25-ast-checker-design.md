# AST Checker Design Spec

> Tree-sitter-based code structure validation for the Online Judge platform.

## 1. Overview

Teachers can configure per-problem, per-language rules that validate student code structure (e.g., "must use while loop", "cannot use for loop", "must call print()"). Rules use a predefined engine library — admins never write raw tree-sitter queries.

### Critical Invariant

AST check runs **AFTER** normal judging, **ONLY** on submissions that would be AC. If AST fails, the displayed result is `AST_CHECK_FAILED`, but **all statistics treat it as AC** — problem `accepted_number`, user profile solved status, contest ranking. The student solved the problem correctly; they just didn't use the required syntax.

### Goals

- Enforce coding constraints for pedagogical purposes (beginner programming courses)
- Support all 6 languages: Python3, C, C++, Java, Golang, JavaScript (Python3 and C prioritized)
- Predefined rule library with parameterized engines
- Full admin UI for configuring rules per problem per language
- New `AST_CHECK_FAILED` judge status with clear error messages

### Non-Goals

- Output-aware checks ("禁止直接输出完整目标答案") — requires expected output, not AST
- String literal content matching (`.2f`, `03d` format specifiers) — deferred
- Custom tree-sitter query support for admins

---

## 2. New Judge Status

```python
class JudgeStatus(models.IntegerChoices):
    COMPILE_ERROR = -2
    WRONG_ANSWER = -1
    ACCEPTED = 0
    CPU_TIME_LIMIT_EXCEEDED = 1
    REAL_TIME_LIMIT_EXCEEDED = 2
    MEMORY_LIMIT_EXCEEDED = 3
    RUNTIME_ERROR = 4
    SYSTEM_ERROR = 5
    PENDING = 6
    JUDGING = 7
    PARTIALLY_ACCEPTED = 8
    AST_CHECK_FAILED = 10   # 9 is taken by frontend SubmissionStatus.submitting
```

Helper function in `submission/models.py`:

```python
def is_accepted(result):
    return result in (JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED)
```

---

## 3. Data Model

**Problem model** — new JSONField:

```python
ast_rules = models.JSONField(null=True, blank=True, default=None)
```

Schema:

```json
{
  "Python3": [
    {"engine": "must_exist_node", "target": "for_loop", "message": "必须使用 for 循环"},
    {"engine": "count_node", "target": "while_loop", "min": 2, "message": "while 循环至少出现 2 次"},
    {"engine": "must_call_function", "target": "print", "message": "必须调用 print()"},
    {"engine": "must_use_operator", "target": "+=", "message": "必须使用 += 运算符"},
    {"engine": "must_call_method", "target": "append", "message": "必须使用 append()"}
  ],
  "C": [
    {"engine": "must_exist_node", "target": "for_loop", "message": "必须使用 for 循环"}
  ]
}
```

`target` uses **language-agnostic logical names** (e.g., `for_loop`, `while_loop`). Each engine maps these to language-specific tree-sitter node types via the mapping layer. When `ast_rules` is `null` or the current language has no rules, AST checking is skipped entirely.

---

## 4. Submission Flow

```
SubmissionAPI.post()
  → create Submission(PENDING)
  → judge_task.send()
    → JudgeDispatcher.judge()
      → apply code template
      → choose judge server
      → send to judge server
      → process judge result
      → _compute_statistic_info()
      → if result == AC and ast_rules exist for this language:
          → AST check (NEW)
          → if AST fails:
              result = AST_CHECK_FAILED (display only)
              err_info = rule violation details
      → update_problem_status (treats AST_CHECK_FAILED as AC)
      → push WebSocket with final result
```

The check runs on `self.submission.code` (raw student code), not the template-wrapped version.

### Integration Code

```python
# In JudgeDispatcher.judge(), after _compute_statistic_info and result determination:

if self.submission.result == JudgeStatus.ACCEPTED:
    ast_rules = self.problem.ast_rules
    if ast_rules and language in ast_rules:
        from ast_checker.checker import check_ast
        passed, errors = check_ast(self.submission.code, language, ast_rules[language])
        if not passed:
            self.submission.result = JudgeStatus.AST_CHECK_FAILED
            self.submission.statistic_info["err_info"] = "\n".join(errors)

self.submission.save(update_fields=["result", "info", "statistic_info"])
```

### Statistics Storage

`statistic_info` uses the **actual result code** as the key: `{"0": 5, "10": 3, "-1": 20}`. This means:
- `accepted_number` = AC + AST_CHECK_FAILED combined (for overall acceptance rate)
- `statistic_info` retains the breakdown: 5 pure AC, 3 AST check failed, 20 WA
- Frontend statistics chart can show AST_CHECK_FAILED as a separate slice

### Profile Status Storage

When storing status in `acm_problems_status` / `oi_problems_status` / `contest_problems_status`, always store `JudgeStatus.ACCEPTED` (0), **never** `AST_CHECK_FAILED` (10). This ensures `my_status` shows as AC in the problem list and sidebar without special frontend handling.

---

## 5. Rule Engine

### Directory Structure

```
OnlineJudge/ast_checker/
├── __init__.py
├── checker.py              # Entry point: check_ast(code, language, rules) → (bool, errors)
├── engines/
│   ├── __init__.py         # Engine registry
│   ├── base.py             # BaseEngine abstract class
│   ├── node_exists.py      # must_exist_node / must_not_exist_node
│   ├── node_count.py       # count_node
│   ├── function_call.py    # must_call_function / must_not_call_function / count_function_call
│   ├── method_call.py      # must_call_method / must_not_call_method
│   ├── operator.py         # must_use_operator
│   ├── keyword_arg.py      # must_use_keyword_arg
│   ├── import_check.py     # must_import / must_not_import
│   └── structural.py       # nested_for, chained_comparison, swap_assignment, etc.
└── mappings/
    ├── __init__.py          # get_mapping(language) dispatcher
    ├── python.py
    ├── c.py
    ├── cpp.py
    ├── java.py
    ├── go.py
    └── javascript.py
```

### Engine Interface

```python
class BaseEngine:
    def check(self, tree, rule, language, mapping) -> list[str]:
        """Returns error messages (empty = pass)."""
        raise NotImplementedError
```

### Entry Point

```python
def check_ast(code: str, language: str, rules: list[dict]) -> tuple[bool, list[str]]:
    """
    Parse code with tree-sitter, run all rules, return (passed, error_messages).
    - Empty rules → (True, [])
    - Parse failure → (True, []) — skip AST check, let compiler report errors
    """
```

### Engine Catalog

| Engine | Parameters | Description |
|---|---|---|
| `must_exist_node` | `target` | Node type must appear at least once |
| `must_not_exist_node` | `target` | Node type must not appear |
| `count_node` | `target`, `min?`, `max?` | Node type count within [min, max] |
| `must_call_function` | `target` | Must call a function (e.g., `print`, `input`) |
| `must_not_call_function` | `target` | Must not call a function |
| `count_function_call` | `target`, `min?`, `max?` | Function call count within range |
| `must_call_method` | `target` | Must call a method (e.g., `.append()`) |
| `must_not_call_method` | `target` | Must not call a method |
| `must_use_operator` | `target`, `category?` | Must use a specific operator (see below) |
| `must_use_keyword_arg` | `target` (fn), `arg_name`, `value?` | Must use keyword arg in a call |
| `must_import` | `target` | Must import a module |
| `must_not_import` | `target` | Must not import a module |
| `must_use_variable_name` | `target` | Must assign to a variable with this name |
| `must_not_use_variable_name` | `target` | Must not use a variable with this name |
| `nested_for` | — | Must have nested for loops |
| `chained_comparison` | — | Must use chained comparison (Python only) |
| `swap_assignment` | — | Must use swap assignment (Python only) |
| `chain_assignment` | — | Must use chain assignment (Python only) |
| `must_use_recursion` | — | Must have a self-calling function |
| `no_recursion` | — | No function may call itself |

**Operator categories** (auto-inferred from `target`):
- Arithmetic (`+`,`-`,`*`,`/`,`//`,`%`,`**`) → binary expressions
- Augmented (`+=`,`-=`) → augmented assignments
- Comparison (`==`,`!=`,`>`,`>=`,`<`,`<=`) → comparisons
- Logical (`and`,`or`,`not`) → boolean/unary expressions
- Bitwise (`&`,`|`) → binary expressions

### Language Mapping

Each mapping file exports a dict translating logical names to tree-sitter node types:

```python
# mappings/python.py
PYTHON_MAPPING = {
    "for_loop": "for_statement",
    "while_loop": "while_statement",
    "if_statement": "if_statement",
    "else_clause": "else_clause",
    "elif_clause": "elif_clause",
    "break": "break_statement",
    "continue": "continue_statement",
    "function_definition": "function_definition",
    "return": "return_statement",
    "try_except": "try_statement",
    "with_statement": "with_statement",
    "list_comprehension": "list_comprehension",
    "list_literal": "list",
    "dict_literal": "dictionary",
    "set_literal": "set",
    "f_string": "format_string",
    "import": "import_statement",
    "import_from": "import_from_statement",
    "assignment": "assignment",
    "class_definition": "class_definition",
    # Operators map to themselves in Python
    "+": "+", "-": "-", "*": "*", "/": "/", "//": "//", "%": "%", "**": "**",
    "+=": "+=", "-=": "-=",
    "==": "==", "!=": "!=", ">": ">", ">=": ">=", "<": "<", "<=": "<=",
    "and": "and", "or": "or", "not": "not",
    "&": "&", "|": "|",
}

# mappings/c.py
C_MAPPING = {
    "for_loop": "for_statement",
    "while_loop": "while_statement",
    "if_statement": "if_statement",
    "else_clause": "else_clause",
    "break": "break_statement",
    "continue": "continue_statement",
    "function_definition": "function_definition",
    "return": "return_statement",
    "assignment": "assignment_expression",
    # ... C-specific mappings
}
```

### Known Limitations

- **Method call detection is name-based only**: `must_call_method("append")` matches any `.append()` regardless of object type. tree-sitter has no type information. Acceptable for teaching scenarios.
- **Structural rules are language-specific**: `swap_assignment`, `chained_comparison`, `chain_assignment` apply only to Python. The engine returns pass for unsupported languages.

---

## 6. Backend Impact Checklist

Every location that checks `JudgeStatus.ACCEPTED` must be updated to use `is_accepted()` or `result__in=[ACCEPTED, AST_CHECK_FAILED]`.

### 6.1 `judge/dispatcher.py` — Statistics Methods (10 changes)

| Line | Current Code | Change |
|---|---|---|
| 106 | `resp_data[i]["result"] == JudgeStatus.ACCEPTED` | **NO CHANGE** — individual test case results from judge server |
| 205 | `self.submission.result = JudgeStatus.ACCEPTED` | **NO CHANGE** — initial result assignment, before AST check |
| 254 | `self.last_result != JudgeStatus.ACCEPTED and self.submission.result == JudgeStatus.ACCEPTED` | → `not is_accepted(self.last_result) and is_accepted(self.submission.result)` |
| 264 | `acm_problems_status[problem_id]["status"] != JudgeStatus.ACCEPTED` | → `not is_accepted(...)` |
| 266 | `self.submission.result == JudgeStatus.ACCEPTED` | → `is_accepted(...)` |
| 274 | `oi_problems_status[problem_id]["status"] != JudgeStatus.ACCEPTED` | → `not is_accepted(...)` |
| 280 | `self.submission.result == JudgeStatus.ACCEPTED` | → `is_accepted(...)` |
| 292 | `self.submission.result == JudgeStatus.ACCEPTED` | → `is_accepted(...)` |
| 305-310 | `acm_problems_status[problem_id] = {"status": self.submission.result, ...}` | → store `JudgeStatus.ACCEPTED` as status when `is_accepted()` |
| 308 | `acm_problems_status[problem_id]["status"] != JudgeStatus.ACCEPTED` | → `not is_accepted(...)` |
| 310 | `self.submission.result == JudgeStatus.ACCEPTED` | → `is_accepted(...)` |
| 320-331 | OI mode — same pattern as ACM | Same changes |

### 6.2 `judge/dispatcher.py` — `update_contest_problem_status()` (5 changes)

| Line | Current Code | Change |
|---|---|---|
| 344 | `{"status": self.submission.result, ...}` | → store `JudgeStatus.ACCEPTED` when `is_accepted()` |
| 345 | `contest_problems_status[problem_id]["status"] != JudgeStatus.ACCEPTED` | → `not is_accepted(...)` |
| 346 | `contest_problems_status[problem_id]["status"] = self.submission.result` | → store `JudgeStatus.ACCEPTED` when `is_accepted()` |
| 357,362 | OI mode — same pattern | Same changes |
| 371 | `self.submission.result == JudgeStatus.ACCEPTED` | → `is_accepted(...)` |

### 6.3 `judge/dispatcher.py` — `_update_acm_contest_rank()` (2 changes)

| Line | Current Code | Change |
|---|---|---|
| 409 | `self.submission.result == JudgeStatus.ACCEPTED` | → `is_accepted(...)` |
| 424 | `self.submission.result == JudgeStatus.ACCEPTED` | → `is_accepted(...)` |

Lines 417/433 (`!= COMPILE_ERROR` → increment `error_number`) are automatically correct once 409/424 are fixed. Without this fix, AST_CHECK_FAILED would fall into the `elif` branch and incorrectly add 20 minutes penalty.

### 6.4 `judge/dispatcher.py` — `_update_oi_contest_rank()`

**NO CHANGE needed.** OI rank uses `statistic_info["score"]` set by `_compute_statistic_info()` before AST check. AST check does not modify the score.

### 6.5 Other Backend Files (11 changes)

| File | Line(s) | Change |
|---|---|---|
| `account/views/oj.py` | 468, 483 | `result=JudgeStatus.ACCEPTED` → `result__in=[ACCEPTED, AST_CHECK_FAILED]` |
| `comment/views/oj.py` | 31 | Same |
| `contest/views/admin.py` | 220 | Same |
| `problem/views/oj.py` | 199, 210 | Same |
| `problem/views/oj.py` | 241 | **NO CHANGE** — profile stores ACCEPTED(0) |
| `problem/views/admin.py` | 530, 596 | `Count("id", filter=Q(result=JudgeStatus.ACCEPTED))` → `Q(result__in=[...])` |
| `problem/views/admin.py` | 444, 472 | **NO CHANGE** — full resets |
| `problemset/views/oj.py` | 190 | `result != JudgeStatus.ACCEPTED` → `not is_accepted(result)` |
| `problemset/management/commands/fix_problemset_progress.py` | 41 | `result=JudgeStatus.ACCEPTED` → `result__in=[...]` |
| `class_pk/views/oj.py` | 280, 291 | Same |
| `submission/views/admin.py` | 81, 94 | `Count(...filter=Q(result=JudgeStatus.ACCEPTED))` → `Q(result__in=[...])` |

**Total: 28 backend changes + 3 no-change confirmations = 31 audit points**

---

## 7. Frontend Changes

### 7.1 Status Code Registration

`ojnext/src/utils/constants.ts`:

```typescript
// SubmissionStatus enum
ast_check_failed = 10,

// JUDGE_STATUS object
"10": {
  name: "代码检查未通过",
  type: "warning",
},
```

`ojnext/src/utils/types.ts` line 68 — add `| 10` to `SUBMISSION_RESULT` type.

### 7.2 SubmissionResult.vue

| Line | What | Change |
|---|---|---|
| 37-38 | Shows `err_info` for `compile_error`, `runtime_error` | Add `ast_check_failed` |
| 110-112 | Shows test case details | Add `ast_check_failed` |
| 119 | `item.result === 0` in test case filter | No change — individual test cases are result 0 |

### 7.3 SubmitCode.vue

| Line | What | Change |
|---|---|---|
| 152 | Confetti on AC | **NO CHANGE** — no celebration for AST fail |
| 162 | `if (result !== SubmissionStatus.accepted) return` — sets `my_status = 0` | **Add `ast_check_failed`**: `if (result !== SubmissionStatus.accepted && result !== SubmissionStatus.ast_check_failed) return` |

Without the line 162 fix, the problem stays "unsolved" in the sidebar until page refresh.

### 7.4 Other Frontend (no changes needed)

| Component | Why |
|---|---|
| `oj/api.ts` (my_status check) | Backend stores 0 in profile, not 10 |
| `ProblemComment.vue` (my_status check) | Same reason |
| `ProblemInfo.vue` (statistic chart) | Covered by constants.ts — chart auto-shows new status |
| `useSubmissionMonitor.ts` (WebSocket) | Only treats result 9 as "still processing" |

### 7.5 Admin UI

In the problem edit page, add a collapsible "代码规则检查" section:

- **Language tabs**: Only show tabs for languages enabled on this problem
- **Rule list per language**: Each rule is a row with:
  - Engine dropdown (grouped: 节点检查 / 函数调用 / 运算符 / 结构检查 / 导入…)
  - Target dropdown/input (context-dependent on engine type)
  - Optional parameters: `min`, `max`, `value` (shown when engine uses them)
  - Message input (with auto-generated default)
  - Delete button
- **Add rule button** per language tab
- Collapsed by default (most problems won't have AST rules)

---

## 8. Contest Behavior

Contests and regular problems use the **same AST check logic**. No `contest_id` guard — if the contest problem has `ast_rules`, AST check runs.

- AST_CHECK_FAILED counts as AC for contest ranking (ACM `accepted_number`, penalty time)
- When adding a bank problem to a contest, `ast_rules` is copied. Contest creator can edit/clear rules on the contest copy.
- `update_contest_problem_status()` and `_update_acm_contest_rank()` use `is_accepted()`.
- All contests currently use ACM mode only. OI code paths are updated for correctness but lower risk.

---

## 9. Legacy Data & Migration

### Migration

One Django migration (additive, no data migration):
1. Add `ast_rules` JSONField (null=True) to Problem model
2. Add `AST_CHECK_FAILED = 10` to JudgeStatus

Existing problems get `ast_rules=null` (no AST checking).

### Legacy Data Policy

- Existing submissions are **not retroactively checked**. Only new submissions after rules are added.
- `accepted_number` and `statistic_info` keep current values. `statistic_info` will naturally accumulate `"10"` entries as new AST_CHECK_FAILED submissions come in.
- Phase 2: optional "AST re-check" admin action — not in Phase 1.

---

## 10. Dependencies

```
tree-sitter
tree-sitter-python
tree-sitter-c
tree-sitter-cpp
tree-sitter-java
tree-sitter-go
tree-sitter-javascript
```

Pure Python wheels with pre-compiled grammars, no system dependencies.

---

## 11. Phased Delivery

### Phase 1 (MVP)

- Rule engine framework + `check_ast()` entry point
- **Python3 mapping** (most complete, matches full rule catalog)
- **C mapping** (second priority)
- Engines: `must_exist_node`, `must_not_exist_node`, `count_node`, `must_call_function`, `must_not_call_function`, `count_function_call`, `must_call_method`, `must_not_call_method`, `must_use_operator`
- JudgeDispatcher integration (AST check + all 28 statistics changes)
- Frontend: status code, result display, admin UI
- Migration

### Phase 2

- Engines: `must_use_keyword_arg`, `must_import`/`must_not_import`, `must_use_variable_name`/`must_not_use_variable_name`
- Structural engines: `nested_for`, `chained_comparison`, `swap_assignment`, `chain_assignment`, `must_use_recursion`, `no_recursion`
- C++ mapping

### Phase 3

- Java, Go, JavaScript mappings
- String literal content checks (format specifiers)
- Optional "AST re-check" admin action for existing AC submissions
