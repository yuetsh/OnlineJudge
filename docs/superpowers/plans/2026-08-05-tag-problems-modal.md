# 标签管理点击查看对应题目 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 后台标签管理页点击标签名或题目数，弹窗列出该标签下的题目，支持跳转编辑、按标题搜索、移除该题的这个标签。

**Architecture:** 给后台题目列表 API `ProblemAdminAPI.get` 加一个 `tag_id` 查询参数，弹窗直接复用它，从而白拿分页、标题搜索和创建者权限过滤。移除标签复用已有的 `BatchProblemTagAPI`（`action="remove"`）。没有新建后端接口。

**Tech Stack:** 后端 Django 6 + DRF（`OnlineJudge/`）；前端 Vue 3 + TypeScript + Naive UI（`ojnext/`）。

**Spec:** `docs/superpowers/specs/2026-08-05-tag-problems-modal-design.md`

## Global Constraints

- **不写测试。** 两个子项目的 CLAUDE.md 都规定 "Do not write tests"。本计划用 lint / 构建 / Django shell 验证代替测试步骤。
- **两个 git 仓库。** `OnlineJudge/` 和 `ojnext/` 各自是独立 git 仓库，根目录 `/home/xuyue/Projects/OJ` 不是仓库。每个任务的 commit 必须在对应子目录里执行。
- 前端不需要手写 import：`ref` / `computed` / `watch` / `h` / `useRouter` / `useMessage` / `useToggle` / `watchDebounced` / `DataTableColumn` / 所有 `N*` 组件都由 `unplugin-auto-import` 和 `unplugin-vue-components` 自动导入。在 `render` 函数里以变量形式使用的 Naive UI 组件（如 `h(NButton, ...)`）**必须**手动 `import { NButton } from "naive-ui"`。
- 后端代码风格：ruff，双引号，行宽 180。
- 前端代码风格：Prettier，无分号，双引号。

---

### Task 1: 后端按标签筛选题目

**Files:**
- Modify: `OnlineJudge/problem/views/admin.py:270-281`（`ProblemAdminAPI.get`）

**Interfaces:**
- Consumes: 无
- Produces: `GET /api/admin/problem?paging=true&offset=0&limit=10&tag_id=<int>` 返回该标签下的题目分页数据（结构与现有列表一致：`{results: [...], total: n}`）

- [ ] **Step 1: 加 tag_id 过滤**

在 `OnlineJudge/problem/views/admin.py` 的 `ProblemAdminAPI.get` 里，把现有的 keyword 过滤块：

```python
        keyword = request.GET.get("keyword", "").strip()
        if keyword:
            problems = problems.filter(Q(title__icontains=keyword) | Q(_id__icontains=keyword))
        if not user.can_mgmt_all_problem():
```

改成：

```python
        keyword = request.GET.get("keyword", "").strip()
        if keyword:
            problems = problems.filter(Q(title__icontains=keyword) | Q(_id__icontains=keyword))

        tag_id = request.GET.get("tag_id")
        if tag_id:
            problems = problems.filter(tags__id=tag_id)

        if not user.can_mgmt_all_problem():
```

- [ ] **Step 2: 跑 lint**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge && ruff check problem/views/admin.py && ruff format --check problem/views/admin.py
```

Expected: `All checks passed!` 且格式检查无输出报错。

- [ ] **Step 3: 用 Django shell 验证过滤能跑通**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge && python manage.py shell -c "
from problem.models import Problem, ProblemTag
t = ProblemTag.objects.first()
if t is None:
    print('库里没有标签，跳过')
else:
    n = Problem.objects.filter(contest_id__isnull=True, tags__id=t.id).count()
    print(f'标签 {t.name} (id={t.id}) 下有 {n} 道非比赛题')
"
```

Expected: 打印出标签名和题目数，没有异常。数字应与标签管理页显示的 `problem_count` 一致（该标签下若有比赛题则会偏小，属正常）。

- [ ] **Step 4: 提交**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge && git add problem/views/admin.py && git commit -m "feat: 后台题目列表支持按标签筛选"
```

---

### Task 2: 标签题目弹窗组件

**Files:**
- Modify: `ojnext/src/admin/api.ts:29-54`（`getProblemList`）
- Create: `ojnext/src/admin/problem/components/TagProblemsModal.vue`

**Interfaces:**
- Consumes: Task 1 的 `tag_id` 查询参数；已有的 `batchTagProblems(problemIds: number[], tagNames: string[], action: "add" | "remove")`
- Produces:
  - `getProblemList(offset?: number, limit?: number, keyword: string, author?: string, contestID?: string, tagId?: number)` — 新增第 6 个可选参数
  - `TagProblemsModal.vue` 组件，props `{ show: boolean; tagId: number; tagName: string }`，emits `{ "update:show": [value: boolean]; changed: [] }`

- [ ] **Step 1: 给 getProblemList 加 tagId 参数**

在 `ojnext/src/admin/api.ts` 把 `getProblemList` 整个函数替换为：

```ts
export async function getProblemList(
  offset = 0,
  limit = 10,
  keyword: string,
  author?: string,
  contestID?: string,
  tagId?: number,
) {
  const endpoint = !!contestID ? "admin/contest/problem" : "admin/problem"
  const res = await http.get<{ results: AdminProblem[]; total: number }>(
    endpoint,
    {
      params: {
        paging: true,
        offset,
        limit,
        keyword,
        author,
        contest_id: contestID,
        tag_id: tagId,
      },
    },
  )
  return {
    results: res.data.results.map(toProblemListItem),
    total: res.data.total,
  }
}
```

`tagId` 为 `undefined` 时 axios 会自动丢掉这个 query 参数，所以现有调用方（`list.vue`）不用改。

- [ ] **Step 2: 创建弹窗组件**

新建 `ojnext/src/admin/problem/components/TagProblemsModal.vue`，内容如下：

```vue
<script setup lang="ts">
import { NButton, NTag } from "naive-ui"
import Pagination from "shared/components/Pagination.vue"
import type { AdminProblemFiltered } from "utils/types"
import { batchTagProblems, getProblemList } from "admin/api"

