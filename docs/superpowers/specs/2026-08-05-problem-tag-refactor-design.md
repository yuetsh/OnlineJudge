# 题目标签（ProblemTag）重构设计

日期：2026-08-05

## 背景

`ProblemTag` 自项目初始化以来从未演进：只有一个 `name TextField`，无唯一约束，标签全靠管理员在编辑题目时顺手输入创建（`ProblemAPI.post/put`、`ContestProblemAPI.post/put` 四处各自复制一份 get-or-create 逻辑）。没有专门的标签管理入口，无法重命名/合并/删除，也没有批量给多道题打标签的能力。

本次重构目标：**让 tag 成为后台管理题目的抓手**——具体是标签集中管理（增删改/合并）+ 批量给多道题打标签/移除标签。不涉及标签分类/分组、不改学生端筛选（仍单选）、不涉及 `Contest.tag`（无关的单独字段）。

## 目标 / 非目标

**目标**
1. 标签名规范化：去首尾空格 + 大小写不敏感唯一，消除并防止重复标签
2. 迁移现有脏数据：一次性脚本合并已存在的重复标签
3. 收敛四处重复的 get-or-create 逻辑为一个共享方法
4. 新增标签管理后台页面：列表（含关联题目数、搜索）、重命名（撞名自动合并）、删除（二次确认+影响题数提示）
5. 普通题目后台列表新增批量打标签/移除标签能力
6. 标签相关操作后主动失效 `problem/tags` 缓存

**非目标**
- 标签分类/分组/层级
- 学生端多标签筛选（保持现状单选）
- 竞赛题目列表的批量打标签入口（本次不做）
- `Contest.tag` 字段（设计完全无关，不在本次范围）

## 数据模型

`OnlineJudge/problem/models.py` 中 `ProblemTag`：

- `name` 保存前 `strip()`
- 新增大小写不敏感唯一约束：`models.UniqueConstraint(Lower("name"), name="problem_tag_name_ci_unique")`（Django `functions.Lower`，Postgres 原生支持函数索引）

新增数据迁移（migration）：
1. **数据清理**（`RunPython`，在加约束之前跑）：按 `strip().lower()` 分组现有 `ProblemTag`；每组内保留关联题目数最多的一个作为主标签（并列时保留 `id` 最小的），其余标签的 `problem_problem_tags` 关系全部改指向主标签（去重，避免同一题目对同一标签出现两条关系），再删除多余标签行。
2. **加约束**：`AddConstraint`。

## 后端 API

### 1. 共享标签解析方法

新增 `OnlineJudge/problem/services.py`（或就近放在 `problem/utils.py`）：

```python
def resolve_tags(names: list[str]) -> list[ProblemTag]:
    """按 strip + 大小写不敏感解析/创建标签，供题目创建/编辑复用"""
```

替换以下四处内联的 get-or-create 代码，改为调用 `resolve_tags`：
- `problem/views/admin.py` `ProblemAPI.post`
- `problem/views/admin.py` `ProblemAPI.put`
- `problem/views/admin.py` `ContestProblemAPI.post`
- `problem/views/admin.py` `ContestProblemAPI.put`

### 2. 标签管理 CRUD API（新增，仅 admin）

新增 `TagAdminAPI`（挂到 `problem/urls/admin.py`，如 `problem/tag`）：

- `GET ?keyword=`：返回全部标签（不再过滤 `problem_count__gt=0`，管理端需要看到未使用的标签），字段 `id, name, problem_count`，按 `problem_count` 降序或按名字排序，支持 `keyword` icontains 搜索
- `PUT`（传 `id`, `name`）：重命名。保存前 strip；若新名字（大小写不敏感）与另一已存在标签冲突：
  - 将当前标签下的题目关系全部转移到目标已存在标签（去重）
  - 删除当前标签
  - 返回 `{merged: true, into: {id, name}, affected_count: N}`
  - 若不冲突，直接改名，返回 `{merged: false}`
- `DELETE`（传 `id`）：返回受影响题目数供前端二次确认；真正执行删除时解除所有题目关联后删除标签行

