# AST Checker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add tree-sitter-based AST checking to enforce code structure rules on student submissions (Phase 1 MVP: Python3 + C, 9 engine types).

**Architecture:** New `ast_checker/` module with engine-based rule checking, integrated into `JudgeDispatcher.judge()` post-judge. AST_CHECK_FAILED (status 10) is treated as AC for all statistics. Language mappings translate logical target names to tree-sitter node types.

**Tech Stack:** tree-sitter (Python bindings), tree-sitter-python, tree-sitter-c, Django 6, Vue 3 + Naive UI

**Design spec:** `docs/specs/2026-05-25-ast-checker-design.md`

**Testing policy:** Do not write tests (per project CLAUDE.md).

---

### Task 1: Add tree-sitter dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Install tree-sitter packages**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
uv add tree-sitter tree-sitter-python tree-sitter-c
```

- [ ] **Step 2: Verify installation**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
uv run python -c "from tree_sitter import Language, Parser; import tree_sitter_python; import tree_sitter_c; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
git add pyproject.toml uv.lock
git commit -m "deps: add tree-sitter with Python and C grammars"
```

---

### Task 2: Backend model changes

**Files:**
- Modify: `submission/models.py`
- Modify: `problem/models.py`
- Modify: `problem/serializers.py`
- Create migration via `makemigrations`

- [ ] **Step 1: Add AST_CHECK_FAILED status and is_accepted helper to `submission/models.py`**

Add `AST_CHECK_FAILED = 10` to the `JudgeStatus` enum and add `is_accepted()` function after the class:

```python
# In JudgeStatus class, after PARTIALLY_ACCEPTED = 8:
    AST_CHECK_FAILED = 10, "AST Check Failed"
```

```python
# After the JudgeStatus class, before the Submission class:
def is_accepted(result):
    return result in (JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED)
```

- [ ] **Step 2: Add ast_rules field to Problem model in `problem/models.py`**

Add after the `show_flowchart` field (line 84):

```python
    # AST 代码结构检查规则
    ast_rules = models.JSONField(null=True, blank=True, default=None)
```

- [ ] **Step 3: Update serializers in `problem/serializers.py`**

Add `ast_rules` to `CreateOrEditProblemSerializer` (after the `flowchart_hint` field, around line 87):

```python
    # AST 规则
    ast_rules = serializers.JSONField(required=False, allow_null=True, default=None)
```

Exclude `ast_rules` from student-facing serializers. In `ProblemSerializer.Meta.exclude` (around line 143), add `"ast_rules"`:

```python
        exclude = (
            "test_case_score",
            "test_case_id",
            "visible",
            "is_public",
            "answers",
            "ast_rules",
        )
```

In `ProblemSafeSerializer.Meta.exclude` (around line 189), add `"ast_rules"`:

```python
        exclude = (
            "test_case_score",
            "test_case_id",
            "visible",
            "is_public",
            "difficulty",
            "submission_number",
            "accepted_number",
            "statistic_info",
            "answers",
            "ast_rules",
        )
```

`ProblemAdminSerializer` uses `fields = "__all__"` — no change needed, `ast_rules` is included automatically.

- [ ] **Step 4: Create and apply migration**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
python manage.py makemigrations problem submission
python manage.py migrate
```

- [ ] **Step 5: Commit**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
git add submission/models.py problem/models.py problem/serializers.py problem/migrations/ submission/migrations/
git commit -m "feat: add AST_CHECK_FAILED status, is_accepted helper, ast_rules field"
```

---

### Task 3: AST checker — language mappings

**Files:**
- Create: `ast_checker/__init__.py`
- Create: `ast_checker/mappings/__init__.py`
- Create: `ast_checker/mappings/python.py`
- Create: `ast_checker/mappings/c.py`

- [ ] **Step 1: Create `ast_checker/__init__.py`**

```python
```

(Empty file — package marker only.)

- [ ] **Step 2: Create `ast_checker/mappings/python.py`**

```python
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
    "+": "+",
    "-": "-",
    "*": "*",
    "/": "/",
    "//": "//",
    "%": "%",
    "**": "**",
    "+=": "+=",
    "-=": "-=",
    "*=": "*=",
    "/=": "/=",
    "%=": "%=",
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

- [ ] **Step 3: Create `ast_checker/mappings/c.py`**

```python
C_MAPPING = {
    "for_loop": "for_statement",
    "while_loop": "while_statement",
    "do_while": "do_statement",
    "if_statement": "if_statement",
    "else_clause": "else_clause",
    "break": "break_statement",
    "continue": "continue_statement",
    "function_definition": "function_definition",
    "return": "return_statement",
    "switch_statement": "switch_statement",
    "case_statement": "case_statement",
    "assignment": "assignment_expression",
    "struct": "struct_specifier",
    "include": "preproc_include",
    "+": "+",
    "-": "-",
    "*": "*",
    "/": "/",
    "%": "%",
    "+=": "+=",
    "-=": "-=",
    "*=": "*=",
    "/=": "/=",
    "%=": "%=",
    "==": "==",
    "!=": "!=",
    ">": ">",
    ">=": ">=",
    "<": "<",
    "<=": "<=",
    "and": "&&",
    "or": "||",
    "not": "!",
    "&": "&",
    "|": "|",
    "++": "++",
    "--": "--",
}
```

- [ ] **Step 4: Create `ast_checker/mappings/__init__.py`**

```python
from tree_sitter import Language

from .c import C_MAPPING
from .python import PYTHON_MAPPING

_MAPPINGS = {
    "Python3": PYTHON_MAPPING,
    "C": C_MAPPING,
}

