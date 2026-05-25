# AST Checker Design Spec

## Overview

Add tree-sitter-based AST checking to the Online Judge submission flow. Teachers can configure per-problem, per-language rules that validate student code structure (e.g., "must use while loop", "cannot use for loop", "must call print()").

**Critical invariant**: AST check runs AFTER normal judging. Only submissions that would be AC are checked. If AST fails, the displayed result is `AST_CHECK_FAILED`, but **all statistics treat it as AC** (problem accepted count, user profile solved status, contest ranking). The student solved the problem correctly — they just didn't use the required syntax.

## Goals

- Enforce coding constraints for pedagogical purposes (beginner programming courses)
- Support all 6 languages: Python3, C, C++, Java, Golang, JavaScript
- Predefined rule library with parameterized engines (no raw tree-sitter queries for admins)
- Full admin UI for configuring rules per problem per language
- New `AST_CHECK_FAILED` judge status with clear error messages

## Non-Goals

- Output-aware checks ("禁止直接输出完整目标答案") — requires expected output, not AST
- String literal content matching (`.2f`, `03d` format specifiers) — deferred to a later phase
- Custom tree-sitter query support for admins

---

## Architecture

### Submission Flow (modified)

```
SubmissionAPI.post()
  → create Submission(PENDING)
  → judge_task.send()
    → JudgeDispatcher.judge()
      → apply code template
      → choose judge server
      → send to judge server
      → process judge result
      → if result == AC and ast_rules exist for this language:
          → **AST check** ← NEW
          → if AST fails:
              → result = AST_CHECK_FAILED (display only)
              → write err_info with rule violation details
          → (statistics still treat as AC)
      → update_problem_status / update_contest_* (treats AST_CHECK_FAILED as AC)
      → push WebSocket with final result
```

AST check runs AFTER the judge server returns a result, and ONLY when the result is AC. The key insight: a student who produces correct output has solved the problem — they just need to adjust their approach. Statistics (accepted count, user profile, contest rank) always reflect the AC.

### Data Model

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

Key design: `target` uses **language-agnostic logical names** (e.g., `for_loop`, `while_loop`, `print`). Each engine maps these to language-specific tree-sitter node types internally.

When `ast_rules` is `null` or the current language has no rules, AST checking is skipped entirely.

**JudgeStatus** — new status code:

```python
class JudgeStatus(models.IntegerChoices):
    COMPILE_ERROR = -2, "Compile Error"
    WRONG_ANSWER = -1, "Wrong Answer"
    ACCEPTED = 0, "Accepted"
    CPU_TIME_LIMIT_EXCEEDED = 1, "CPU Time Limit Exceeded"
    REAL_TIME_LIMIT_EXCEEDED = 2, "Real Time Limit Exceeded"
    MEMORY_LIMIT_EXCEEDED = 3, "Memory Limit Exceeded"
    RUNTIME_ERROR = 4, "Runtime Error"
    SYSTEM_ERROR = 5, "System Error"
    PENDING = 6, "Pending"
    JUDGING = 7, "Judging"
    PARTIALLY_ACCEPTED = 8, "Partially Accepted"
    AST_CHECK_FAILED = 10, "AST Check Failed"   # NEW (9 is taken by frontend's "submitting" transient state)
```

Frontend `constants.ts` must be updated with the new status code, label, and color.

---

## Rule Engine Architecture

### Directory Structure

```
OnlineJudge/ast_checker/
├── __init__.py
├── checker.py              # Entry point: check(code, language, rules) → (ok, errors)
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
        """
        Returns a list of error messages (empty = pass).
        - tree: tree-sitter parsed tree
        - rule: the rule dict (engine, target, message, min, max, value, etc.)
        - language: language name string
        - mapping: language-specific node type mapping dict
        """
        raise NotImplementedError
```

### Engine Catalog

