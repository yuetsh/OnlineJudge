# 提交前自动代码格式化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户提交 Python3/C/C++ 代码时，前端先调用新增的 `/api/format_code` 接口（后端用 `ruff format` / `clang-format`）格式化代码，更新编辑器内容后再提交；其他语言原样提交，格式化失败时按语言区分降级。

**Architecture:** 后端在 `submission` 应用新增一个同步 `APIView`（`FormatCodeAPI`），内部通过 `subprocess` 调用 `ruff format` 或 `clang-format`，返回格式化后的代码或错误码（`format-error` / `server-error`）。前端在 `SubmitCode.vue` 的 `submit()` 中，对 Python3/C/C++ 调用该接口，成功则写回 `codeStore`（驱动编辑器与 Yjs 同步），`format-error` 阻止提交并提示，其他错误静默降级提交原代码。

**Tech Stack:** Django 6 + DRF (`utils.api.APIView`), `subprocess`, `ruff` CLI, `clang-format` CLI；Vue 3 + Pinia + axios (`utils/http.ts`)

> 注：本项目 `CLAUDE.md` 明确"不写测试"。本计划用手动验证（dev server + curl / 浏览器）代替自动化测试步骤。

---

## Backend Tasks

### Task 1: 新建 `submission/utils.py` — 格式化工具封装

**Files:**
- Create: `OnlineJudge/submission/utils.py`

- [ ] **Step 1: 编写格式化函数与异常类**

```python
import subprocess

CLANG_FORMAT_STYLE = "{BasedOnStyle: LLVM, IndentWidth: 4, BreakBeforeBraces: Attach}"


class FormatSyntaxError(Exception):
    """格式化工具因代码本身存在语法错误而失败（目前只有 ruff format 会触发）"""


class FormatToolError(Exception):
    """格式化工具执行本身失败：超时、二进制缺失、非预期的非零退出码"""


def format_code(code, language):
    """
    :param code: 用户代码
    :param language: "python" | "c" | "cpp"
    :return: 格式化后的代码字符串
    :raises FormatSyntaxError: 代码语法错误导致格式化失败（仅 python）
    :raises FormatToolError: 格式化工具本身执行失败
    """
    if language == "python":
        return _format_with_ruff(code)
    return _format_with_clang(code, language)


def _format_with_ruff(code):
    try:
        result = subprocess.run(
            ["ruff", "format", "--stdin-filename", "code.py", "-"],
            input=code,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        raise FormatToolError(str(e))
    if result.returncode != 0:
        raise FormatSyntaxError(result.stderr)
    return result.stdout


def _format_with_clang(code, language):
    filename = "code.c" if language == "c" else "code.cpp"
    try:
        result = subprocess.run(
            [
                "clang-format",
                f"-assume-filename={filename}",
                f"-style={CLANG_FORMAT_STYLE}",
            ],
            input=code,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        raise FormatToolError(str(e))
    if result.returncode != 0:
        raise FormatToolError(result.stderr)
    return result.stdout
```

- [ ] **Step 2: 手动验证 ruff 分支**

Run:
```bash
cd OnlineJudge
uv run python -c "
from submission.utils import format_code
print(repr(format_code('x=1\ndef f( a,b ):\n  return a+b\n', 'python')))
"
```
Expected: 输出格式化后的代码（4 空格缩进、`x = 1`、空两行分隔函数等），不抛异常。

- [ ] **Step 3: 手动验证 ruff 语法错误分支**

Run:
```bash
uv run python -c "
from submission.utils import format_code, FormatSyntaxError
try:
    format_code('def f(:\n  pass\n', 'python')
except FormatSyntaxError as e:
    print('FormatSyntaxError:', e)
"
```
Expected: 打印 `FormatSyntaxError: ...` 且包含 ruff 的语法错误信息。

- [ ] **Step 4: 手动验证 clang-format 分支**

Run:
```bash
uv run python -c "
from submission.utils import format_code
print(format_code('#include<stdio.h>\nint main(){\nint a=1;\nreturn 0;}\n', 'cpp'))
"
```
Expected: 输出 4 空格缩进、`{` 跟在行尾（Attach 风格）的格式化代码。

- [ ] **Step 5: Commit**

```bash
git add submission/utils.py
git commit -m "feat(submission): add ruff/clang-format code formatting helper"
```

---

### Task 2: 新增 `FormatCodeSerializer`

**Files:**
- Modify: `OnlineJudge/submission/serializers.py`

- [ ] **Step 1: 在文件末尾追加序列化器**