_LANGUAGES: dict[str, Language] = {}


def _init_languages():
    try:
        import tree_sitter_python as tspython

        _LANGUAGES["Python3"] = Language(tspython.language())
    except ImportError:
        pass
    try:
        import tree_sitter_c as tsc

        _LANGUAGES["C"] = Language(tsc.language())
    except ImportError:
        pass


_init_languages()


def get_mapping(language: str) -> dict:
    return _MAPPINGS.get(language, {})


def get_language(language: str) -> Language | None:
    return _LANGUAGES.get(language)
```

- [ ] **Step 5: Verify mappings load**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
uv run python -c "from ast_checker.mappings import get_mapping, get_language; print(get_language('Python3')); print(len(get_mapping('Python3')))"
```

Expected: a Language object and a number (e.g., `Language(...)` and `42`).

- [ ] **Step 6: Commit**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
git add ast_checker/
git commit -m "feat: add ast_checker mappings for Python3 and C"
```

---

### Task 4: AST checker — engine framework and Phase 1 engines

**Files:**
- Create: `ast_checker/engines/__init__.py`
- Create: `ast_checker/engines/base.py`
- Create: `ast_checker/engines/node_exists.py`
- Create: `ast_checker/engines/node_count.py`
- Create: `ast_checker/engines/function_call.py`
- Create: `ast_checker/engines/method_call.py`
- Create: `ast_checker/engines/operator.py`

- [ ] **Step 1: Create `ast_checker/engines/base.py`**

```python
class BaseEngine:
    @staticmethod
    def collect_nodes(node, node_type):
        results = []
        if node.type == node_type:
            results.append(node)
        for child in node.children:
            results.extend(BaseEngine.collect_nodes(child, node_type))
        return results

    @staticmethod
    def has_node(node, node_type):
        if node.type == node_type:
            return True
        return any(BaseEngine.has_node(child, node_type) for child in node.children)

    def check(self, tree, rule, language, mapping) -> list[str]:
        raise NotImplementedError
```

- [ ] **Step 2: Create `ast_checker/engines/node_exists.py`**

```python
from .base import BaseEngine


class MustExistNodeEngine(BaseEngine):
    def check(self, tree, rule, language, mapping):
        target = rule["target"]
        node_type = mapping.get(target, target)
        if not self.has_node(tree.root_node, node_type):
            return [rule.get("message", f"必须使用 {target}")]
        return []


class MustNotExistNodeEngine(BaseEngine):
    def check(self, tree, rule, language, mapping):
        target = rule["target"]
        node_type = mapping.get(target, target)
        if self.has_node(tree.root_node, node_type):
            return [rule.get("message", f"不能使用 {target}")]
        return []
```

- [ ] **Step 3: Create `ast_checker/engines/node_count.py`**

```python
from .base import BaseEngine


class CountNodeEngine(BaseEngine):
    def check(self, tree, rule, language, mapping):
        target = rule["target"]
        node_type = mapping.get(target, target)
        nodes = self.collect_nodes(tree.root_node, node_type)
        count = len(nodes)
        min_count = rule.get("min")
        max_count = rule.get("max")
        if min_count is not None and count < min_count:
            return [rule.get("message", f"{target} 至少出现 {min_count} 次，当前 {count} 次")]
        if max_count is not None and count > max_count:
            return [rule.get("message", f"{target} 至多出现 {max_count} 次，当前 {count} 次")]
        return []
```

- [ ] **Step 4: Create `ast_checker/engines/function_call.py`**

```python
from .base import BaseEngine

CALL_NODE_TYPES = {
    "Python3": "call",
    "C": "call_expression",
}


class _FunctionCallBase(BaseEngine):
    def _find_function_calls(self, root, func_name, language):
        call_type = CALL_NODE_TYPES.get(language, "call")
        calls = self.collect_nodes(root, call_type)
        matches = []
        for call in calls:
            func_node = call.child_by_field_name("function")
            if func_node and func_node.type == "identifier" and func_node.text.decode() == func_name:
                matches.append(call)
        return matches


class MustCallFunctionEngine(_FunctionCallBase):
    def check(self, tree, rule, language, mapping):
        target = rule["target"]
        if not self._find_function_calls(tree.root_node, target, language):
            return [rule.get("message", f"必须调用 {target}()")]
        return []


class MustNotCallFunctionEngine(_FunctionCallBase):
    def check(self, tree, rule, language, mapping):
        target = rule["target"]
        if self._find_function_calls(tree.root_node, target, language):
            return [rule.get("message", f"不能调用 {target}()")]
        return []


class CountFunctionCallEngine(_FunctionCallBase):
    def check(self, tree, rule, language, mapping):
        target = rule["target"]
        count = len(self._find_function_calls(tree.root_node, target, language))
        min_count = rule.get("min")
        max_count = rule.get("max")
        if min_count is not None and count < min_count:
            return [rule.get("message", f"{target}() 至少调用 {min_count} 次，当前 {count} 次")]
        if max_count is not None and count > max_count:
            return [rule.get("message", f"{target}() 至多调用 {max_count} 次，当前 {count} 次")]
        return []
```

- [ ] **Step 5: Create `ast_checker/engines/method_call.py`**

```python
from .base import BaseEngine

CALL_NODE_TYPES = {
    "Python3": "call",
    "C": "call_expression",
}


class _MethodCallBase(BaseEngine):
    def _find_method_calls(self, root, method_name, language):
        if language == "C":
            return []
        call_type = CALL_NODE_TYPES.get(language, "call")
        calls = self.collect_nodes(root, call_type)
        matches = []
        for call in calls:
            func_node = call.child_by_field_name("function")
            if func_node and func_node.type == "attribute":
                attr_node = func_node.child_by_field_name("attribute")
                if attr_node and attr_node.text.decode() == method_name:
                    matches.append(call)
        return matches