| Engine Name | Parameters | Description |
|---|---|---|
| `must_exist_node` | `target` | Node type must appear at least once |
| `must_not_exist_node` | `target` | Node type must not appear |
| `count_node` | `target`, `min?`, `max?` | Node type count must be within [min, max] |
| `must_call_function` | `target` | Must call a specific function (e.g., `print`, `input`) |
| `must_not_call_function` | `target` | Must not call a specific function |
| `count_function_call` | `target`, `min?`, `max?` | Function call count within range |
| `must_call_method` | `target` | Must call a method (e.g., `.append()`, `.split()`) |
| `must_not_call_method` | `target` | Must not call a method |
| `must_use_operator` | `target`, `category?` | Must use a specific operator. Category auto-inferred from target: arithmetic (`+`,`-`,`*`,`/`,`//`,`%`,`**`) → search in binary expressions; augmented (`+=`,`-=`) → search in augmented assignments; comparison (`==`,`!=`,`>`,`>=`,`<`,`<=`) → search in comparisons; logical (`and`,`or`,`not`) → search in boolean/unary expressions; bitwise (`&`,`\|`) → search in binary expressions |
| `must_use_keyword_arg` | `target` (function), `arg_name`, `value?` | Must use keyword arg in a call |
| `must_import` | `target` | Must import a specific module |
| `must_not_import` | `target` | Must not import a specific module |
| `must_use_variable_name` | `target` | Must assign to a variable with this name |
| `must_not_use_variable_name` | `target` | Must not assign to a variable with this name |
| `nested_for` | — | Must have a for loop nested inside another for loop |
| `chained_comparison` | — | Must use chained comparison (e.g., `a < b < c`) |
| `swap_assignment` | — | Must use swap assignment (e.g., `a, b = b, a`) |
| `chain_assignment` | — | Must use chain assignment (e.g., `a = b = 1`) |
| `must_use_recursion` | — | Must have a function that calls itself |
| `no_recursion` | — | No function may call itself |

### Language Mapping

Each mapping file exports a dict translating logical names to tree-sitter node types:

```python
# mappings/python.py
PYTHON_MAPPING = {
    # Node types
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

    # Operators
    "+": "+",
    "-": "-",
    "*": "*",
    "/": "/",
    "//": "//",
    "%": "%",
    "**": "**",
    "+=": "+=",
    "-=": "-=",
    "==": "==",
    "!=": "!=",
    ">": ">",
    ">=": ">=",
    "<": "<",
    "<=": "<=",
    "and": "and",
    "or": "or",
    "not": "not",
    "&": "&",
    "|": "|",
}
```

```python
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

### Entry Point

```python
# checker.py
def check_ast(code: str, language: str, rules: list[dict]) -> tuple[bool, list[str]]:
    """
    Parse code with tree-sitter, run all rules, return (passed, error_messages).
    If rules is empty, returns (True, []).
    If tree-sitter fails to parse (syntax error), returns (True, []) — skip AST
    check and let the compiler report the error downstream.
    """
```

### Known Limitations

- **Method call detection is name-based only**: `must_call_method("append")` matches any `.append()` call regardless of object type. tree-sitter provides no type information. Acceptable for teaching scenarios.
- **Structural rules are language-specific**: `swap_assignment`, `chained_comparison`, `chain_assignment` only apply to Python. The engine should return (pass) for unsupported languages rather than erroring.

### Integration in JudgeDispatcher

The AST check happens AFTER the judge server returns a result, and ONLY when the result is AC.

```python
# In JudgeDispatcher.judge(), after processing the judge server response:
# (after _compute_statistic_info and result determination)

    # --- AST CHECK (NEW) ---
    # Only check AST when the submission would be AC
    if self.submission.result == JudgeStatus.ACCEPTED:
        ast_rules = self.problem.ast_rules
        if ast_rules and language in ast_rules:
            from ast_checker.checker import check_ast
            passed, errors = check_ast(self.submission.code, language, ast_rules[language])
            if not passed:
                self.submission.result = JudgeStatus.AST_CHECK_FAILED
                self.submission.statistic_info["err_info"] = "\n".join(errors)
    # --- END AST CHECK ---

    self.submission.save(update_fields=["result", "info", "statistic_info"])
    # ... push WebSocket, update statistics
