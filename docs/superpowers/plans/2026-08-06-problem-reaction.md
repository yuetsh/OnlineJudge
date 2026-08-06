# 题目点评重写（表情 Reaction）实现计划

> 2026-08-06 规则更新：当前实现已改为单选、点击即提交、提交后不可修改，并通过 `(problem, user)` 数据库唯一约束保证一人一题一条。新接口使用单值 `type` / `mine_type`；为支持前后端错序部署，过渡期仍接受单元素 `types` 并返回数组 `mine`。统计直接查询数据库，不再使用 reaction 缓存。本文中的多选及缓存步骤是早期实施记录。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把题目点评从「三维评分 + 文字」重写为「一排七个表情按钮，点击即表态」，并把后台从逐条评论管理改为按题目聚合的反馈统计表。

**Architecture:** 后端新建 `reaction` app 替换 `comment` app，一行一个表情（`unique(problem, user, type)`），写入用「整份覆盖」（事务内 delete + bulk_create）。用户接口一个 endpoint 同时返回「我点了什么」和「大家点了什么」，后者仅在前者非空时下发。后台统计用一条 ORM 查询完成聚合、按占比排序与分页。前端重写 `ProblemReaction.vue`，七个按钮始终一排，按容器宽度降级。

**Tech Stack:** Django 6 + DRF + PostgreSQL + Redis（后端）；Vue 3 + TypeScript + Naive UI + `@iconify/vue`（前端）

**设计文档：** `OnlineJudge/docs/superpowers/specs/2026-08-06-problem-reaction-design.md`

## Global Constraints

- **不要写测试。** 项目测试策略明确禁止，本计划所有任务均不含测试步骤。
- **本地无法运行后端。** 没有 Docker、PostgreSQL、Redis 与判题沙箱。`makemigrations` 可本地执行（不连库），`migrate` 只能在服务器执行。后端验证手段只有 `ruff check .` 和代码审查。
- **后端 lint 与格式化：** `ruff check .` 与 `ruff format .`，行宽 180，双引号。
- **前端验证手段：** `npm run build`（在 `ojnext/` 下）。无测试套件，格式化用 `npm fmt`。
- **错误响应用 `self.error(msg)`**，不要用 HTTP 400。项目基类统一返回 `{"error": "error", "data": msg}`，HTTP 状态码恒为 200。
- **前端自动导入已配置。** Vue API（`ref`/`computed`/`onMounted`/`watch`）、`storeToRefs`、VueUse、Naive UI 组件与 `useMessage` 等**不需要手写 import**。需要手写 import 的只有：`@iconify/vue` 的 `Icon`、项目内的 store / api / constants / types。
- **代码与数据库中不得出现 Unicode emoji 字面量。** 一律用语义 key + Iconify 图标名。文档和注释里可以用。
- **两个 git 仓库：** `OnlineJudge/`（当前分支 `yuetsh`）与 `ojnext/`（当前分支 `main`）。根目录不是仓库。各自独立提交。
- **前后端必须一起部署。** Task 7 删除 `comment` app 后，未更新的前端会调到不存在的接口。

**表情集合（七个，顺序固定）：**

| key | 中文标签 | Iconify 图标 |
|---|---|---|
| `too_easy` | 太简单 | `fluent-emoji:smiling-face-with-sunglasses` |
| `too_hard` | 太难了 | `fluent-emoji:exploding-head` |
| `confusing` | 没看懂 | `fluent-emoji:face-with-spiral-eyes` |
| `buggy` | 题目有错 | `fluent-emoji:bug` |
| `learned` | 学到了 | `fluent-emoji:light-bulb` |
| `interesting` | 有意思 | `fluent-emoji:star-struck` |
| `want_explain` | 想听讲解 | `fluent-emoji:books` |

**最多同时选 3 个。**

---

## 文件结构

**后端新建（`OnlineJudge/`）**

| 文件 | 职责 |
|---|---|
| `reaction/__init__.py` | 空 |
| `reaction/models.py` | `ReactionType` 枚举 + `Reaction` 模型 |
| `reaction/serializers.py` | `SetReactionSerializer`（POST 入参校验 + 去重限长） |
| `reaction/views/__init__.py` | 空 |
| `reaction/views/oj.py` | `ReactionAPI`（GET/POST），含统计缓存 |
| `reaction/views/admin.py` | `ReactionStatsAPI`（按题目聚合 + 占比排序） |
| `reaction/urls/__init__.py` | 空 |
| `reaction/urls/oj.py` | `/api/reaction` |
| `reaction/urls/admin.py` | `/api/admin/reaction` |
| `reaction/migrations/` | 由 `makemigrations` 生成 |

**后端修改**

| 文件 | 改动 |
|---|---|
| `oj/settings.py` | `LOCAL_APPS` 增删 |
| `oj/urls.py` | include 增删 |
| `utils/constants.py` | `CacheKey.comment_stats` → `reaction_stats` |

**后端删除：** `comment/` 整个目录

**前端新建（`ojnext/`）**

| 文件 | 职责 |
|---|---|
| `src/oj/problem/components/ProblemReaction.vue` | 学生端表情条 |
| `src/admin/communication/reactions.vue` | 后台反馈统计表 |

**前端修改**