class MustCallMethodEngine(_MethodCallBase):
    def check(self, tree, rule, language, mapping):
        target = rule["target"]
        if not self._find_method_calls(tree.root_node, target, language):
            return [rule.get("message", f"必须调用 .{target}()")]
        return []


class MustNotCallMethodEngine(_MethodCallBase):
    def check(self, tree, rule, language, mapping):
        target = rule["target"]
        if self._find_method_calls(tree.root_node, target, language):
            return [rule.get("message", f"不能调用 .{target}()")]
        return []
```

- [ ] **Step 6: Create `ast_checker/engines/operator.py`**

```python
from .base import BaseEngine


class MustUseOperatorEngine(BaseEngine):
    def check(self, tree, rule, language, mapping):
        target = rule["target"]
        mapped_op = mapping.get(target, target)
        if not self.has_node(tree.root_node, mapped_op):
            return [rule.get("message", f"必须使用 {target} 运算符")]
        return []
```

- [ ] **Step 7: Create `ast_checker/engines/__init__.py`**

```python
from .function_call import CountFunctionCallEngine, MustCallFunctionEngine, MustNotCallFunctionEngine
from .method_call import MustCallMethodEngine, MustNotCallMethodEngine
from .node_count import CountNodeEngine
from .node_exists import MustExistNodeEngine, MustNotExistNodeEngine
from .operator import MustUseOperatorEngine

ENGINES = {
    "must_exist_node": MustExistNodeEngine(),
    "must_not_exist_node": MustNotExistNodeEngine(),
    "count_node": CountNodeEngine(),
    "must_call_function": MustCallFunctionEngine(),
    "must_not_call_function": MustNotCallFunctionEngine(),
    "count_function_call": CountFunctionCallEngine(),
    "must_call_method": MustCallMethodEngine(),
    "must_not_call_method": MustNotCallMethodEngine(),
    "must_use_operator": MustUseOperatorEngine(),
}


def get_engine(name: str):
    return ENGINES.get(name)
```

- [ ] **Step 8: Commit**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
git add ast_checker/engines/
git commit -m "feat: add AST checker engine framework with 9 Phase 1 engines"
```

---

### Task 5: AST checker — entry point

**Files:**
- Create: `ast_checker/checker.py`

- [ ] **Step 1: Create `ast_checker/checker.py`**

```python
from tree_sitter import Parser

from .engines import get_engine
from .mappings import get_language, get_mapping


def check_ast(code: str, language: str, rules: list[dict]) -> tuple[bool, list[str]]:
    if not rules:
        return True, []

    ts_language = get_language(language)
    if ts_language is None:
        return True, []

    mapping = get_mapping(language)

    try:
        parser = Parser(ts_language)
        tree = parser.parse(code.encode("utf-8"))
    except Exception:
        return True, []

    errors = []
    for rule in rules:
        engine = get_engine(rule.get("engine", ""))
        if engine is None:
            continue
        rule_errors = engine.check(tree, rule, language, mapping)
        errors.extend(rule_errors)

    return len(errors) == 0, errors
```

- [ ] **Step 2: Smoke test**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
uv run python -c "
from ast_checker.checker import check_ast
# Should pass: code has a for loop
ok, errs = check_ast('for i in range(10): print(i)', 'Python3', [{'engine': 'must_exist_node', 'target': 'for_loop', 'message': '必须使用 for'}])
print('pass' if ok else 'fail', errs)
# Should fail: code has no while loop
ok, errs = check_ast('for i in range(10): print(i)', 'Python3', [{'engine': 'must_exist_node', 'target': 'while_loop', 'message': '必须使用 while'}])
print('pass' if ok else 'fail', errs)
"
```

Expected:
```
pass []
fail ['必须使用 while']
```

- [ ] **Step 3: Commit**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
git add ast_checker/checker.py
git commit -m "feat: add check_ast entry point"
```

---

### Task 6: JudgeDispatcher — AST check and statistics updates

**Files:**
- Modify: `judge/dispatcher.py`

This task modifies 5 methods in `judge/dispatcher.py`. Read the file first, then apply changes method by method.

**Critical invariant:** `is_accepted()` treats both `ACCEPTED` and `AST_CHECK_FAILED` as accepted. When storing status in profile dicts (`acm_problems_status`, `oi_problems_status`, `contest_problems_status`), always store `JudgeStatus.ACCEPTED` (0), never `AST_CHECK_FAILED` (10).

- [ ] **Step 1: Update imports in `judge/dispatcher.py`**

Change the import line:

```python
from submission.models import JudgeStatus, Submission
```

to:

```python
from submission.models import JudgeStatus, Submission, is_accepted
```

- [ ] **Step 2: Insert AST check in `judge()` method**

In the `judge()` method, find the block that determines the submission result (around lines 204-209):

```python
            if not error_test_case:
                self.submission.result = JudgeStatus.ACCEPTED
            elif self.problem.rule_type == ProblemRuleType.ACM or len(error_test_case) == len(resp["data"]):
                self.submission.result = error_test_case[0]["result"]
            else:
                self.submission.result = JudgeStatus.PARTIALLY_ACCEPTED
```

Insert AST check **after** this block and **before** `self.submission.save(...)` (line 210):