```

Note: AST check runs on `self.submission.code` (raw student code), not the template-wrapped `code`, because the template prepend/append is not student-written.

### Statistics: AST_CHECK_FAILED = AC

All statistics methods must treat `AST_CHECK_FAILED` the same as `ACCEPTED`.

### Helper

```python
# submission/models.py (add to JudgeStatus or as module-level function)
def is_accepted(result):
    return result in (JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED)
```

### Backend Impact Checklist (every location that checks JudgeStatus.ACCEPTED)

**`judge/dispatcher.py` — statistics methods (10 changes):**

| Line | Current Code | Change |
|---|---|---|
| 106 | `resp_data[i]["result"] == JudgeStatus.ACCEPTED` | **NO CHANGE** — individual test case results from judge server, unrelated to AST |
| 205 | `self.submission.result = JudgeStatus.ACCEPTED` | **NO CHANGE** — this is where result is first set; AST check happens after this |
| 254 | `self.last_result != JudgeStatus.ACCEPTED and self.submission.result == JudgeStatus.ACCEPTED` | → `not is_accepted(self.last_result) and is_accepted(self.submission.result)` |
| 264 | `acm_problems_status[problem_id]["status"] != JudgeStatus.ACCEPTED` | → `not is_accepted(...)` |
| 266 | `self.submission.result == JudgeStatus.ACCEPTED` | → `is_accepted(...)` |
| 274 | `oi_problems_status[problem_id]["status"] != JudgeStatus.ACCEPTED` | → `not is_accepted(...)` |
| 280 | `self.submission.result == JudgeStatus.ACCEPTED` | → `is_accepted(...)` |
| 292 | `self.submission.result == JudgeStatus.ACCEPTED` | → `is_accepted(...)` |
| 305-310 | `acm_problems_status[problem_id] = {"status": self.submission.result, ...}` | → store `JudgeStatus.ACCEPTED` as status (not raw result) |
| 308 | `acm_problems_status[problem_id]["status"] != JudgeStatus.ACCEPTED` | → `not is_accepted(...)` |
| 310 | `self.submission.result == JudgeStatus.ACCEPTED` | → `is_accepted(...)` |
| 320-331 | OI mode — same pattern as ACM | Same changes |

**Critical**: When storing status in `acm_problems_status` / `oi_problems_status`, always store `JudgeStatus.ACCEPTED` (0), not `AST_CHECK_FAILED` (10). This ensures `my_status` shows as AC in the problem list. The raw `AST_CHECK_FAILED` result lives only on the Submission record itself.

**`judge/dispatcher.py` — contest statistics:**
Same changes in `update_contest_problem_status()` — treat AST_CHECK_FAILED as AC for contest accepted tracking and rank.

**`account/views/oj.py` — query filters (2 changes):**

| Line | Current Code | Change |
|---|---|---|
| 468 | `result=JudgeStatus.ACCEPTED` | → `result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED]` |
| 483 | `result=JudgeStatus.ACCEPTED` | → `result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED]` |

**`comment/views/oj.py` (1 change):**

| Line | Current Code | Change |
|---|---|---|
| 31 | `result=JudgeStatus.ACCEPTED` | → `result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED]` |

**`contest/views/admin.py` (1 change):**

| Line | Current Code | Change |
|---|---|---|
| 220 | `result=JudgeStatus.ACCEPTED` | → `result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED]` |

**`problem/views/oj.py` (2 changes):**

| Line | Current Code | Change |
|---|---|---|
| 199 | `result=JudgeStatus.ACCEPTED` | → `result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED]` |
| 210 | `result=JudgeStatus.ACCEPTED` | → `result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED]` |
| 241 | `v.get("status") == JudgeStatus.ACCEPTED` | **NO CHANGE** — profile stores ACCEPTED(0), not raw result |

**`problem/views/admin.py` (2 changes + no-change):**

| Line | Current Code | Change |
|---|---|---|
| 530 | `accepted=Count("id", filter=Q(result=JudgeStatus.ACCEPTED))` | → `Q(result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED])` |
| 596 | Same pattern | Same change |
| 444,472 | `problem.accepted_number = 0` | **NO CHANGE** — full resets |

**`problemset/views/oj.py` (1 change):**

| Line | Current Code | Change |
|---|---|---|
| 190 | `submission.result != JudgeStatus.ACCEPTED` | → `not is_accepted(submission.result)` |

**`problemset/management/commands/fix_problemset_progress.py` (1 change):**

| Line | Current Code | Change |
|---|---|---|
| 41 | `result=JudgeStatus.ACCEPTED` | → `result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED]` |

**`class_pk/views/oj.py` (2 changes):**

| Line | Current Code | Change |
|---|---|---|
| 280 | `submissions.filter(result=JudgeStatus.ACCEPTED)` | → `result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED]` |
| 291 | `submissions.filter(user_id=user_id, result=JudgeStatus.ACCEPTED)` | Same |

**`submission/views/admin.py` (2 changes):**

| Line | Current Code | Change |
|---|---|---|
| 81 | `accepted_count=Count("id", filter=Q(result=JudgeStatus.ACCEPTED))` | → `Q(result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED])` |
| 94 | Same pattern | Same change |

### statistic_info (per-result counts)

Use the **actual result code** as the key — `{"0": 5, "10": 3, "-1": 20}`. This means:
- `accepted_number` = AC + AST_CHECK_FAILED combined (for overall acceptance rate)
- `statistic_info` retains the breakdown: 5 pure AC, 3 AST check failed, 20 WA
- Frontend statistics display can show AST_CHECK_FAILED as a separate category, giving teachers visibility into how many students solved the problem but didn't meet syntax requirements

---

## Frontend Changes

### Status Code Registration

**Conflict**: Frontend `SubmissionStatus.submitting = 9` is a frontend-only transient state. AST_CHECK_FAILED uses `10` to avoid collision.

Changes to `ojnext/src/utils/constants.ts`:

```typescript
// SubmissionStatus enum — add:
ast_check_failed = 10,