| 文件 | 改动 |
|---|---|
| `src/utils/constants.ts` | 新增 `REACTIONS`、`MAX_REACTIONS` |
| `src/utils/types.ts` | 删 `Comment`，新增 reaction 相关类型 |
| `src/oj/api.ts` | 删三个 comment 函数，新增两个 reaction 函数 |
| `src/admin/api.ts` | 删两个 comment 函数，新增 `getReactionStats` |
| `src/oj/problem/detail.vue` | 三处组件引用 |
| `src/oj/problem/components/SubmitCode.vue` | 一处组件引用，去掉 `showStatistics` |
| `src/routes.ts` | 路由 `comment/list` → `reaction/list` |
| `src/shared/layout/admin.vue` | 菜单「评论」→「题目反馈」 |

**前端删除：** `src/oj/problem/components/ProblemComment.vue`、`src/admin/communication/comments.vue`、`src/admin/communication/components/CommentActions.vue`

---

## Task 1: 后端 reaction app 骨架与数据模型

建立 app 并生成迁移。此任务结束后 `comment` app 仍在正常工作，两者并存。

**Files:**
- Create: `OnlineJudge/reaction/__init__.py`
- Create: `OnlineJudge/reaction/models.py`
- Create: `OnlineJudge/reaction/serializers.py`
- Create: `OnlineJudge/reaction/views/__init__.py`
- Create: `OnlineJudge/reaction/urls/__init__.py`
- Modify: `OnlineJudge/oj/settings.py`（`LOCAL_APPS`）
- Modify: `OnlineJudge/utils/constants.py`（`CacheKey`）

**Interfaces:**
- Produces: `reaction.models.ReactionType`（TextChoices，七个成员）、`reaction.models.Reaction`（模型）、`reaction.serializers.SetReactionSerializer`、`utils.constants.CacheKey.reaction_stats`

- [ ] **Step 1: 创建 app 目录与空的 `__init__.py`**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
mkdir -p reaction/views reaction/urls
touch reaction/__init__.py reaction/views/__init__.py reaction/urls/__init__.py
```

- [ ] **Step 2: 写 `reaction/models.py`**

```python
from django.db import models

from account.models import User
from problem.models import Problem


class ReactionType(models.TextChoices):
    TOO_EASY = "too_easy", "太简单"
    TOO_HARD = "too_hard", "太难了"
    CONFUSING = "confusing", "没看懂"
    BUGGY = "buggy", "题目有错"
    LEARNED = "learned", "学到了"
    INTERESTING = "interesting", "有意思"
    WANT_EXPLAIN = "want_explain", "想听讲解"


class Reaction(models.Model):
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    type = models.CharField(max_length=20, choices=ReactionType.choices, verbose_name="表情类型")
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reaction"
        unique_together = ("problem", "user", "type")
        indexes = [
            models.Index(fields=["problem", "type"], name="reaction_problem_type_idx"),
        ]
```

- [ ] **Step 3: 写 `reaction/serializers.py`**

`types` 先去重再判长度，避免学生重复传同一个 key 绕过上限。

```python
from reaction.models import ReactionType
from utils.api import serializers

MAX_REACTIONS = 3


class SetReactionSerializer(serializers.Serializer):
    problem_id = serializers.IntegerField()
    types = serializers.ListField(
        child=serializers.ChoiceField(choices=ReactionType.choices),
        allow_empty=True,
    )

    def validate_types(self, value):
        unique = list(dict.fromkeys(value))
        if len(unique) > MAX_REACTIONS:
            raise serializers.ValidationError(f"最多只能选 {MAX_REACTIONS} 个")
        return unique
```

- [ ] **Step 4: 在 `oj/settings.py` 的 `LOCAL_APPS` 中注册**

在 `"comment",` 这一行**之后**加一行（此时两者并存）：

```python
    "comment",
    "reaction",
```

- [ ] **Step 5: 在 `utils/constants.py` 的 `CacheKey` 中加缓存键**

在 `comment_stats = "comment_stats"` 之后加一行：

```python
    comment_stats = "comment_stats"
    reaction_stats = "reaction_stats"
```

- [ ] **Step 6: 生成迁移**

Run: `cd /home/xuyue/Projects/OJ/OnlineJudge && python manage.py makemigrations reaction`
Expected: 输出 `Migrations for 'reaction':` 并创建 `reaction/migrations/0001_initial.py`。此命令不连数据库，本地可执行。

- [ ] **Step 7: 静态检查**

Run: `cd /home/xuyue/Projects/OJ/OnlineJudge && ruff format . && ruff check .`
Expected: `All checks passed!`

- [ ] **Step 8: 提交**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
git add reaction oj/settings.py utils/constants.py
git commit -m "feat(reaction): 新增 reaction app 与数据模型

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: 用户接口 `/api/reaction`

**Files:**
- Create: `OnlineJudge/reaction/views/oj.py`
- Create: `OnlineJudge/reaction/urls/oj.py`
- Modify: `OnlineJudge/oj/urls.py`

**Interfaces:**
- Consumes: Task 1 的 `Reaction`、`ReactionType`、`SetReactionSerializer`、`CacheKey.reaction_stats`
- Produces: `GET /api/reaction?problem_id=X` → `{"mine": ReactionKey[], "counts": Record<ReactionKey, number> | null}`；`POST /api/reaction {problem_id, types}` → 同结构

- [ ] **Step 1: 写 `reaction/views/oj.py`**

要点：
- `counts` 只在 `mine` 非空时计算并下发，这是「点完才显示」的服务端保障
- 写入用 `sync_to_async` 包一个同步函数，才能用 `transaction.atomic`（Django 的异步 ORM 不支持异步事务）。项目已有此用法，见 `contest/views/oj.py`
- AC 判定沿用旧 `CommentAPI.post`：`result` 属于 `ACCEPTED` 或 `AST_CHECK_FAILED`

```python
from asgiref.sync import sync_to_async
from django.db import transaction
from django.db.models import Count, Q