在 `submission/serializers.py` 末尾追加：

```python
class FormatCodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=1024 * 1024)
    language = serializers.ChoiceField(choices=("python", "c", "cpp"))
```

- [ ] **Step 2: 手动验证**

Run:
```bash
cd OnlineJudge
uv run python -c "
from submission.serializers import FormatCodeSerializer
s = FormatCodeSerializer(data={'code': 'x=1', 'language': 'python'})
print(s.is_valid(), s.validated_data)
s2 = FormatCodeSerializer(data={'code': 'x=1', 'language': 'java'})
print(s2.is_valid(), s2.errors)
"
```
Expected: 第一行 `True {'code': 'x=1', 'language': 'python'}`；第二行 `False {'language': [ErrorDetail(string='\"java\" is not a valid choice.', code='invalid_choice')]}`

- [ ] **Step 3: Commit**

```bash
git add submission/serializers.py
git commit -m "feat(submission): add FormatCodeSerializer"
```

---

### Task 3: 新增 `FormatCodeAPI` 视图

**Files:**
- Modify: `OnlineJudge/submission/views/oj.py`

- [ ] **Step 1: 在文件顶部导入区添加 logging 和新依赖**

当前顶部导入（`submission/views/oj.py:1-16`）：

```python
import ipaddress

from asgiref.sync import sync_to_async
from django.utils import timezone

from account.decorators import check_contest_permission, login_required
from contest.models import ContestStatus
from flowchart.models import FlowchartSubmission
from judge.tasks import judge_task
from options.options import SysOptions

# from judge.dispatcher import JudgeDispatcher
from problem.models import Problem, ProblemRuleType
from utils.api import AsyncAPIView, validate_serializer
from utils.cache import cache
from utils.captcha import Captcha
from utils.throttling import TokenBucket

from ..models import Submission
from ..serializers import (
    CreateSubmissionSerializer,
    ShareSubmissionSerializer,
    SubmissionListSerializer,
    SubmissionModelSerializer,
    SubmissionSafeModelSerializer,
    bulk_fetch_problemset_progress,
)
```

修改为（新增 `import logging`、`APIView`、`FormatCodeSerializer`、`from ..utils import ...`）：

```python
import ipaddress
import logging

from asgiref.sync import sync_to_async
from django.utils import timezone

from account.decorators import check_contest_permission, login_required
from contest.models import ContestStatus
from flowchart.models import FlowchartSubmission
from judge.tasks import judge_task
from options.options import SysOptions

# from judge.dispatcher import JudgeDispatcher
from problem.models import Problem, ProblemRuleType
from utils.api import APIView, AsyncAPIView, validate_serializer
from utils.cache import cache
from utils.captcha import Captcha
from utils.throttling import TokenBucket

from ..models import Submission
from ..serializers import (
    CreateSubmissionSerializer,
    FormatCodeSerializer,
    ShareSubmissionSerializer,
    SubmissionListSerializer,
    SubmissionModelSerializer,
    SubmissionSafeModelSerializer,
    bulk_fetch_problemset_progress,
)
from ..utils import FormatSyntaxError, FormatToolError, format_code

logger = logging.getLogger(__name__)
```

- [ ] **Step 2: 在文件末尾追加视图类**

在 `submission/views/oj.py` 文件末尾追加：

```python
class FormatCodeAPI(APIView):
    @login_required
    @validate_serializer(FormatCodeSerializer)
    def post(self, request):
        code = request.data["code"]
        language = request.data["language"]
        try:
            formatted = format_code(code, language)
        except FormatSyntaxError as e:
            return self.error(msg=str(e), err="format-error")
        except FormatToolError as e:
            logger.exception("format_code tool error: %s", e)
            return self.error(msg="format failed", err="server-error")
        return self.success({"code": formatted})
```

- [ ] **Step 3: 手动验证（需先启动 dev server）**

Run（另开终端）:
```bash
cd OnlineJudge && python dev.py
```

确认服务起来后，用已登录用户的 session/cookie 验证（替换 `<csrftoken>`/`<sessionid>` 为实际 cookie 值，可从浏览器登录后开发者工具中获取）：

```bash
curl -s -X POST http://localhost:8000/api/format_code \
  -H "Content-Type: application/json" \
  -H "Cookie: sessionid=<sessionid>; csrftoken=<csrftoken>" \
  -H "X-CSRFToken: <csrftoken>" \
  -d '{"code": "x=1\ndef f( a,b ):\n  return a+b\n", "language": "python"}'
```
Expected: `{"error": null, "data": {"code": "x = 1\n\n\ndef f(a, b):\n    return a + b\n"}}`