// JUDGE_STATUS object — add:
"10": {
  name: "代码检查未通过",
  type: "warning",
},
```

Changes to `ojnext/src/utils/types.ts`:
- Update `SUBMISSION_RESULT` type to include `"10"`

### Submission Result Display

`SubmissionResult.vue` checks specific statuses to decide what to show:
- Line 37-38: Shows `err_info` for `compile_error` and `runtime_error` → **add `ast_check_failed`** so AST error messages are displayed
- Line 110-112: Shows test case details for `accepted`, `compile_error`, `runtime_error` → **add `ast_check_failed`** (submission was judged, test cases exist)
- Line 119: `data.some((item) => item.result === 0)` filters test case data → **also include result === 10** or leave as-is since AST_CHECK_FAILED submissions did pass all test cases (result 0 in individual test case items)

### SubmitCode.vue — AC celebration and my_status

- Line 152: `result !== SubmissionStatus.accepted` → controls confetti. **Do NOT add `ast_check_failed`** — no celebration when AST fails.
- Line 162-165: `if (result !== SubmissionStatus.accepted) return` → skips setting `problem.value!.my_status = 0`. **NEEDS CHANGE**: add `ast_check_failed` so that `my_status` is immediately set to 0 in the UI (without waiting for page refresh). Otherwise the problem stays "unsolved" in the sidebar until the user refreshes.

```typescript
// Line 162: change to
if (result !== SubmissionStatus.accepted && result !== SubmissionStatus.ast_check_failed) return
```

### Problem List "My Status"

`oj/api.ts` line 26-28 checks `my_status === 0` to show the green AC icon. Since backend stores `ACCEPTED` (0) in the user profile status (not the raw AST_CHECK_FAILED result), `my_status` will be `0`. **No change needed** — the problem list will correctly show the green AC icon.

### ProblemComment.vue

Line 5: `v-if="problem?.my_status !== 0"` — hides comment if not AC. Since `my_status` stores 0, **NO CHANGE needed**.

### ProblemInfo.vue — statistic_info chart

Line 33-38: Iterates `statistic_info` keys and maps via `JUDGE_STATUS[i]["name"]`. Since `statistic_info` will contain key `"10"` for AST_CHECK_FAILED, the JUDGE_STATUS entry must exist. **Covered by constants.ts change** — the chart will automatically show "代码检查未通过" as a separate slice.

### types.ts

Line 68: `export type SUBMISSION_RESULT = -2 | -1 | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9` → **add `| 10`**

### WebSocket Monitor

`useSubmissionMonitor.ts` line 92-94 treats result `9` as "still processing". Since AST_CHECK_FAILED is `10`, **no change needed** — when result `10` arrives via WebSocket, the monitor will correctly stop polling and show the final result.

### Admin UI (ojnext)

In the problem edit page, add a collapsible "代码规则检查" section:

- **Language tabs**: Only show tabs for languages selected in this problem's `languages` field
- **Rule list per language**: Each rule is a row with:
  - Engine dropdown (grouped by category: 节点检查 / 函数调用 / 运算符 / 结构检查 / 导入…)
  - Target dropdown/input (context-dependent: node types for node engines, function names for call engines, operators for operator engine)
  - Optional parameters: `min`, `max`, `value` fields (shown only when the selected engine uses them)
  - Message input (custom error message, with auto-generated default)
  - Delete button
- **Add rule button** per language tab
- Section is collapsed by default (most problems won't have AST rules)

---

## Dependencies

Backend (add to pyproject.toml / requirements):
- `tree-sitter` (Python bindings)
- `tree-sitter-python`
- `tree-sitter-c`
- `tree-sitter-cpp`
- `tree-sitter-java`
- `tree-sitter-go`
- `tree-sitter-javascript`

These are pure Python wheels with pre-compiled grammars, no system dependencies needed.

---

## Migration

One Django migration:
1. Add `ast_rules` JSONField (null=True) to Problem model
2. Add `AST_CHECK_FAILED = 10` to JudgeStatus

Both are additive, no data migration needed. Existing problems get `ast_rules=null` (no AST checking).

### Legacy Data Policy

- **Existing submissions are not retroactively checked.** When a teacher adds AST rules to an existing problem, only new submissions are AST-checked. Prior AC submissions remain AC.
- **No data migration required.** `accepted_number` and `statistic_info` keep their current values. The `statistic_info` will naturally accumulate `"10"` entries as new AST_CHECK_FAILED submissions come in.
- **Phase 2: optional "AST re-check"** — an admin action to re-run AST rules on all existing AC submissions for a given problem. Not in Phase 1.

---

## Phased Delivery

> Note: Most problems use Python3 and C. Prioritize these two languages.

### Phase 1 (MVP)
- Rule engine framework + checker entry point
- **Python3 mapping** (most complete, matches the full rule catalog)
- **C mapping** (second priority, covers the most-used language pair)
- Engines: `must_exist_node`, `must_not_exist_node`, `count_node`, `must_call_function`, `must_not_call_function`, `count_function_call`, `must_call_method`, `must_not_call_method`, `must_use_operator`
- JudgeDispatcher integration
- Frontend: status code + admin UI
- Migration

### Phase 2
- Remaining engines: `must_use_keyword_arg`, `must_import`/`must_not_import`, `must_use_variable_name`/`must_not_use_variable_name`
- Structural engines: `nested_for`, `chained_comparison` (Python only), `swap_assignment` (Python only), `chain_assignment` (Python only), `must_use_recursion`, `no_recursion`
- C++ mapping (shares most structure with C)

### Phase 3
- Java, Go, JavaScript mappings
- String literal content checks (format specifiers)
- Additional structural rules as needed