from account.decorators import login_required
from problem.models import Problem
from reaction.models import Reaction, ReactionType
from reaction.serializers import SetReactionSerializer
from submission.models import JudgeStatus, Submission
from utils.api import AsyncAPIView
from utils.api.api import validate_serializer
from utils.async_helpers import async_cache_delete, async_cache_get, async_cache_set
from utils.constants import CacheKey

ACCEPTED_RESULTS = [JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED]


class ReactionAPI(AsyncAPIView):
    async def get_counts(self, problem_id):
        """返回该题七个表情的计数，带 Redis 缓存。"""
        cache_key = f"{CacheKey.reaction_stats}:{problem_id}"
        cached = await async_cache_get(cache_key)
        if cached is not None:
            return cached
        counts = await Reaction.objects.filter(problem_id=problem_id).aaggregate(
            **{t.value: Count("id", filter=Q(type=t.value)) for t in ReactionType}
        )
        await async_cache_set(cache_key, counts, 3600)
        return counts

    @login_required
    async def get(self, request):
        problem_id = request.GET.get("problem_id")
        if not problem_id:
            return self.error("problem_id is required")
        mine = [r.type async for r in Reaction.objects.filter(user=request.user, problem_id=problem_id)]
        if not mine:
            return self.success({"mine": [], "counts": None})
        return self.success({"mine": mine, "counts": await self.get_counts(problem_id)})

    @login_required
    @validate_serializer(SetReactionSerializer)
    async def post(self, request):
        data = request.data
        try:
            problem = await Problem.objects.aget(id=data["problem_id"], visible=True)
        except Problem.DoesNotExist:
            return self.error("problem is not exists")

        solved = await Submission.objects.filter(
            user_id=request.user.id,
            problem_id=problem.id,
            result__in=ACCEPTED_RESULTS,
        ).aexists()
        if not solved:
            return self.error("submission is not exists or not accepted")

        types = data["types"]
        user = request.user

        def overwrite():
            with transaction.atomic():
                Reaction.objects.filter(user=user, problem=problem).delete()
                Reaction.objects.bulk_create([Reaction(user=user, problem=problem, type=t) for t in types])

        await sync_to_async(overwrite)()
        await async_cache_delete(f"{CacheKey.reaction_stats}:{problem.id}")

        if not types:
            return self.success({"mine": [], "counts": None})
        return self.success({"mine": types, "counts": await self.get_counts(problem.id)})
```

- [ ] **Step 2: 写 `reaction/urls/oj.py`**

```python
from django.urls import path

from ..views.oj import ReactionAPI

urlpatterns = [
    path("reaction", ReactionAPI.as_view()),
]
```

- [ ] **Step 3: 在 `oj/urls.py` 注册路由**

在 `path("api/", include("comment.urls.oj")),` 这一行**之前**插入：

```python
    path("api/", include("reaction.urls.oj")),
```

- [ ] **Step 4: 静态检查**

Run: `cd /home/xuyue/Projects/OJ/OnlineJudge && ruff format . && ruff check .`
Expected: `All checks passed!`

- [ ] **Step 5: 提交**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
git add reaction oj/urls.py
git commit -m "feat(reaction): 用户端表情接口

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: 管理接口 `/api/admin/reaction`

**Files:**
- Create: `OnlineJudge/reaction/views/admin.py`
- Create: `OnlineJudge/reaction/urls/admin.py`
- Modify: `OnlineJudge/oj/urls.py`

**Interfaces:**
- Consumes: Task 1 的 `Reaction`、`ReactionType`
- Produces: `GET /api/admin/reaction?problem=&ordering=&offset=&limit=` → 分页结构 `{"results": [...], "total": n}`，每行字段：`pid`（题目序号）、`title`、`users`、七个表情计数、七个 `<key>_ratio`

- [ ] **Step 1: 写 `reaction/views/admin.py`**

要点：
- `values(pid=..., title=...)` 用别名，避免前端拿到 `problem___id` 这种键名
- 表情列按**占比**排序，并过滤掉表态人数 < 3 的题；`users` 列按数量排序，不加过滤
- `ordering` 传非法值时静默回落到 `-users`，不报错
- `users` 是 `Count("user", distinct=True)`，分组内至少有一行，恒 ≥ 1，不会除零
- 七个 `_ratio` 注解会一并出现在返回的字典里，前端忽略即可，无需额外裁剪

```python
from django.db.models import Count, F, FloatField, Q
from django.db.models.functions import Cast

from account.decorators import super_admin_required
from reaction.models import Reaction, ReactionType
from utils.api import APIView

MIN_USERS_FOR_RATIO = 3
DEFAULT_ORDERING = "-users"


