# 提交前自动代码格式化 — Design Spec

**Date:** 2026-06-14
**Status:** Approved

---

## Overview

为 Python3、C、C++ 提供"提交前自动格式化"功能：用户点击"提交代码"时，前端先调用后端格式化接口
（Python3 用 `ruff format`，C/C++ 用 `clang-format`），将格式化后的代码写回编辑器（含 Yjs 协作同步）并提交。
其他语言（Java/Go/JavaScript）跳过格式化，原样提交。无开关，默认开启。

---

## Backend

### Endpoint

```
POST /api/format_code
```

- 放在 `submission` 应用，与 `SubmissionAPI` 同级（`submission/views/oj.py` / `submission/urls/oj.py` / `submission/serializers.py`）
- 需要登录（`@login_required`），与提交代码一致

### Request

```json
{ "code": "...", "language": "python" }
```

- `language`: `ChoiceField`，取值 `"python"` / `"c"` / `"cpp"`（对应前端 `LANGUAGE_FORMAT_VALUE`）
- `code`: `CharField(max_length=1024 * 1024)`，与 `CreateSubmissionSerializer.code` 一致

### 格式化实现

新增 `submission/utils.py`（或现有 utils 模块）中的 `format_code(code: str, language: str) -> str`：

- `language == "python"`:
  ```python
  subprocess.run(
      ["ruff", "format", "--stdin-filename", "code.py", "-"],
      input=code, capture_output=True, text=True, timeout=5,
  )
  ```
  - `returncode != 0` → 视为语法错误，抛出携带 `stderr` 的异常，view 返回 `err="format-error"`

- `language in ("c", "cpp")`:
  ```python
  filename = "code.c" if language == "c" else "code.cpp"
  subprocess.run(
      ["clang-format", f"-assume-filename={filename}",
       "-style={BasedOnStyle: LLVM, IndentWidth: 4, BreakBeforeBraces: Attach}"],
      input=code, capture_output=True, text=True, timeout=5,
  )
  ```
  - `returncode != 0` 或 subprocess 异常（超时等）→ view 返回 `err="server-error"`（clang-format 正常情况下几乎不会因代码内容失败）

### Response

| 情况 | 响应 |
|---|---|
| 成功 | `self.success({"code": "<formatted code>"})` |
| Python 语法错误（ruff format 非0） | `self.error(msg="<ruff stderr 摘要>", err="format-error")` |
| 工具执行异常（超时/二进制缺失/clang-format 非0） | `self.error(msg="format failed", err="server-error")` |

### 依赖与部署变更

- `pyproject.toml`: 将 `ruff` 从 `[dependency-groups].dev` 移到主依赖（`[project.dependencies]`），同步更新 `deploy/requirements.txt`
- `Dockerfile`: `apk add` 中新增 `clang-extra-tools`（提供 `clang-format` 二进制），放在常驻依赖区（不在 `apk del` 清理列表中）

---

## Frontend

### API

`ojnext/src/oj/api.ts` 新增：

```ts
export function formatCode(data: { code: string; language: string }) {
  return http.post<{ code: string }>("format_code", data)
}
```

### 集成点：`ojnext/src/oj/problem/components/SubmitCode.vue`

在现有 Python 语法检测（`checkPythonSyntax`）之后、构建 `SubmitCodePayload` 之前插入：

```ts
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
      // 仅 Python3 会出现：代码本身有语法问题
      message.warning(`代码格式化失败：${e.data}，请检查代码后重试`)
      return
    }
    // server-error / 网络异常：工具问题，静默降级，提交原代码
  }
}
```

注：`http.ts` 拦截器会剥掉响应信封——成功时 `res` 即 `{error: null, data: {...}}`，失败时 `Promise.reject(res.data)`（即 `{error, data}`），因此用 `try/catch` 而非检查 `res.data.error`。

- `codeStore.setCode(...)` 更新 `code.value`，`SyncCodeEditor` 通过 `v-model` 绑定自动刷新编辑器显示并同步给协作者
- 提交时使用（可能已更新的）`codeStore.code.value` 构建 `SubmitCodePayload`，逻辑不变
- 不增加 loading 文案，格式化请求耗时很短，按钮状态保持原有的"正在提交"流程

---

## Error Handling Summary

| 失败类型 | Python3 | C/C++ |
|---|---|---|
| 格式化工具报代码语法错误（`format-error`） | 提示用户检查代码，**阻止提交** | 不会出现（clang-format 容错） |
| 工具/服务异常（`server-error`、网络错误、超时） | 静默降级，提交原代码 | 静默降级，提交原代码 |

---

## Out of Scope

- Java / Go / JavaScript 格式化（暂无对应工具集成）
- 格式化开关 / 用户偏好设置
- `CodeEditor.vue`（只读展示组件）不涉及