```python
            if self.submission.result == JudgeStatus.ACCEPTED:
                ast_rules = self.problem.ast_rules
                if ast_rules and language in ast_rules:
                    from ast_checker.checker import check_ast

                    passed, errors = check_ast(self.submission.code, language, ast_rules[language])
                    if not passed:
                        self.submission.result = JudgeStatus.AST_CHECK_FAILED
                        self.submission.statistic_info["err_info"] = "\n".join(errors)
```

- [ ] **Step 3: Update `update_problem_status_rejudge()` method**

Replace the entire method body. Key changes:
- Line 254: `self.last_result != JudgeStatus.ACCEPTED and self.submission.result == JudgeStatus.ACCEPTED` → `not is_accepted(self.last_result) and is_accepted(self.submission.result)`
- Line 264: `!= JudgeStatus.ACCEPTED` → `not is_accepted(...)`
- Line 265: store `JudgeStatus.ACCEPTED` when `is_accepted()`
- Line 266: `== JudgeStatus.ACCEPTED` → `is_accepted()`
- Lines 274, 279, 280: same pattern for OI mode

```python
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
            if problem.rule_type == ProblemRuleType.ACM:
                acm_problems_status = profile.acm_problems_status.get("problems", {})
                if not is_accepted(acm_problems_status[problem_id]["status"]):
                    acm_problems_status[problem_id]["status"] = JudgeStatus.ACCEPTED if is_accepted(self.submission.result) else self.submission.result
                    if is_accepted(self.submission.result):
                        profile.accepted_number += 1
                profile.acm_problems_status["problems"] = acm_problems_status
                profile.save(update_fields=["accepted_number", "acm_problems_status"])

            else:
                oi_problems_status = profile.oi_problems_status.get("problems", {})
                score = self.submission.statistic_info["score"]
                if not is_accepted(oi_problems_status[problem_id]["status"]):
                    # minus last time score, add this tim score
                    profile.add_score(this_time_score=score,
                                      last_time_score=oi_problems_status[problem_id]["score"])
                    oi_problems_status[problem_id]["score"] = score
                    oi_problems_status[problem_id]["status"] = JudgeStatus.ACCEPTED if is_accepted(self.submission.result) else self.submission.result
                    if is_accepted(self.submission.result):
                        profile.accepted_number += 1
                profile.oi_problems_status["problems"] = oi_problems_status
                profile.save(update_fields=["accepted_number", "oi_problems_status"])
```

- [ ] **Step 4: Update `update_problem_status()` method**

Replace the entire method body. Key changes:
- Line 292: `== JudgeStatus.ACCEPTED` → `is_accepted()`
- Lines 305, 306, 309, 310, 311: store `JudgeStatus.ACCEPTED` when `is_accepted()`, use `is_accepted()` for comparisons
- Lines 320, 323, 325, 330, 331: same for OI mode

```python
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
            if problem.rule_type == ProblemRuleType.ACM:
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

            else:
                oi_problems_status = user_profile.oi_problems_status.get("problems", {})
                score = self.submission.statistic_info["score"]
                if problem_id not in oi_problems_status:
                    user_profile.add_score(score)
                    oi_problems_status[problem_id] = {"status": profile_status,
                                                      "_id": self.problem._id,
                                                      "score": score}
                    if is_accepted(self.submission.result):
                        user_profile.accepted_number += 1
                elif not is_accepted(oi_problems_status[problem_id]["status"]):
                    # minus last time score, add this time score
                    user_profile.add_score(this_time_score=score,
                                           last_time_score=oi_problems_status[problem_id]["score"])
                    oi_problems_status[problem_id]["score"] = score
                    oi_problems_status[problem_id]["status"] = profile_status
                    if is_accepted(self.submission.result):
                        user_profile.accepted_number += 1
                user_profile.oi_problems_status["problems"] = oi_problems_status
                user_profile.save(update_fields=["submission_number", "accepted_number", "oi_problems_status"])
```

- [ ] **Step 5: Update `update_contest_problem_status()` method**

Replace the entire method body. Key changes:
- Lines 344-346: store `JudgeStatus.ACCEPTED` when `is_accepted()`, use `is_accepted()` for comparison
- Lines 357, 362: same for OI mode
- Line 371: `== JudgeStatus.ACCEPTED` → `is_accepted()`

```python
    def update_contest_problem_status(self):
        with transaction.atomic():
            user = User.objects.select_for_update().get(id=self.submission.user_id)
            user_profile = user.userprofile
            problem_id = str(self.problem.id)
            profile_status = JudgeStatus.ACCEPTED if is_accepted(self.submission.result) else self.submission.result
            if self.contest.rule_type == ContestRuleType.ACM:
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

            elif self.contest.rule_type == ContestRuleType.OI:
                contest_problems_status = user_profile.oi_problems_status.get("contest_problems", {})
                score = self.submission.statistic_info["score"]
                if problem_id not in contest_problems_status:
                    contest_problems_status[problem_id] = {"status": profile_status,
                                                           "_id": self.problem._id,
                                                           "score": score}
                else:
                    contest_problems_status[problem_id]["score"] = score
                    contest_problems_status[problem_id]["status"] = profile_status
                user_profile.oi_problems_status["contest_problems"] = contest_problems_status
                user_profile.save(update_fields=["oi_problems_status"])

            problem = Problem.objects.select_for_update().get(contest_id=self.contest_id, id=self.problem.id)
            result = str(self.submission.result)
            problem_info = problem.statistic_info
            problem_info[result] = problem_info.get(result, 0) + 1
            problem.submission_number = F("submission_number") + 1
            if is_accepted(self.submission.result):
                problem.accepted_number = F("accepted_number") + 1
            problem.save(update_fields=["submission_number", "accepted_number", "statistic_info"])
```

- [ ] **Step 6: Update `_update_acm_contest_rank()` method**