class ReactionStatsAPI(APIView):
    @super_admin_required
    def get(self, request):
        queryset = (
            Reaction.objects.values(pid=F("problem___id"), title=F("problem__title"))
            .annotate(users=Count("user", distinct=True))
            .annotate(**{t.value: Count("id", filter=Q(type=t.value)) for t in ReactionType})
            .annotate(
                **{
                    f"{t.value}_ratio": Cast(t.value, FloatField()) / Cast("users", FloatField())
                    for t in ReactionType
                }
            )
        )

        problem_id = request.GET.get("problem")
        if problem_id:
            queryset = queryset.filter(problem___id__iexact=problem_id, problem__contest_id__isnull=True)

        ordering = request.GET.get("ordering") or DEFAULT_ORDERING
        prefix = "-" if ordering.startswith("-") else ""
        field = ordering.lstrip("-")
        if field == "users":
            order_by = f"{prefix}users"
        elif field in ReactionType.values:
            # 按占比排序时过滤低样本，避免 1 人点 1 个就冲到 100%
            queryset = queryset.filter(users__gte=MIN_USERS_FOR_RATIO)
            order_by = f"{prefix}{field}_ratio"
        else:
            order_by = DEFAULT_ORDERING

        queryset = queryset.order_by(order_by)
        return self.success(self.paginate_data(request, queryset))
```

- [ ] **Step 2: 写 `reaction/urls/admin.py`**

```python
from django.urls import path

from ..views.admin import ReactionStatsAPI

urlpatterns = [
    path("reaction", ReactionStatsAPI.as_view()),
]
```

- [ ] **Step 3: 在 `oj/urls.py` 注册路由**

在 Task 2 加的那行**之后**插入：

```python
    path("api/admin/", include("reaction.urls.admin")),
```

- [ ] **Step 4: 静态检查**

Run: `cd /home/xuyue/Projects/OJ/OnlineJudge && ruff format . && ruff check .`
Expected: `All checks passed!`

- [ ] **Step 5: 提交**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
git add reaction oj/urls.py
git commit -m "feat(reaction): 后台表情统计接口

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: 前端常量、类型与 API 层

**Files:**
- Modify: `ojnext/src/utils/types.ts`
- Modify: `ojnext/src/utils/constants.ts`
- Modify: `ojnext/src/oj/api.ts`
- Modify: `ojnext/src/admin/api.ts`

**Interfaces:**
- Consumes: Task 2 与 Task 3 的接口契约
- Produces: `ReactionKey`、`ReactionCounts`、`ReactionState`、`ReactionStatsRow` 类型；`REACTIONS`、`MAX_REACTIONS` 常量；`getReaction`、`setReaction`、`getReactionStats` 函数

- [ ] **Step 1: 在 `src/utils/types.ts` 中新增 reaction 类型**

在原 `Comment` 接口（约 597 行）**之后**追加。此时先不删 `Comment`，Task 7 统一清理。

```ts
export type ReactionKey =
  | "too_easy"
  | "too_hard"
  | "confusing"
  | "buggy"
  | "learned"
  | "interesting"
  | "want_explain"

export type ReactionCounts = Record<ReactionKey, number>

export interface ReactionState {
  mine: ReactionKey[]
  counts: ReactionCounts | null
}

export interface ReactionStatsRow extends ReactionCounts {
  pid: string
  title: string
  users: number
}
```

- [ ] **Step 2: 在 `src/utils/constants.ts` 末尾新增常量**

顺序即按钮渲染顺序，不要改动。与后端 `ReactionType` 必须同步。

```ts
import type { ReactionKey } from "utils/types"

export const REACTIONS: {
  key: ReactionKey
  label: string
  icon: string
}[] = [
  {
    key: "too_easy",
    label: "太简单",
    icon: "fluent-emoji:smiling-face-with-sunglasses",
  },
  { key: "too_hard", label: "太难了", icon: "fluent-emoji:exploding-head" },
  {
    key: "confusing",
    label: "没看懂",
    icon: "fluent-emoji:face-with-spiral-eyes",
  },
  { key: "buggy", label: "题目有错", icon: "fluent-emoji:bug" },
  { key: "learned", label: "学到了", icon: "fluent-emoji:light-bulb" },
  { key: "interesting", label: "有意思", icon: "fluent-emoji:star-struck" },
  { key: "want_explain", label: "想听讲解", icon: "fluent-emoji:books" },
]

export const MAX_REACTIONS = 3
```

注意：`import type` 语句要放到文件顶部已有的 import 区域，不要留在文件中间。

- [ ] **Step 3: 在 `src/oj/api.ts` 新增两个函数**

放在原 `getCommentStatistics` 之后。旧的三个 comment 函数此时先保留，Task 7 统一删除。

```ts
export function getReaction(problemID: number) {
  return http.get("reaction", { params: { problem_id: problemID } })
}

export function setReaction(problemID: number, types: ReactionKey[]) {
  return http.post("reaction", { problem_id: problemID, types })
}
```

`ReactionKey` 需要在该文件顶部的 type import 中补上，参照文件已有的 `import type { ... } from "utils/types"` 写法。

- [ ] **Step 4: 在 `src/admin/api.ts` 新增统计函数**

放在原 `deleteComment` 之后。

```ts
export function getReactionStats(
  offset = 0,
  limit = 10,
  problem: string,
  ordering: string,
) {
  return http.get("admin/reaction", {
    params: { offset, limit, problem, ordering },
  })
}
```

- [ ] **Step 5: 格式化并验证编译**

Run: `cd /home/xuyue/Projects/OJ/ojnext && npm fmt && npm run build`
Expected: 构建成功，无 TypeScript 报错。

- [ ] **Step 6: 提交**

```bash
cd /home/xuyue/Projects/OJ/ojnext
git add src/utils/types.ts src/utils/constants.ts src/oj/api.ts src/admin/api.ts
git commit -m "feat(reaction): 前端表情常量、类型与 API

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: 学生端表情条组件

