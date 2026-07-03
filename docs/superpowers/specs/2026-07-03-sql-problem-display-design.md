# SQL 题数据化展示设计

日期：2026-07-03

## 背景

SQL 题目前沿用传统题的展示结构：「输入/输出」两段富文本描述 + `samples`（纯文本输入输出对，附带一个对 SQL 无效的"测试"按钮）。这与 SQL 题的实际形态不符——SQL 题的本质是「给定数据表 → 写出查询/修改语句 → 得到结果集/表的新状态」，学生需要看到的是**表结构、示例数据、期望结果**，而不是文本化的输入输出。

判题侧现状（`judge/sql_dispatcher.py` + `judge/sql_runner.py`）：

- 每个测试点的 input 文件是一份建表 + 插数据的 sqlite 初始化脚本
- 期望结果由题目 `answers` 中的 SQL 标准答案现场执行得出
- `sql_config`：`{"mode": "query"|"modify", "order_sensitive": bool}`

## 核心决策

1. **展示数据自动生成**，不由管理员手动录入：后端在保存题目时用 sqlite 跑测试点 1 的初始化脚本得到「数据表」，跑标准答案得到「期望结果」，存成结构化 JSON。展示与判题同源，永不脱节，出题人零额外工作。
2. **modify 题只展示有变化的表**：对比初始状态与标准答案执行后的状态，仅输出内容有变化的表，标为「执行后的 XX 表」。
3. **期望结果直接展示**（含 query 题的结果集），与 LeetCode 等业界惯例一致，利于学生对照调试。

## 后端设计

### 数据结构

`Problem` 新增 `sql_display` JSONField（`null=True`，非 SQL 题或生成条件不满足时为 `null`）：

```json
{
  "tables": [
    {
      "name": "students",
      "columns": [{ "name": "id", "type": "INTEGER" }, { "name": "name", "type": "TEXT" }],
      "rows": [[1, "小明"], [2, "小红"]],
      "total_rows": 12,
      "truncated": true
    }
  ],
  "expected": {
    "columns": ["name", "score"],
    "rows": [["小明", 95]]
  }
}
```

- query 模式：`expected` 为 `{columns, rows}` 结果集
- modify 模式：`expected` 为 `{"changed_tables": [{name, columns, rows, total_rows, truncated}]}`，只含有变化的表
- modify 模式中被标准答案 DROP 的表以 `{"name", "columns"(原结构), "rows": [], "total_rows": 0, "truncated": false, "dropped": true}` 条目出现，前端渲染为「XX 表已被删除」
- modify 模式若标准答案未改动任何表，保存时报错（视为出题配置问题）

### 生成逻辑

`judge/sql_runner.py` 新增 `build_display(init_sql, ref_sql, mode)`：

- 复用现有 `_init_conn`、`_execute_statements`、`_dump_tables`
- 用 `PRAGMA table_info` 取各表列名与声明类型
- 只取**测试点 1** 的初始化脚本（测试点 1 即"样例"，其余为隐藏用例，与传统题语义一致）
- 每表 / 结果集最多存 **20 行**，超出时记录 `total_rows` 与 `truncated: true`
- modify 模式：dump 初始状态 → 执行标准答案 → dump 最终状态 → 逐表对比，只输出有差异的表

### 触发时机

管理端创建/编辑题目保存时（problem admin view/serializer 层）：

- `sql_config` 存在且测试点、SQL 标准答案齐备 → 生成并写入 `sql_display`
- 初始化脚本或标准答案执行失败 → 直接把错误返回给出题人（提前暴露配置问题）
- 缺答案或缺测试点 → `sql_display = null`，前端降级为只显示描述
- 测试点重新上传后，再次保存题目即重新生成

`sql_display` 随现有 Problem 序列化器下发给学生端与管理端。

## 前端设计

### 学生端 `oj/problem/components/ProblemContent.vue`

以 `problem.sql_config` 判断是否 SQL 题。SQL 题下：

- 隐藏「输入」「输出」富文本区块与「例子」区块（连同无效的"测试"按钮）
- 新增「数据表」区块：每张表一个 `n-data-table`，上方标表名，表头为列名 + 灰色小字类型标注（如 `name TEXT`）；`truncated` 时显示「共 N 行，仅展示前 20 行」
- 新增「期望结果」区块：
  - query 题：渲染结果表；`order_sensitive === false` 时附提示「结果顺序不限」
  - modify 题：按「执行后的 XX 表」逐表渲染
- `sql_display` 为 null 时不渲染这两个区块（降级为仅描述）
- 描述、提示、要求、来源、相似题目等区块照旧

### 管理端 `admin/problem/detail.vue`

选择 SQL 后隐藏「输入描述 / 输出描述 / 样例」表单项，其余不动。

### 类型同步

`ojnext/src/utils/types.ts` 给 `Problem` 加 `sql_display` 类型定义。

## 不做的事（YAGNI）

- 不做展示数据的手动覆盖/编辑
- 不展示测试点 2 及之后的数据
- 不做 ER 图、外键可视化
- 不加「隐藏期望结果」开关（如未来有需要，可在 `sql_config` 中扩展）