Replace the entire method body. Key changes:
- Lines 409, 424: `== JudgeStatus.ACCEPTED` → `is_accepted()`

```python
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
                info["ac_time"] = (self.submission.create_time - self.contest.start_time).total_seconds()
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
                info["ac_time"] = (self.submission.create_time - self.contest.start_time).total_seconds()
                rank.total_time += info["ac_time"]

                if problem.accepted_number == 1:
                    info["is_first_ac"] = True

            elif self.submission.result != JudgeStatus.COMPILE_ERROR:
                info["error_number"] = 1
        rank.submission_info[str(self.submission.problem_id)] = info
        rank.save(update_fields=["submission_info", "total_time", "accepted_number", "submission_number"])
```

`_update_oi_contest_rank()`: **NO CHANGE** — uses `statistic_info["score"]` set before AST check.

- [ ] **Step 7: Commit**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
git add judge/dispatcher.py
git commit -m "feat: integrate AST check into JudgeDispatcher with is_accepted() statistics"
```

---

### Task 7: Other backend query filter updates

**Files:**
- Modify: `account/views/oj.py`
- Modify: `comment/views/oj.py`
- Modify: `contest/views/admin.py`
- Modify: `problem/views/oj.py`
- Modify: `problem/views/admin.py`
- Modify: `problemset/views/oj.py`
- Modify: `problemset/management/commands/fix_problemset_progress.py`
- Modify: `class_pk/views/oj.py`
- Modify: `submission/views/admin.py`

Every `result=JudgeStatus.ACCEPTED` query filter becomes `result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED]`. Every `result != JudgeStatus.ACCEPTED` comparison becomes `not is_accepted(result)`.

Read each file before editing to verify line numbers.

- [ ] **Step 1: Update `account/views/oj.py`**

Add import at top:

```python
from submission.models import JudgeStatus, Submission, is_accepted
```

(If `JudgeStatus` and `Submission` are already imported, just add `is_accepted`.)

Line 468 — change:
```python
result=JudgeStatus.ACCEPTED,
```
to:
```python
result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED],
```

Line 483 — change:
```python
submissions = Submission.objects.filter(problem=problem, result=JudgeStatus.ACCEPTED)
```
to:
```python
submissions = Submission.objects.filter(problem=problem, result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED])
```

- [ ] **Step 2: Update `comment/views/oj.py`**

Line 31 — change:
```python
result=JudgeStatus.ACCEPTED,
```
to:
```python
result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED],
```

- [ ] **Step 3: Update `contest/views/admin.py`**

Line 220 — change:
```python
submissions = Submission.objects.filter(contest=contest, result=JudgeStatus.ACCEPTED).order_by("-create_time")
```
to:
```python
submissions = Submission.objects.filter(contest=contest, result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED]).order_by("-create_time")
```

- [ ] **Step 4: Update `problem/views/oj.py`**

Line 199 — change:
```python
result=JudgeStatus.ACCEPTED,
```
to:
```python
result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED],
```

Line 210 — change:
```python
result=JudgeStatus.ACCEPTED,
```
to:
```python
result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED],
```

Line 313 (in `ProblemYearlyACRateAPI`) — change:
```python
accepted=Count("id", filter=Q(result=JudgeStatus.ACCEPTED)),
```
to:
```python
accepted=Count("id", filter=Q(result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED])),
```

Line 241 (in `SimilarProblemAPI`): **NO CHANGE** — profile stores `ACCEPTED` (0).

- [ ] **Step 5: Update `problem/views/admin.py`**

Line 530 (in `StuckProblemsAPI`) — change:
```python
accepted=Count("id", filter=Q(result=JudgeStatus.ACCEPTED)),
```
to:
```python
accepted=Count("id", filter=Q(result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED])),
```

Line 596 (in `TopACTrendAPI`) — change:
```python
accepted=Count("id", filter=Q(result=JudgeStatus.ACCEPTED)),
```
to:
```python
accepted=Count("id", filter=Q(result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED])),
```

Lines 444, 472: **NO CHANGE** — these are full resets (`accepted_number = 0`).

- [ ] **Step 6: Update `problemset/views/oj.py`**

Add import:
```python
from submission.models import JudgeStatus, Submission, is_accepted
```

Line 190 — change:
```python
if submission.result != JudgeStatus.ACCEPTED:
```
to:
```python
if not is_accepted(submission.result):
```

- [ ] **Step 7: Update `problemset/management/commands/fix_problemset_progress.py`**

Line 41 — change:
```python
result=JudgeStatus.ACCEPTED,
```
to:
```python
result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED],
```

- [ ] **Step 8: Update `class_pk/views/oj.py`**

Line 280 — change:
```python
submissions.filter(result=JudgeStatus.ACCEPTED)
```
to:
```python
submissions.filter(result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED])
```

Line 291 — change:
```python
submissions.filter(user_id=user_id, result=JudgeStatus.ACCEPTED)
```
to:
```python
submissions.filter(user_id=user_id, result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED])
```

- [ ] **Step 9: Update `submission/views/admin.py`**

Line 81 — change:
```python
accepted_count=Count("id", filter=Q(result=JudgeStatus.ACCEPTED)),
```
to:
```python
accepted_count=Count("id", filter=Q(result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED])),
```

Line 94 — change:
```python
accepted_count=Count("id", filter=Q(result=JudgeStatus.ACCEPTED)),
```
to:
```python
accepted_count=Count("id", filter=Q(result__in=[JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED])),
```

- [ ] **Step 10: Verify no remaining raw `result=JudgeStatus.ACCEPTED` queries**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
grep -rn "result=JudgeStatus.ACCEPTED" --include="*.py" | grep -v migrations | grep -v __pycache__
```