**Files:**
- Create: `ojnext/src/oj/problem/components/ProblemReaction.vue`
- Modify: `ojnext/src/oj/problem/detail.vue`（三处引用）
- Modify: `ojnext/src/oj/problem/components/SubmitCode.vue`（一处引用 + 去掉 prop）

**Interfaces:**
- Consumes: Task 4 的 `REACTIONS`、`MAX_REACTIONS`、`getReaction`、`setReaction`、`ReactionKey`、`ReactionCounts`
- Produces: `ProblemReaction.vue` 组件，无 props

- [ ] **Step 1: 创建 `src/oj/problem/components/ProblemReaction.vue`**

关键实现点：
- 用 `useElementSize` 监听**容器**宽度决定是否显示中文标签。不要用 `useBreakpoints`——那是视口宽度，检测不到分屏把容器压窄的情况。`ResizeObserver` 在 Chrome 64+ 可用，机房老机器没问题
- `flex-wrap: nowrap` + `overflow-x: auto`，七个按钮永不换行
- 乐观更新：先改本地状态再发请求，失败回滚
- 已选满 3 个时，未选中的按钮置灰；已选中的仍可点以取消

```vue
<template>
  <n-alert v-if="!userStore.isAuthed" type="error" title="请先登录" />
  <div v-else ref="container" class="reactions">
    <n-tooltip v-for="item in REACTIONS" :key="item.key" trigger="hover">
      <template #trigger>
        <n-button
          size="small"
          :disabled="isDisabled(item.key)"
          :type="mine.includes(item.key) ? 'primary' : 'default'"
          :ghost="mine.includes(item.key)"
          @click="toggle(item.key)"
        >
          <Icon :icon="item.icon" :width="18" />
          <span v-if="showLabel" class="label">{{ item.label }}</span>
          <span v-if="counts" class="count">{{ counts[item.key] }}</span>
        </n-button>
      </template>
      {{ tooltipOf(item.key, item.label) }}
    </n-tooltip>
  </div>
</template>

<script lang="ts" setup>
import { Icon } from "@iconify/vue"
import { storeToRefs } from "pinia"
import { getReaction, setReaction } from "oj/api"
import { useProblemStore } from "oj/store/problem"
import { useUserStore } from "shared/store/user"
import { MAX_REACTIONS, REACTIONS } from "utils/constants"
import type { ReactionCounts, ReactionKey } from "utils/types"

const userStore = useUserStore()
const problemStore = useProblemStore()
const { problem } = storeToRefs(problemStore)
const message = useMessage()

const container = ref<HTMLElement | null>(null)
const { width } = useElementSize(container)
// 七个按钮带中文标签大约需要 560px，放不下就只留图标和计数
const showLabel = computed(() => width.value >= 560)

const mine = ref<ReactionKey[]>([])
const counts = ref<ReactionCounts | null>(null)

const solved = computed(() => problem.value?.my_status === 0)

function isDisabled(key: ReactionKey) {
  if (!solved.value) return true
  if (mine.value.includes(key)) return false
  return mine.value.length >= MAX_REACTIONS
}

function tooltipOf(key: ReactionKey, label: string) {
  if (!solved.value) return "完成本题后可以评价"
  if (isDisabled(key)) return `最多选 ${MAX_REACTIONS} 个，先取消一个`
  if (counts.value) return `${counts.value[key]} 人选了「${label}」`
  return label
}

async function toggle(key: ReactionKey) {
  if (!problem.value) return
  const prevMine = [...mine.value]
  const prevCounts = counts.value ? { ...counts.value } : null
  const selected = mine.value.includes(key)
  const next = selected
    ? mine.value.filter((k) => k !== key)
    : [...mine.value, key]

  mine.value = next
  if (counts.value) counts.value[key] += selected ? -1 : 1

  try {
    const res = await setReaction(problem.value.id, next)
    mine.value = res.data.mine
    counts.value = res.data.counts
  } catch {
    mine.value = prevMine
    counts.value = prevCounts
    message.error("操作失败，请重试")
  }
}

async function load() {
  if (!problem.value) return
  const res = await getReaction(problem.value.id)
  mine.value = res.data.mine
  counts.value = res.data.counts
}

onMounted(() => {
  if (userStore.isAuthed) load()
})
</script>

<style scoped>
.reactions {
  display: flex;
  flex-wrap: nowrap;
  gap: 8px;
  overflow-x: auto;
}
.label {
  margin-left: 4px;
}
.count {
  margin-left: 6px;
  opacity: 0.7;
}
</style>
```

- [ ] **Step 2: 替换 `detail.vue` 中的三处引用**

把顶部的异步组件声明（约 26–28 行）改为：

```ts
const ProblemReaction = defineAsyncComponent(
  () => import("./components/ProblemReaction.vue"),
)
```

