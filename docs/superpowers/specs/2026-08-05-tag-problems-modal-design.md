# 标签管理：点击查看对应题目

## 背景

后台标签管理页（`ojnext/src/admin/problem/tags.vue`）目前只显示每个标签的 `problem_count` 数字，管理员无法知道具体是哪些题目在用这个标签。重命名/合并/删除标签时缺少判断依据。

后台题目列表 API（`ProblemAdminAPI.get`）当前只支持 `keyword` 和 `author` 两个筛选条件，没有按标签筛选的能力。

## 目标

在标签管理页点击标签名或题目数，弹窗列出该标签下的题目，并支持跳转编辑、按标题搜索、直接移除该题的这个标签。

## 方案

复用后台题目列表 API，给它加一个 `tag_id` 筛选参数。弹窗因此白拿分页、标题搜索和 `can_mgmt_all_problem` 权限过滤，不需要新建接口。移除标签复用已有的 `BatchProblemTagAPI`。

### 后端

`OnlineJudge/problem/views/admin.py` — `ProblemAdminAPI.get`，在现有 `author` / `keyword` 过滤旁边加：

```python
tag_id = request.GET.get("tag_id")
if tag_id:
    problems = problems.filter(tags__id=tag_id)
```

没有其他后端改动。移除标签走已有的 `POST admin/problem/batch_tag`，`action="remove"`，该接口已经会 `clear_tag_cache()`。

### 前端 API

`ojnext/src/admin/api.ts` — `getProblemList` 末尾加可选参数 `tagId`，为空时不传给后端。

### 弹窗组件

新建 `ojnext/src/admin/problem/components/TagProblemsModal.vue`。

- props：`tagId: number`、`tagName: string`、`v-model:show`
- emits：`changed` —— 移除标签成功后触发，父组件据此刷新题目数
- 顶部：搜索框，debounce 500ms，走后端 `keyword` 参数
- 表格列：
  - 显示 ID（`_id`）
  - 标题 —— 点击 `router.push` 到 `admin problem edit`，同时关闭弹窗
  - 是否公开（`visible`）
  - 「移除标签」按钮 —— 调 `batchTagProblems([row.id], [tagName], "remove")`，成功后刷新弹窗列表并 `emit("changed")`
- 底部：分页，每页 10 条
- 打开弹窗时重置到第 1 页、清空搜索词

### tags.vue 接入

标签名列和题目数列都渲染成可点击（`n-button text`），点击时记录当前行的 `id` / `name` 并打开弹窗。弹窗 `changed` 事件触发时调用现有的 `listTags()` 同步题目数。

标签名列在编辑态（`editingId === row.id`）下仍然渲染 `NInput`，不可点击。

## 已知不一致

标签表的 `problem_count` 来自 `TagAdminAPI` 的 `Count("problem")`，是全量统计；而弹窗走 `ProblemAdminAPI`，非超管只能看到自己创建的题。因此普通 admin 可能看到「题目数 12」但弹窗只列出 3 道。

本次不处理。当前使用场景以超管为主，两个数字一致。若将来需要抹平，给 `TagAdminAPI` 的计数加上同样的创建者过滤即可。

## 不做的事

- 不给后台题目列表页加标签筛选的 UI（本次只有弹窗用 `tag_id`）
- 不在弹窗里做批量移除
- 不改前台（`oj/`）的标签相关页面