Expected: Only the two NO-CHANGE lines in `judge/dispatcher.py` (lines 106 and 205) should remain.

- [ ] **Step 11: Commit**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
git add account/views/oj.py comment/views/oj.py contest/views/admin.py problem/views/oj.py problem/views/admin.py problemset/views/oj.py problemset/management/commands/fix_problemset_progress.py class_pk/views/oj.py submission/views/admin.py
git commit -m "feat: update all query filters to treat AST_CHECK_FAILED as accepted"
```

---

### Task 8: Frontend — status codes, types, and result display

**Files:**
- Modify: `ojnext/src/utils/constants.ts`
- Modify: `ojnext/src/utils/types.ts`
- Modify: `ojnext/src/oj/problem/components/SubmissionResult.vue`
- Modify: `ojnext/src/oj/problem/components/SubmitCode.vue`

- [ ] **Step 1: Add status code to `constants.ts`**

In the `SubmissionStatus` enum, after `submitting = 9,` add:

```typescript
  ast_check_failed = 10,
```

In the `JUDGE_STATUS` object, after the `"9"` entry add:

```typescript
  "10": {
    name: "代码检查未通过",
    type: "warning",
  },
```

- [ ] **Step 2: Update `types.ts`**

Line 68 — change:

```typescript
export type SUBMISSION_RESULT = -2 | -1 | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9
```

to:

```typescript
export type SUBMISSION_RESULT = -2 | -1 | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10
```

Add `ast_rules` to the `Problem` interface. After `show_flowchart?: boolean` (around line 139), add:

```typescript
  ast_rules?: { [key: string]: { engine: string; target?: string; min?: number; max?: number; message: string }[] } | null
```

- [ ] **Step 3: Update `SubmissionResult.vue` — error message display**

In the `msg` computed (around lines 36-38), add a case for `ast_check_failed` before the `err_info` check:

```typescript
  if (result === SubmissionStatus.ast_check_failed) {
    msg += "你的答案是正确的，但是代码结构不符合要求：\n\n"
  }
```

The full block becomes:

```typescript
  if (
    result === SubmissionStatus.compile_error ||
    result === SubmissionStatus.runtime_error
  ) {
    msg += "请仔细检查，看看代码的格式是不是写错了！\n\n"
  }

  if (result === SubmissionStatus.ast_check_failed) {
    msg += "你的答案是正确的，但是代码结构不符合要求：\n\n"
  }

  if (props.submission.statistic_info?.err_info) {
    msg += props.submission.statistic_info.err_info
  }
```

- [ ] **Step 4: Update `SubmissionResult.vue` — test case table**

In `infoTable` computed (around lines 109-114), add `ast_check_failed` to the conditions that return `[]`:

```typescript
  if (
    result === SubmissionStatus.accepted ||
    result === SubmissionStatus.compile_error ||
    result === SubmissionStatus.runtime_error ||
    result === SubmissionStatus.ast_check_failed
  ) {
    return []
  }
```

- [ ] **Step 5: Update `SubmissionResult.vue` — hide AI hints for AST failures**

In `showAIHint` computed (around line 55), add exclusion:

```typescript
    props.submission.result !== SubmissionStatus.ast_check_failed &&
```

The full block becomes:

```typescript
const showAIHint = computed(() => {
  if (!props.submission) return false
  return (
    problemStore.failCount >= 3 &&
    props.submission.result !== SubmissionStatus.accepted &&
    props.submission.result !== SubmissionStatus.ast_check_failed &&
    props.submission.result !== SubmissionStatus.pending &&
    props.submission.result !== SubmissionStatus.judging &&
    props.submission.result !== SubmissionStatus.submitting
  )
})
```

- [ ] **Step 6: Update `SubmitCode.vue` — fail count watcher**

In the fail count watcher (around line 152), change:

```typescript
    if (result !== SubmissionStatus.accepted) {
      problemStore.incrementFailCount()
    }
```

to:

```typescript
    if (result !== SubmissionStatus.accepted && result !== SubmissionStatus.ast_check_failed) {
      problemStore.incrementFailCount()
    }
```

- [ ] **Step 7: Update `SubmitCode.vue` — AC celebration watcher**

In the AC celebration watcher (around lines 162-189), change the guard and add an early return for AST failures after updating status:

```typescript
watch(
  () => submission.value?.result,
  async (result) => {
    if (result !== SubmissionStatus.accepted && result !== SubmissionStatus.ast_check_failed) return

    // 1. 刷新题目状态
    problem.value!.my_status = 0

    // 2. 创建ProblemSetSubmission记录，更新题单进度
    if (problemSetId) {
      await updateProblemSetProgress(
        Number(problemSetId),
        problem.value!.id,
        submission.value!.id,
      )
    }

    if (result !== SubmissionStatus.accepted) return

    // 3. 放烟花
    celebrate()

    // 4. 显示评价框
    if (!contestID && !problemSetId) {
      showCommentPanelDelayed()
    }

    if (problemSetId) {
      // 延迟回到题单页面
      goToProblemSetDelayed()
    }
  },
)
```

- [ ] **Step 8: Commit**

```bash
cd /home/xuyue/Projects/OJ/ojnext
git add src/utils/constants.ts src/utils/types.ts src/oj/problem/components/SubmissionResult.vue src/oj/problem/components/SubmitCode.vue
git commit -m "feat: add AST_CHECK_FAILED status and update result display"
```

---

### Task 9: Frontend — admin UI for AST rules

**Files:**
- Create: `ojnext/src/admin/problem/components/AstRulesEditor.vue`
- Modify: `ojnext/src/admin/problem/detail.vue`

- [ ] **Step 1: Create `AstRulesEditor.vue`**

```vue
<script setup lang="ts">
import type { LANGUAGE } from "utils/types"