再把模板中三处 `<ProblemComment />` 全部改成 `<ProblemReaction />`。

Run 确认改干净：`cd /home/xuyue/Projects/OJ/ojnext && grep -n "ProblemComment" src/oj/problem/detail.vue`
Expected: 无输出

- [ ] **Step 3: 替换 `SubmitCode.vue` 中的一处引用**

把顶部异步组件声明（约 26–28 行）改为：

```ts
const ProblemReaction = defineAsyncComponent(
  () => import("./ProblemReaction.vue"),
)
```

把 `<ProblemComment :showStatistics="false" />` 改为 `<ProblemReaction />`——**`showStatistics` prop 已删除，不要保留**。

Run 确认：`cd /home/xuyue/Projects/OJ/ojnext && grep -rn "ProblemComment\|showStatistics" src/`
Expected: 只剩 `src/oj/problem/components/ProblemComment.vue` 文件自身（Task 7 删除）

- [ ] **Step 4: 格式化并验证编译**

Run: `cd /home/xuyue/Projects/OJ/ojnext && npm fmt && npm run build`
Expected: 构建成功

- [ ] **Step 5: 提交**

```bash
cd /home/xuyue/Projects/OJ/ojnext
git add src/oj/problem
git commit -m "feat(reaction): 学生端表情条组件

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: 后台反馈统计页

**Files:**
- Create: `ojnext/src/admin/communication/reactions.vue`
- Modify: `ojnext/src/routes.ts`
- Modify: `ojnext/src/shared/layout/admin.vue`

**Interfaces:**
- Consumes: Task 4 的 `getReactionStats`、`REACTIONS`、`ReactionStatsRow`
- Produces: 路由 `admin reaction list`（路径 `/admin/reaction/list`）

- [ ] **Step 1: 创建 `src/admin/communication/reactions.vue`**

要点：
- 七个表情列与「表态人数」列都开 `sorter: true`，走**服务端排序**，用 `@update:sorter` 回填 `query.ordering`
- 表头用图标 + 文字，不要只放图标
- 无删除操作

```vue
<template>
  <n-flex justify="space-between" class="titleWrapper">
    <h2 class="title">题目反馈统计</h2>
    <div>
      <n-input
        v-model:value="query.problem"
        clearable
        placeholder="输入题目序号"
      />
    </div>
  </n-flex>
  <n-data-table
    striped
    :columns="columns"
    :data="rows"
    :scroll-x="1100"
    remote
    @update:sorter="handleSorter"
  />
  <Pagination
    :total="total"
    v-model:limit="query.limit"
    v-model:page="query.page"
  />
</template>

<script lang="ts" setup>
import { Icon } from "@iconify/vue"
import { NButton, NFlex } from "naive-ui"
import Pagination from "shared/components/Pagination.vue"
import { REACTIONS } from "utils/constants"
import type { ReactionStatsRow } from "utils/types"
import { getReactionStats } from "../api"

const rows = ref<ReactionStatsRow[]>([])
const total = ref(0)
const query = reactive({
  limit: 10,
  page: 1,
  problem: "",
  ordering: "-users",
})

const columns: DataTableColumn<ReactionStatsRow>[] = [
  {
    title: "题目",
    key: "pid",
    width: 100,
    fixed: "left",
    render: (row) =>
      h(
        NButton,
        {
          text: true,
          type: "info",
          onClick: () => window.open("/problem/" + row.pid, "_blank"),
        },
        () => row.pid,
      ),
  },
  { title: "标题", key: "title", minWidth: 180, ellipsis: true },
  { title: "表态人数", key: "users", width: 110, sorter: true },
  ...REACTIONS.map((item) => ({
    title: () =>
      h(NFlex, { align: "center", size: 4, wrap: false }, () => [
        h(Icon, { icon: item.icon, width: 18 }),
        item.label,
      ]),
    key: item.key,
    width: 110,
    sorter: true,
  })),
]

function handleSorter(sorter: { columnKey: string; order: string | false }) {
  if (!sorter || !sorter.order) {
    query.ordering = "-users"
  } else {
    query.ordering =
      (sorter.order === "descend" ? "-" : "") + String(sorter.columnKey)
  }
  query.page = 1
  listStats()
}

async function listStats() {
  const offset = (query.page - 1) * query.limit
  const res = await getReactionStats(
    offset,
    query.limit,
    query.problem,
    query.ordering,
  )
  rows.value = res.data.results
  total.value = res.data.total
}

onMounted(listStats)
watch(() => [query.page, query.limit], listStats)
watchDebounced(() => query.problem, listStats, {
  debounce: 500,
  maxWait: 1000,
})
</script>

<style scoped>
.titleWrapper {
  margin-bottom: 16px;
}

.title {
  margin: 0;
}
</style>
```

- [ ] **Step 2: 在 `src/routes.ts` 中替换路由**

把 `comment/list` 那一条（约 260–264 行）整体改为：

```ts
    {
      path: "reaction/list",
      name: "admin reaction list",
      component: () => import("admin/communication/reactions.vue"),
      meta: { requiresSuperAdmin: true },
    },
```

- [ ] **Step 3: 在 `src/shared/layout/admin.vue` 中替换菜单项**

把「评论」那一项（约 117–125 行）整体改为：

```ts
      {
        label: () =>
          h(
            RouterLink,
            { to: "/admin/reaction/list" },
            { default: () => "题目反馈" },
          ),
        key: "admin reaction list",
      },