interface Props {
  show: boolean
  tagId: number
  tagName: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  "update:show": [value: boolean]
  changed: []
}>()

const router = useRouter()
const message = useMessage()

const problems = ref<AdminProblemFiltered[]>([])
const total = ref(0)
const page = ref(1)
const limit = ref(10)
const keyword = ref("")

const columns: DataTableColumn<AdminProblemFiltered>[] = [
  { title: "显示编号", key: "_id", width: 100 },
  {
    title: "标题",
    key: "title",
    minWidth: 200,
    render: (row) =>
      h(
        NButton,
        { text: true, type: "primary", onClick: () => goEdit(row) },
        () => row.title,
      ),
  },
  {
    title: "可见",
    key: "visible",
    width: 80,
    render: (row) =>
      h(NTag, { size: "small", type: row.visible ? "success" : "default" }, () =>
        row.visible ? "公开" : "隐藏",
      ),
  },
  {
    title: "选项",
    key: "actions",
    width: 110,
    render: (row) =>
      h(
        NButton,
        { size: "small", type: "error", onClick: () => removeTag(row) },
        () => "移除标签",
      ),
  },
]

async function listProblems() {
  if (page.value < 1) page.value = 1
  const offset = (page.value - 1) * limit.value
  const res = await getProblemList(
    offset,
    limit.value,
    keyword.value,
    "",
    undefined,
    props.tagId,
  )
  problems.value = res.results
  total.value = res.total
}

function close() {
  emit("update:show", false)
}

function goEdit(row: AdminProblemFiltered) {
  close()
  router.push({ name: "admin problem edit", params: { problemID: row.id } })
}

async function removeTag(row: AdminProblemFiltered) {
  await batchTagProblems([row.id], [props.tagName], "remove")
  message.success(`已移除「${row.title}」的标签`)
  emit("changed")
  // 移掉本页最后一条时退回上一页，交给下面的 watcher 重新拉取
  if (problems.value.length === 1 && page.value > 1) {
    page.value -= 1
  } else {
    listProblems()
  }
}

// 改搜索词就回到第一页
watch(keyword, () => (page.value = 1))

// 每次打开弹窗重置状态，拉取交给下面的 watcher
watch(
  () => props.show,
  (show) => {
    if (!show) return
    page.value = 1
    keyword.value = ""
  },
)

// 打开 / 翻页 / 改每页条数 / 改搜索词都走这里，防抖把同一批变更合并成一次请求
watchDebounced(
  () => [props.show, props.tagId, page.value, limit.value, keyword.value],
  () => {
    if (!props.show) return
    listProblems()
  },
  { debounce: 300, maxWait: 800 },
)
</script>

<template>
  <n-modal
    :show="show"
    preset="card"
    :title="`标签「${tagName}」下的题目`"
    style="width: 720px"
    @close="close"
  >
    <n-flex vertical size="large">
      <n-flex justify="space-between" align="center">
        <span>共 {{ total }} 道题</span>
        <n-input
          v-model:value="keyword"
          style="width: 220px"
          placeholder="输入标题关键字"
          clearable
        />
      </n-flex>
      <n-data-table striped :columns="columns" :data="problems" />
      <Pagination :total="total" v-model:limit="limit" v-model:page="page" />
    </n-flex>
  </n-modal>
</template>
```

- [ ] **Step 3: 格式化并确认能构建**

```bash
cd /home/xuyue/Projects/OJ/ojnext && npm run fmt && npm run build
```

Expected: Prettier 无报错；`vite build` 成功结束（`built in ...`），没有 "Could not resolve" 之类的模块解析错误。

- [ ] **Step 4: 提交**

```bash
cd /home/xuyue/Projects/OJ/ojnext && git add src/admin/api.ts src/admin/problem/components/TagProblemsModal.vue && git commit -m "feat: 新增标签题目弹窗组件"
```

---

### Task 3: 标签管理页接入弹窗

**Files:**
- Modify: `ojnext/src/admin/problem/tags.vue`

**Interfaces:**
- Consumes: Task 2 的 `TagProblemsModal.vue`（props `show` / `tagId` / `tagName`，emits `update:show` / `changed`）
- Produces: 无（终端任务）

- [ ] **Step 1: 引入组件和弹窗状态**

在 `ojnext/src/admin/problem/tags.vue` 的 `<script setup>` 里，把顶部 import 和状态声明部分：

```ts
import { NButton, NFlex, NInput } from "naive-ui"
import type { AdminTag } from "utils/types"
import { deleteTag, getTagAdminList, renameTag } from "../api"