未登录时（不带 Cookie）请求应返回 `{"error": "login-required", ...}`。

- [ ] **Step 4: Commit**

```bash
git add submission/views/oj.py
git commit -m "feat(submission): add FormatCodeAPI view"
```

---

### Task 4: 注册 URL 路由

**Files:**
- Modify: `OnlineJudge/submission/urls/oj.py`

- [ ] **Step 1: 修改文件**

当前内容：

```python
from django.urls import path

from ..views.oj import (
    ContestSubmissionListAPI,
    SubmissionAPI,
    SubmissionExistsAPI,
    SubmissionListAPI,
    SubmissionsTodayCount,
)

urlpatterns = [
    path("submission", SubmissionAPI.as_view()),
    path("submissions", SubmissionListAPI.as_view()),
    path("submissions/today_count", SubmissionsTodayCount.as_view()),
    path("submission_exists", SubmissionExistsAPI.as_view()),  # DEPRECATED: 前端未调用
    path("contest_submissions", ContestSubmissionListAPI.as_view()),
]
```

改为：

```python
from django.urls import path

from ..views.oj import (
    ContestSubmissionListAPI,
    FormatCodeAPI,
    SubmissionAPI,
    SubmissionExistsAPI,
    SubmissionListAPI,
    SubmissionsTodayCount,
)

urlpatterns = [
    path("submission", SubmissionAPI.as_view()),
    path("submissions", SubmissionListAPI.as_view()),
    path("submissions/today_count", SubmissionsTodayCount.as_view()),
    path("submission_exists", SubmissionExistsAPI.as_view()),  # DEPRECATED: 前端未调用
    path("contest_submissions", ContestSubmissionListAPI.as_view()),
    path("format_code", FormatCodeAPI.as_view()),
]
```

- [ ] **Step 2: 手动验证**

Run（dev server 已启动的前提下）：
```bash
curl -s -X POST http://localhost:8000/api/format_code -H "Content-Type: application/json" -d '{}'
```
Expected: 返回 `{"error": "login-required", ...}`（未登录），说明路由已生效（而不是 404）。

- [ ] **Step 3: Commit**

```bash
git add submission/urls/oj.py
git commit -m "feat(submission): register /api/format_code route"
```

---

### Task 5: 将 `ruff` 移入主依赖

**Files:**
- Modify: `OnlineJudge/pyproject.toml`
- Modify: `OnlineJudge/deploy/requirements.txt` (通过命令生成，不手写)

- [ ] **Step 1: 编辑 `pyproject.toml`**

当前 `[project] dependencies` 列表末尾（`pyproject.toml`）：

```toml
    "asgiref>=3.11.1",
    "jieba>=0.42.1",
]

[dependency-groups]
dev = [
    "ruff>=0.15.11",
]
```

改为（`ruff` 移入 `dependencies`，删除 `[dependency-groups]`）：

```toml
    "asgiref>=3.11.1",
    "jieba>=0.42.1",
    "ruff>=0.15.11",
]
```

> 如果 `[dependency-groups]` 块下还有其他依赖项，只删除 `"ruff>=0.15.11",` 这一行并保留其余内容；本仓库当前该块只有 ruff 一项，可整块删除。

- [ ] **Step 2: 同步 lock 文件与 requirements**

Run:
```bash
cd OnlineJudge
uv sync
./reqs.sh
```
Expected: `uv.lock` 更新（ruff 从 dev group 移到主依赖组），`deploy/requirements.txt` 重新生成并包含 `ruff==...` 一行。

- [ ] **Step 3: 验证 ruff 仍可用**

Run:
```bash
uv run ruff --version
```
Expected: 输出版本号（如 `ruff 0.15.12`），不报错。

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock deploy/requirements.txt
git commit -m "build: move ruff from dev to main dependencies (needed at runtime for code formatting)"
```

---

### Task 6: Dockerfile 增加 `clang-format`

**Files:**
- Modify: `OnlineJudge/Dockerfile`

- [ ] **Step 1: 修改 `apk add` 列表**

当前（`Dockerfile:17-23`）：

```dockerfile
apk add --no-cache \
  gcc libc-dev python3-dev \
  libpq libpq-dev \
  libjpeg-turbo libjpeg-turbo-dev \
  zlib zlib-dev \
  freetype freetype-dev \
  supervisor openssl nginx curl unzip