```

- [ ] **Step 4: 格式化并验证编译**

Run: `cd /home/xuyue/Projects/OJ/ojnext && npm fmt && npm run build`
Expected: 构建成功

- [ ] **Step 5: 提交**

```bash
cd /home/xuyue/Projects/OJ/ojnext
git add src/admin src/routes.ts src/shared/layout/admin.vue
git commit -m "feat(reaction): 后台题目反馈统计页

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: 下线 comment，清理残留

新功能已全部就位，此任务只做删除与文档。**这是前后端不兼容的分界点**，部署时两个仓库必须一起上。

**Files:**
- Delete: `OnlineJudge/comment/`（整个目录）
- Modify: `OnlineJudge/oj/settings.py`、`OnlineJudge/oj/urls.py`、`OnlineJudge/utils/constants.py`
- Create: `OnlineJudge/reaction/migrations/0002_delete_comment.py`（由 `makemigrations` 生成，文件名以实际为准）
- Delete: `ojnext/src/oj/problem/components/ProblemComment.vue`
- Delete: `ojnext/src/admin/communication/comments.vue`
- Delete: `ojnext/src/admin/communication/components/CommentActions.vue`
- Modify: `ojnext/src/utils/types.ts`、`ojnext/src/oj/api.ts`、`ojnext/src/admin/api.ts`
- Modify: `CLAUDE.md`（仓库根目录）

- [ ] **Step 1: 从 `oj/settings.py` 移除 `"comment",`**

`LOCAL_APPS` 中只保留 `"reaction",`。

- [ ] **Step 2: 从 `oj/urls.py` 移除两条 comment include**

删除 `path("api/", include("comment.urls.oj")),` 与 `path("api/admin/", include("comment.urls.admin")),`。

- [ ] **Step 3: 从 `utils/constants.py` 的 `CacheKey` 移除 `comment_stats`**

只保留 `reaction_stats = "reaction_stats"`。

- [ ] **Step 4: 生成删表迁移**

