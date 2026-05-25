# AST Checker Design Spec

## Overview

Add tree-sitter-based AST checking to the Online Judge submission flow. Teachers can configure per-problem, per-language rules that validate student code structure before judging (e.g., "must use while loop", "cannot use for loop", "must call print()").

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
      → **AST check** ← NEW
        → fail: result=AST_CHECK_FAILED, write err_info, push WebSocket, return
        → pass: continue
      → choose judge server
      → send to judge server
      → process result
```

AST check runs inside the Dramatiq task, after template application and before judge server dispatch. This is consistent with how `COMPILE_ERROR` is handled — the submission exists in history, the result is pushed via WebSocket.

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
    AST_CHECK_FAILED = 9, "AST Check Failed"   # NEW
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

```python
# In JudgeDispatcher.judge(), after template application:
def judge(self):
    language = self.submission.language
    sub_config = list(filter(...))[0]

    if language in self.problem.template:
        template = parse_problem_template(self.problem.template[language])
        code = f"{template['prepend']}\n{self.submission.code}\n{template['append']}"
    else:
        code = self.submission.code

    # --- AST CHECK (NEW) ---
    ast_rules = self.problem.ast_rules
    if ast_rules and language in ast_rules:
        from ast_checker.checker import check_ast
        passed, errors = check_ast(self.submission.code, language, ast_rules[language])
        if not passed:
            self.submission.result = JudgeStatus.AST_CHECK_FAILED
            self.submission.statistic_info["err_info"] = "\n".join(errors)
            self.submission.statistic_info["score"] = 0
            self.submission.save(update_fields=["result", "info", "statistic_info"])
            try:
                push_submission_update(
                    submission_id=str(self.submission.id),
                    user_id=self.submission.user_id,
                    data={
                        "type": "submission_update",
                        "submission_id": str(self.submission.id),
                        "result": JudgeStatus.AST_CHECK_FAILED,
                        "status": "finished",
                    }
                )
            except Exception as e:
                logger.error(f"Failed to push submission update: {str(e)}")
            return
    # --- END AST CHECK ---

    # ... continue with judge server dispatch
```

Note: AST check runs on `self.submission.code` (raw student code), not the template-wrapped `code`, because the template prepend/append is not student-written.

---

## Frontend Changes

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

### Status Display

- Add `AST_CHECK_FAILED = 9` to `ojnext/src/utils/constants.ts`
- Assign a distinct color (suggest orange, between COMPILE_ERROR red and PENDING grey)
- Label: "AST Check Failed" / "代码结构检查未通过"
- When viewing a submission with this status, display `statistic_info.err_info` as the error detail (same rendering as COMPILE_ERROR)

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
2. Add `AST_CHECK_FAILED = 9` to JudgeStatus

Both are additive, no data migration needed. Existing problems get `ast_rules=null` (no AST checking).

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