```

改为（新增 `clang-extra-tools`，提供 `clang-format` 二进制；放在常驻依赖里，不会被后面的 `apk del` 清理）：

```dockerfile
apk add --no-cache \
  gcc libc-dev python3-dev \
  libpq libpq-dev \
  libjpeg-turbo libjpeg-turbo-dev \
  zlib zlib-dev \
  freetype freetype-dev \
  supervisor openssl nginx curl unzip \
  clang-extra-tools
```

- [ ] **Step 2: 验证镜像可构建并包含 clang-format**

Run:
```bash
cd OnlineJudge
docker build -t oj-backend-format-test .
docker run --rm oj-backend-format-test clang-format --version
```
Expected: 构建成功，且输出 `clang-format version ...`（不报 `command not found`）。

> 该步骤构建耗时较长，如本地环境无法运行 docker，可跳过实际构建，但需在 PR 描述中说明未验证，留待 CI/部署时确认。

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "build: install clang-extra-tools for clang-format in backend image"
```

---

## Frontend Tasks

### Task 7: 新增 `formatCode` API 函数

**Files:**
- Modify: `ojnext/src/oj/api.ts`

- [ ] **Step 1: 在 `submitCode` 函数后追加新函数**

当前（`ojnext/src/oj/api.ts:61-63`）：

```ts
export function submitCode(data: SubmitCodePayload) {
  return http.post("submission", data)
}
```

改为：

```ts
export function submitCode(data: SubmitCodePayload) {
  return http.post("submission", data)
}

export function formatCode(data: { code: string; language: string }) {
  return http.post<{ code: string }>("format_code", data)
}
```

- [ ] **Step 2: 手动验证**

Run:
```bash
cd ojnext
npx tsc --noEmit
```
Expected: 无新增类型错误（与修改前结果一致）。

- [ ] **Step 3: Commit**

```bash
git add src/oj/api.ts
git commit -m "feat(api): add formatCode endpoint for pre-submit formatting"
```

---

### Task 8: `SubmitCode.vue` 集成提交前自动格式化

**Files:**
- Modify: `ojnext/src/oj/problem/components/SubmitCode.vue`

- [ ] **Step 1: 添加导入**

当前导入区（`SubmitCode.vue:1-14`）：

```ts
import { Icon } from "@iconify/vue"
import { storeToRefs } from "pinia"
import { getComment, submitCode, updateProblemSetProgress } from "oj/api"
import { useCodeStore } from "oj/store/code"
import { useProblemStore } from "oj/store/problem"
import { useFireworks } from "oj/problem/composables/useFireworks"
import { useSubmissionMonitor } from "oj/problem/composables/useSubmissionMonitor"
import { SubmissionStatus } from "utils/constants"
import type { SubmitCodePayload } from "utils/types"
import SubmissionResult from "./SubmissionResult.vue"
import { useBreakpoints } from "shared/composables/breakpoints"
import { useUserStore } from "shared/store/user"
import { checkPythonSyntax } from "oj/problem/utils/pythonSyntaxCheck"
```

改为（新增 `formatCode` 导入、`LANGUAGE_FORMAT_VALUE` 导入）：

```ts
import { Icon } from "@iconify/vue"
import { storeToRefs } from "pinia"
import {
  formatCode,
  getComment,
  submitCode,
  updateProblemSetProgress,
} from "oj/api"
import { useCodeStore } from "oj/store/code"
import { useProblemStore } from "oj/store/problem"
import { useFireworks } from "oj/problem/composables/useFireworks"
import { useSubmissionMonitor } from "oj/problem/composables/useSubmissionMonitor"
import { LANGUAGE_FORMAT_VALUE, SubmissionStatus } from "utils/constants"
import type { SubmitCodePayload } from "utils/types"
import SubmissionResult from "./SubmissionResult.vue"
import { useBreakpoints } from "shared/composables/breakpoints"
import { useUserStore } from "shared/store/user"
import { checkPythonSyntax } from "oj/problem/utils/pythonSyntaxCheck"
```

- [ ] **Step 2: 在 `submit()` 中插入格式化步骤**

当前 `submit()` 函数（`SubmitCode.vue:110-139`）：