interface AstRule {
  engine: string
  target?: string
  min?: number
  max?: number
  message: string
}

interface Props {
  modelValue: { [key: string]: AstRule[] } | null
  languages: LANGUAGE[]
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: "update:modelValue", value: { [key: string]: AstRule[] } | null): void
}>()

const activeTab = ref(props.languages[0] || "Python3")

const ENGINE_OPTIONS: SelectOption[] = [
  { label: "节点检查", type: "group", key: "node_group", children: [
    { label: "必须存在", value: "must_exist_node" },
    { label: "不能存在", value: "must_not_exist_node" },
    { label: "出现次数", value: "count_node" },
  ]},
  { label: "函数调用", type: "group", key: "func_group", children: [
    { label: "必须调用函数", value: "must_call_function" },
    { label: "不能调用函数", value: "must_not_call_function" },
    { label: "函数调用次数", value: "count_function_call" },
  ]},
  { label: "方法调用", type: "group", key: "method_group", children: [
    { label: "必须调用方法", value: "must_call_method" },
    { label: "不能调用方法", value: "must_not_call_method" },
  ]},
  { label: "运算符", type: "group", key: "op_group", children: [
    { label: "必须使用运算符", value: "must_use_operator" },
  ]},
]

const NODE_TARGET_OPTIONS: SelectOption[] = [
  { label: "for 循环", value: "for_loop" },
  { label: "while 循环", value: "while_loop" },
  { label: "if 条件", value: "if_statement" },
  { label: "else 子句", value: "else_clause" },
  { label: "函数定义", value: "function_definition" },
  { label: "return 语句", value: "return" },
  { label: "break 语句", value: "break" },
  { label: "continue 语句", value: "continue" },
  { label: "列表推导式", value: "list_comprehension" },
  { label: "列表", value: "list_literal" },
  { label: "字典", value: "dict_literal" },
  { label: "集合", value: "set_literal" },
  { label: "f-string", value: "f_string" },
  { label: "try-except", value: "try_except" },
  { label: "类定义", value: "class_definition" },
]

const OPERATOR_TARGET_OPTIONS: SelectOption[] = [
  { label: "+", value: "+" },
  { label: "-", value: "-" },
  { label: "*", value: "*" },
  { label: "/", value: "/" },
  { label: "//", value: "//" },
  { label: "%", value: "%" },
  { label: "**", value: "**" },
  { label: "+=", value: "+=" },
  { label: "-=", value: "-=" },
  { label: "==", value: "==" },
  { label: "!=", value: "!=" },
  { label: ">", value: ">" },
  { label: ">=", value: ">=" },
  { label: "<", value: "<" },
  { label: "<=", value: "<=" },
  { label: "and / &&", value: "and" },
  { label: "or / ||", value: "or" },
  { label: "not / !", value: "not" },
]

const NODE_ENGINES = ["must_exist_node", "must_not_exist_node", "count_node"]
const FUNCTION_ENGINES = ["must_call_function", "must_not_call_function", "count_function_call"]
const METHOD_ENGINES = ["must_call_method", "must_not_call_method"]
const OPERATOR_ENGINES = ["must_use_operator"]
const COUNT_ENGINES = ["count_node", "count_function_call"]

function isNodeEngine(engine: string) { return NODE_ENGINES.includes(engine) }
function isFunctionEngine(engine: string) { return FUNCTION_ENGINES.includes(engine) }
function isMethodEngine(engine: string) { return METHOD_ENGINES.includes(engine) }
function isOperatorEngine(engine: string) { return OPERATOR_ENGINES.includes(engine) }
function isCountEngine(engine: string) { return COUNT_ENGINES.includes(engine) }

function needsTargetDropdown(engine: string) { return isNodeEngine(engine) }
function needsTargetInput(engine: string) { return isFunctionEngine(engine) || isMethodEngine(engine) }
function needsOperatorDropdown(engine: string) { return isOperatorEngine(engine) }

function getRulesForLang(lang: string): AstRule[] {
  if (!props.modelValue) return []
  return props.modelValue[lang] || []
}

function updateRules(lang: string, rules: AstRule[]) {
  const current = { ...(props.modelValue || {}) }
  if (rules.length === 0) {
    delete current[lang]
  } else {
    current[lang] = rules
  }
  emit("update:modelValue", Object.keys(current).length > 0 ? current : null)
}

function addRule(lang: string) {
  const rules = [...getRulesForLang(lang)]
  rules.push({ engine: "must_exist_node", target: "for_loop", message: "" })
  updateRules(lang, rules)
}

function removeRule(lang: string, index: number) {
  const rules = [...getRulesForLang(lang)]
  rules.splice(index, 1)
  updateRules(lang, rules)
}

function updateRule(lang: string, index: number, field: string, value: any) {
  const rules = [...getRulesForLang(lang)]
  const rule = { ...rules[index] }

  if (field === "engine") {
    rule.engine = value
    if (isNodeEngine(value)) rule.target = "for_loop"
    else if (isOperatorEngine(value)) rule.target = "+"
    else rule.target = ""
    delete rule.min
    delete rule.max
  } else if (field === "target") {
    rule.target = value
  } else if (field === "min") {
    if (value === null || value === undefined) delete rule.min
    else rule.min = value
  } else if (field === "max") {
    if (value === null || value === undefined) delete rule.max
    else rule.max = value
  } else if (field === "message") {
    rule.message = value
  }

  rules[index] = rule
  updateRules(lang, rules)
}