先删除 app 目录，再生成迁移：

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
git rm -r comment
python manage.py makemigrations
```

Expected: 生成一条包含 `DeleteModel(name="Comment")` 的迁移。若 Django 因 app 已移除而不生成，则手写迁移，放在 `reaction/migrations/` 下：

```python
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("reaction", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS comment CASCADE;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
```

同时需要清理 `django_migrations` 表中 comment app 的记录，这一步在服务器上执行：

```sql
DELETE FROM django_migrations WHERE app = 'comment';
```

把这条 SQL 写进本任务的服务器验证清单，不要遗漏。

- [ ] **Step 5: 后端静态检查并确认无残留引用**

Run: `cd /home/xuyue/Projects/OJ/OnlineJudge && ruff format . && ruff check . && grep -rn "comment" --include=*.py . --exclude-dir=.venv --exclude-dir=migrations | grep -v flowchart`
Expected: `All checks passed!`，且 grep 无输出（`flowchart` 里的 `comment` 是 AI 评语字段，与本功能无关，已排除）

- [ ] **Step 6: 提交后端**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
git add -A
git commit -m "refactor(reaction): 下线 comment app

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

- [ ] **Step 7: 删除前端旧文件**

```bash
cd /home/xuyue/Projects/OJ/ojnext
git rm src/oj/problem/components/ProblemComment.vue \
       src/admin/communication/comments.vue \
       src/admin/communication/components/CommentActions.vue
```

- [ ] **Step 8: 清理前端旧代码**

- `src/utils/types.ts`：删除 `Comment` 接口（约 597–607 行）
- `src/oj/api.ts`：删除 `createComment`、`getComment`、`getCommentStatistics`
- `src/admin/api.ts`：删除 `getCommentList`、`deleteComment`

Run 确认：`cd /home/xuyue/Projects/OJ/ojnext && grep -rni "comment" src/ | grep -v SubmitFlowchart`
Expected: 无输出（`SubmitFlowchart.vue` 里的 `comment` 是流程图 AI 评语字段，与本功能无关）

- [ ] **Step 9: 在根 `CLAUDE.md` 记录跨端同步项**

在 `## Cross-Project Concerns` 一节中，紧跟 **Judge status codes** 那条之后加入：

```markdown
- **题目表情 reaction** 的语义 key 必须在 `reaction/models.py`（后端 `ReactionType`）和 `ojnext/src/utils/constants.ts`（前端 `REACTIONS`）之间保持一致。改一边必须改另一边。
```

- [ ] **Step 10: 前端格式化并验证编译**

Run: `cd /home/xuyue/Projects/OJ/ojnext && npm fmt && npm run build`
Expected: 构建成功

- [ ] **Step 11: 提交前端**

```bash
cd /home/xuyue/Projects/OJ/ojnext
git add -A
git commit -m "refactor(reaction): 清理旧的评论代码

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## 服务器验证清单

本地无法运行后端，以下必须在服务器上人工确认。

**部署前**

- [ ] 两个仓库的改动一起部署，不可只上一边

**数据库**

- [ ] `python manage.py migrate` 成功，`reaction` 表已建，`comment` 表已删
- [ ] 执行 `DELETE FROM django_migrations WHERE app = 'comment';` 清理迁移记录

**学生端**

- [ ] 未登录访问题目详情：表情条置灰，提示「请先登录」
- [ ] 已登录但未 AC：表情条置灰，提示「完成本题后可以评价」，且**看不到任何计数**
- [ ] AC 后首次进入：七个按钮可点，**不显示数字**
- [ ] 点第一个表情后：整排出现计数，自己点的高亮
- [ ] 选满 3 个后：其余按钮置灰，tooltip 提示「最多选 3 个，先取消一个」；已选中的仍可点击取消
- [ ] 全部取消后：计数重新隐藏
- [ ] 刷新页面后状态保持
- [ ] 分屏模式（`SubmitCode.vue` 内）：七个按钮**一排不换行**，标签自动隐藏只剩图标 + 计数
- [ ] 机房老 Chrome（<94）上图标正常显示，无豆腐块

**后台**

- [ ] `/admin/reaction/list` 可访问，菜单显示「题目反馈」
- [ ] 表格显示题目、标题、表态人数与七个表情计数
- [ ] 点「没看懂」列降序：排在最上面的是该表情占比最高的题，且表态人数 < 3 的题不出现
- [ ] 点「表态人数」列降序：按人数排，低样本的题正常出现
- [ ] 按题目序号筛选可用
- [ ] 分页可用

---

## 执行后遗留项

实现全部完成并通过终审。以下是评审过程中判定「可以带着合并」的次要项，都不阻塞上线，记在这里免得日后重新发现一遍。

**后端**

- `problem_id` 传非数字（如 `?problem_id=abc`）会走兜底 except 返回泛化 500 并打一条 stack trace。前端始终传数字，实际影响只是日志噪音。与原 `comment/views/oj.py` 的写法一致。
- 同一用户并发双 POST 时，两个事务块可能交错撞上 `unique(problem, user, type)`，表现为一次「操作失败，请重试」的提示。状态最终仍会收敛，不会写坏数据。真要消掉的话，`bulk_create(..., ignore_conflicts=True)` 一处即可。
- 后台 `problem` 筛选传了不存在的题号时返回空结果，而不是像旧接口那样报「Problem doesn't exist」。老师打错题号时分不清「打错了」还是「还没人评」。
- 统计缓存是「先写库、后删缓存」，两人并发表态时快照可能少算一票，最长持续到 1 小时 TTL 过期。是计数误差，不值得为它加锁。

**前端**

- `ReactionStatsRow` 不含后端返回的七个 `_ratio` 字段。经核实前端确实不消费它们（列显示计数，排序走服务端），这是刻意保持现状的决定。
- 三个 API 函数没用 `http.get<T>` 泛型，`res.data` 是 `any`。顺带一提 `ReactionState` 类型目前无人引用，加上泛型就能把它用起来。
- `ProblemReaction.vue` 没有 `watch(problem.id)`，`load()` 也没有请求序号守卫。当前都不可达（tab 切换会销毁重建组件，`load()` 只在挂载时调用），但将来若加「下一题」这类同页切题功能，需要一并处理。
- 未登录时显示的是 `n-alert「请先登录」`，而非设计文档写的「灰色按钮排 + 提示」。沿用了旧组件的行为。
- 后台筛选框输入不重置页码，在第 3 页筛选可能落到空页。与原 `comments.vue` 行为一致。
- 后台 `listStats` 无请求序号守卫；`:scroll-x="1100"` 略小于实际列宽合计约 1160。
- `utils/permissions.ts` 的 `checkRoutePermission()` 全仓库无调用方，属既有死代码。实际权限由路由 meta 的 `requiresSuperAdmin` 把关，工作正常。

## Self-Review 记录

**Spec 覆盖检查：** 七个表情（Task 1/4）、最多选 3（Task 1 服务端 + Task 5 前端）、必须 AC（Task 2）、计数服务端把关（Task 2）、一行一个表情 + 唯一约束（Task 1）、整份覆盖写入（Task 2）、缓存与失效（Task 2）、占比排序 + 低样本过滤（Task 3）、四处挂载点 + 删 prop（Task 5）、一排不换行 + 降级（Task 5）、后台统计页 + 服务端排序（Task 6）、删除 comment + 老数据丢弃（Task 7）、跨端同步文档（Task 7）。无遗漏。

**与 spec 的三处有意偏离：**

1. **`self.error()` 而非 HTTP 400。** Spec 写「返回 400」，但项目基类 `APIView` 统一返回 `{"error": ..., "data": ...}`，HTTP 状态码恒 200。按项目约定落地。
2. **窄屏判断用 `useElementSize` 而非 `useBreakpoints`。** Spec 指定了 `shared/composables/breakpoints`，但它基于**视口**宽度，而分屏模式是**容器**被压窄，视口没变——用它检测不到。改用 `ResizeObserver`（Chrome 64+ 支持，老机器无碍）。
3. **admin 接口字段起别名。** 直接 `values("problem___id")` 会让前端拿到 `problem___id` 这种键名，改为 `values(pid=F("problem___id"), title=F("problem__title"))`。同时补了 `title` 列，spec 的表格里没画但有了更好用。

**类型一致性：** `ReactionKey` 在 types.ts 定义，constants.ts、api.ts、两个组件统一引用；后端 `ReactionType.values` 与前端 `REACTIONS` 的 key 集合逐一比对一致。`getReactionStats` 的四个参数顺序与 Task 6 调用处一致。