const message = useMessage()
const dialog = useDialog()

const tags = ref<AdminTag[]>([])
const keyword = ref("")
const editingId = ref<number | null>(null)
const editingName = ref("")
```

改成：

```ts
import { NButton, NFlex, NInput } from "naive-ui"
import type { AdminTag } from "utils/types"
import { deleteTag, getTagAdminList, renameTag } from "../api"
import TagProblemsModal from "./components/TagProblemsModal.vue"

const message = useMessage()
const dialog = useDialog()

const tags = ref<AdminTag[]>([])
const keyword = ref("")
const editingId = ref<number | null>(null)
const editingName = ref("")

const activeTag = ref<AdminTag | null>(null)
const [showTagProblems, toggleTagProblems] = useToggle(false)

function openTagProblems(tag: AdminTag) {
  activeTag.value = tag
  toggleTagProblems(true)
}
```

- [ ] **Step 2: 让标签名和题目数可点击**

把 `columns` 里的「标签名」列 render 的非编辑态分支（原来直接是 `row.name`）和「题目数」列改掉。两列替换后如下：

```ts
  {
    title: "标签名",
    key: "name",
    minWidth: 200,
    render: (row) =>
      editingId.value === row.id
        ? h(NInput, {
            value: editingName.value,
            autofocus: true,
            size: "small",
            style: "max-width: 240px",
            onUpdateValue: (v: string) => (editingName.value = v),
            onKeyup: (e: KeyboardEvent) => {
              if (e.key === "Enter") saveTag(row)
              if (e.key === "Escape") cancelEdit()
            },
          })
        : h(
            NButton,
            {
              text: true,
              type: "primary",
              onClick: () => openTagProblems(row),
            },
            () => row.name,
          ),
  },
  {
    title: "题目数",
    key: "problem_count",
    width: 100,
    render: (row) =>
      h(
        NButton,
        { text: true, type: "primary", onClick: () => openTagProblems(row) },
        () => String(row.problem_count),
      ),
  },
```

编辑态下标签名仍然是输入框，不可点击。

- [ ] **Step 3: 在模板里挂上弹窗**

把 `tags.vue` 模板末尾的 `<n-data-table ... />` 行：

```vue
  <n-data-table striped :columns="columns" :data="tags" />
```

改成：

```vue
  <n-data-table striped :columns="columns" :data="tags" />
  <TagProblemsModal
    v-model:show="showTagProblems"
    :tag-id="activeTag?.id ?? 0"
    :tag-name="activeTag?.name ?? ''"
    @changed="listTags"
  />
```

不要用 `v-if` 包这个组件：组件内部靠 `show` 从 `false` 变 `true` 触发拉取，`v-if` 挂载时 `show` 已经是 `true`，watcher 不会触发，弹窗会是空的。

- [ ] **Step 4: 格式化并确认能构建**

```bash
cd /home/xuyue/Projects/OJ/ojnext && npm run fmt && npm run build
```

Expected: Prettier 无报错；`vite build` 成功结束。

- [ ] **Step 5: 手动验证**

前置：后端在跑（`cd /home/xuyue/Projects/OJ/OnlineJudge && python dev.py`），前端在跑（`cd /home/xuyue/Projects/OJ/ojnext && npm start`），用超管账号登录。

打开 `http://localhost:5173/admin/problem/tags`，逐条确认：

1. 标签名和题目数都是蓝色可点的，点任一个都弹出「标签「X」下的题目」
2. 弹窗顶部「共 N 道题」的 N 与该行题目数一致
3. 表格里题目条数正确，超过 10 条时底部分页可翻页
4. 在弹窗搜索框输入标题关键字，列表过滤正确，且自动回到第 1 页
5. 点某道题标题 → 弹窗关闭并跳到该题编辑页；退回标签管理页
6. 点某道题「移除标签」→ 提示「已移除「X」的标签」，该题从弹窗列表消失，关掉弹窗后该行题目数减 1
7. 点「重命名」进入编辑态时，标签名变成输入框且点不动

- [ ] **Step 6: 提交**

```bash
cd /home/xuyue/Projects/OJ/ojnext && git add src/admin/problem/tags.vue && git commit -m "feat: 标签管理页点击标签查看对应题目"
```

---

## 备注

- 标签表的 `problem_count` 来自 `TagAdminAPI` 的全量 `Count("problem")`，弹窗走 `ProblemAdminAPI` 会按创建者过滤，非超管可能看到两个数字对不上。这是 spec 里明确记录的已知不一致，本次不处理。
- `problem_count` 为 0 的标签点开会是空列表，属预期。