删除的二次确认在前端完成（后端 `DELETE` 直接执行，前端弹窗提前用 `GET` 返回的 `problem_count` 展示提示，用户确认后再调用 `DELETE`）。

### 3. 批量打标签 API（新增，仅 admin）

新增 `BatchProblemTagAPI`（挂到 `problem/urls/admin.py`，如 `problem/batch_tag`）：

- `POST`：入参 `problem_ids: number[]`, `tag_names: string[]`（复用 `resolve_tags` 规范化/创建）, `action: "add" | "remove"`
- 逐个 `Problem` 对其 `tags` 关系执行 `add`/`remove`
- 权限沿用现有 admin 题目管理权限（`ProblemAPI` 同级）

### 4. 已有 `ProblemTagAPI`（OJ 端，学生使用）不变

保留 `problem_count__gt=0` 过滤和 1 小时缓存，供学生端筛选栏使用。

### 5. 缓存失效

`CacheKey.problem_tags` 缓存在以下操作后需要清除：
- `resolve_tags` 创建了新标签时
- `TagAdminAPI` 的重命名（含合并）、删除
- `BatchProblemTagAPI` 的批量操作

统一放在 `resolve_tags` 内部（创建新标签时清缓存）和 `TagAdminAPI`/`BatchProblemTagAPI` 的写操作末尾各自清一次，避免遗漏。

## 前端

### 1. 类型 / API（`ojnext/src/utils/types.ts`, `ojnext/src/shared/api.ts`）

- `Tag` 类型增加 `problem_count: number`
- 新增 API 封装：`getTagAdminList`、`renameTag`、`deleteTag`、`batchTagProblems`

### 2. 新增标签管理页面

新增路由 + 页面（放在 admin 题目模块下，如 `ojnext/src/admin/problem/tags.vue`），沿用现有 admin 页面的表格/弹窗风格（`n-data-table` + `n-modal`）：

- 表格列：标签名（可编辑，`n-input` 内联编辑或点击进入编辑态）、关联题目数、操作（删除）
- 搜索框（对接 `keyword`）
- 重命名保存后，如果响应 `merged: true`，用 `n-dialog`/`message` 提示"已合并到 XX，影响 N 道题"
- 删除按钮点击后先用当前行的 `problem_count` 弹出二次确认对话框（"确定删除标签 XX？当前有 N 道题在使用"），确认后调用删除接口

Admin 侧边菜单加一个入口指向这个新页面。

### 3. 题目后台列表批量打标签

`ojnext/src/admin/problem/list.vue`（普通题目管理列表，竞赛题目列表本次不改）：

- 表格开启行选择（`n-data-table` 的 `row-key` + `checked-row-keys`）
- 顶部工具栏新增"批量添加标签" / "批量移除标签"按钮（选中至少一行才可点击）
- 点击后弹出标签选择弹窗（复用标签管理页的标签列表数据 + `n-dynamic-tags` 或多选 `n-select`），确认后调用批量打标签 API，成功后刷新列表和标签计数

### 4. 现有题目编辑页（`ojnext/src/admin/problem/detail.vue`）

不改交互，仍允许 `n-dynamic-tags` 内联输入新标签；后端 `resolve_tags` 会自动处理大小写归一，无需前端额外校验逻辑（现有 `validateNewTags` 的大小写敏感 `Set` 检查可以保留作为即时提示，但不再是唯一防线）。

## 错误处理

- 重命名/删除标签时标签不存在（并发删除）→ 404，前端提示"标签不存在，请刷新"
- 批量打标签时部分 `problem_ids` 不存在 → 忽略不存在的 id，正常处理其余，不整体失败
- 标签名为空或全空格 → 400，前端表单校验拦截，后端兜底校验

## 测试

按项目约定（`CLAUDE.md`：不新增测试），本次不写新测试，靠手动验证：
1. 跑数据迁移前构造几条大小写不同的重复标签，验证迁移后合并正确、题目关系不丢失
2. 标签管理页增删改、合并提示
3. 批量打标签/移除标签在题目列表生效，学生端筛选栏计数同步更新（缓存失效生效）