watch(() => props.languages, (langs) => {
  if (langs.length && !langs.includes(activeTab.value as LANGUAGE)) {
    activeTab.value = langs[0]
  }
})
</script>

<template>
  <n-collapse>
    <n-collapse-item title="代码规则检查（选填）" name="ast-rules">
      <n-tabs v-if="languages.length" type="segment" v-model:value="activeTab">
        <n-tab-pane v-for="lang in languages" :key="lang" :name="lang" :tab="lang">
          <n-flex vertical>
            <div v-for="(rule, index) in getRulesForLang(lang)" :key="index" style="margin-bottom: 8px">
              <n-flex align="center" :wrap="true">
                <n-select
                  :options="ENGINE_OPTIONS"
                  :value="rule.engine"
                  @update:value="(v: string) => updateRule(lang, index, 'engine', v)"
                  style="width: 160px"
                  size="small"
                />
                <n-select
                  v-if="needsTargetDropdown(rule.engine)"
                  :options="NODE_TARGET_OPTIONS"
                  :value="rule.target"
                  @update:value="(v: string) => updateRule(lang, index, 'target', v)"
                  style="width: 140px"
                  size="small"
                  filterable
                />
                <n-input
                  v-if="needsTargetInput(rule.engine)"
                  :value="rule.target"
                  @update:value="(v: string) => updateRule(lang, index, 'target', v)"
                  placeholder="函数/方法名"
                  style="width: 120px"
                  size="small"
                />
                <n-select
                  v-if="needsOperatorDropdown(rule.engine)"
                  :options="OPERATOR_TARGET_OPTIONS"
                  :value="rule.target"
                  @update:value="(v: string) => updateRule(lang, index, 'target', v)"
                  style="width: 100px"
                  size="small"
                />
                <n-input-number
                  v-if="isCountEngine(rule.engine)"
                  :value="rule.min ?? null"
                  @update:value="(v: number | null) => updateRule(lang, index, 'min', v)"
                  placeholder="最少"
                  style="width: 90px"
                  size="small"
                  :min="0"
                  clearable
                />
                <n-input-number
                  v-if="isCountEngine(rule.engine)"
                  :value="rule.max ?? null"
                  @update:value="(v: number | null) => updateRule(lang, index, 'max', v)"
                  placeholder="最多"
                  style="width: 90px"
                  size="small"
                  :min="0"
                  clearable
                />
                <n-input
                  :value="rule.message"
                  @update:value="(v: string) => updateRule(lang, index, 'message', v)"
                  placeholder="错误提示（选填）"
                  style="width: 200px"
                  size="small"
                />
                <n-button size="small" tertiary type="error" @click="removeRule(lang, index)">
                  删除
                </n-button>
              </n-flex>
            </div>
            <n-button size="small" tertiary type="primary" @click="addRule(lang)">
              添加规则
            </n-button>
          </n-flex>
        </n-tab-pane>
      </n-tabs>
      <n-empty v-else description="请先选择编程语言" />
    </n-collapse-item>
  </n-collapse>
</template>
```

- [ ] **Step 2: Integrate `AstRulesEditor` into `detail.vue`**

Add import (around line 5, with the other component imports):

```typescript
import AstRulesEditor from "./components/AstRulesEditor.vue"
```

Add `ast_rules` to the `problem` default storage object (around line 89, after `show_flowchart: false,`):

```typescript
  ast_rules: null as { [key: string]: any[] } | null,
```

In `getProblemDetail()`, add `ast_rules` loading (after the flowchart fields, around line 178):

```typescript
    problem.value.ast_rules = data.ast_rules ?? null
```

In the template, add the `AstRulesEditor` component. Place it after the code area section and before the test case area section (around line 646, before `<n-divider />`). Find this divider:

```html
  <n-divider />

  <h2 class="title">测试用例区域</h2>
```

Insert before that divider:

```html
  <AstRulesEditor
    v-model="problem.ast_rules"
    :languages="problem.languages"
  />

  <n-divider />

  <h2 class="title">测试用例区域</h2>
```

- [ ] **Step 3: Start dev server and test**

```bash
cd /home/xuyue/Projects/OJ/ojnext
npm start
```

Open the admin problem edit page in a browser. Verify:
1. "代码规则检查" collapsible section appears between code area and test case area
2. Expanding it shows language tabs matching the selected languages
3. "添加规则" button adds a rule row
4. Engine dropdown shows grouped options
5. Target field changes based on engine type (dropdown for nodes, input for functions, dropdown for operators)
6. Min/max fields appear only for count engines
7. Delete button removes a rule
8. Switching language tabs shows per-language rules

- [ ] **Step 4: Commit**

```bash
cd /home/xuyue/Projects/OJ/ojnext
git add src/admin/problem/components/AstRulesEditor.vue src/admin/problem/detail.vue
git commit -m "feat: add admin UI for AST rule configuration"
```

---

## End-to-End Verification

After all tasks are complete, verify the full flow:

1. **Admin**: Edit a problem, add AST rules (e.g., Python3: must_exist_node → for_loop)
2. **Submit**: Submit a Python3 solution that passes all test cases but uses `while` instead of `for`
3. **Expected**: Submission result shows "代码检查未通过" with error "必须使用 for 循环"
4. **Statistics**: Problem `accepted_number` increases, user profile shows the problem as solved (green AC icon), `statistic_info` has a `"10"` entry
5. **Submit again**: Submit with `for` loop — should show "答案正确" with confetti