```ts
async function submit() {
  if (!userStore.isAuthed) return

  // 0. Python3 语法检测
  if (codeStore.code.language === "Python3") {
    const syntaxError = checkPythonSyntax(codeStore.code.value)
    if (syntaxError) {
      message.warning(`第 ${syntaxError.line} 行存在语法错误，请修正后再提交`)
      return
    }
  }

  // 1. 构建提交数据
  const data: SubmitCodePayload = {
    problem_id: problem.value!.id,
    language: codeStore.code.language,
    code: codeStore.code.value,
  }
  if (contestID) {
    data.contest_id = parseInt(contestID)
  }
  // 2. 提交代码到后端
  const res = await submitCode(data)
  console.log(`[Submit] 代码已提交: ID=${res.data.submission_id}`)

  // 3. 启动冷却 + 监控
  startCooldown()
  startMonitoring(res.data.submission_id)
  showResult.value = true
}
```

改为（在"1. 构建提交数据"之前插入"0.5 提交前自动格式化"）：

```ts
async function submit() {
  if (!userStore.isAuthed) return

  // 0. Python3 语法检测
  if (codeStore.code.language === "Python3") {
    const syntaxError = checkPythonSyntax(codeStore.code.value)
    if (syntaxError) {
      message.warning(`第 ${syntaxError.line} 行存在语法错误，请修正后再提交`)
      return
    }
  }

  // 0.5 提交前自动格式化（Python3 用 ruff，C/C++ 用 clang-format）
  const formatLang = LANGUAGE_FORMAT_VALUE[codeStore.code.language]
  if (["python", "c", "cpp"].includes(formatLang)) {
    try {
      const res = await formatCode({
        code: codeStore.code.value,
        language: formatLang,
      })
      codeStore.setCode(res.data.code)
    } catch (e: any) {
      if (e?.error === "format-error") {
        // 仅 Python3 会出现：代码本身存在语法错误
        message.warning(`代码格式化失败：${e.data}，请检查代码后重试`)
        return
      }
      // server-error / 网络异常：格式化工具问题，静默降级，提交原代码
    }
  }

  // 1. 构建提交数据
  const data: SubmitCodePayload = {
    problem_id: problem.value!.id,
    language: codeStore.code.language,
    code: codeStore.code.value,
  }
  if (contestID) {
    data.contest_id = parseInt(contestID)
  }
  // 2. 提交代码到后端
  const res = await submitCode(data)
  console.log(`[Submit] 代码已提交: ID=${res.data.submission_id}`)

  // 3. 启动冷却 + 监控
  startCooldown()
  startMonitoring(res.data.submission_id)
  showResult.value = true
}
```

- [ ] **Step 3: 启动前后端 dev server 并手动验证**

Run（两个终端）:
```bash
cd OnlineJudge && python dev.py
cd ojnext && npm start
```

浏览器打开 `http://localhost:5173`，登录后进入任意题目页：

1. 选择 Python3，编辑器中输入不规范格式的代码（如 `x=1\ndef f( a,b ):\n  return a+b`），点击"提交代码"。
   Expected: 编辑器内容自动变为 ruff 格式化后的样式（如 `x = 1` 单独成行，函数前空两行，4 空格缩进），随后正常提交并显示判题结果。
2. 选择 C++，输入未格式化的代码（如 `#include<iostream>\nint main(){\nstd::cout<<"hi";\nreturn 0;}`），点击"提交代码"。
   Expected: 编辑器内容自动变为 clang-format 格式化后的样式（4 空格缩进，`{` 跟在行尾），随后正常提交。
3. 选择 Java，提交任意代码。
   Expected: 不触发格式化请求（浏览器 Network 面板中无 `/api/format_code` 请求），直接提交。
4. （可选）Python3 下输入有语法错误但能通过 `checkPythonSyntax` 的边界代码，验证若后端返回 `format-error`，会弹出警告且不提交。

- [ ] **Step 4: Commit**

```bash
git add src/oj/problem/components/SubmitCode.vue
git commit -m "feat(problem): auto-format Python3/C/C++ code before submit"
```

---

## Self-Review Notes

- **Spec coverage:** 接口位置/参数/响应格式（Task 1-4）、依赖与 Docker（Task 5-6）、前端 API + 集成点 + 错误分类处理（Task 7-8）均已覆盖；Java/Go/JS 跳过逻辑通过 `["python","c","cpp"].includes(formatLang)` 判断实现。
- **Type consistency:** `format_code(code, language)` 签名、`FormatSyntaxError`/`FormatToolError` 异常名在 Task 1/3 中一致；前端 `formatCode({code, language})` 返回 `{code: string}`，与 `res.data.code` 用法一致；`err` 取值 `"format-error"` / `"server-error"` 在后端 Task 3 与前端 Task 8 中一致。
- **Out of scope（与 spec 一致，未在本计划中实现）:** 格式化开关、Java/Go/JS 格式化、`CodeEditor.vue` 只读组件改动。
