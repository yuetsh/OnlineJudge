# 题目点评重写：从评分表单到表情 Reaction

> 2026-08-06 规则更新：评价已改为单选，点击一个表情后立即提交，且提交后不可修改。一人一题在数据库中最多保留一条记录。新请求字段为 `type`，新响应字段为 `mine_type: ReactionKey | null`；为支持前后端错序部署，过渡期仍接受单元素 `types` 并返回数组 `mine`。计数直接查询数据库，不使用 Redis 缓存。本文后续关于“最多选 3 个、可取消、整份覆盖、统计缓存”的内容仅保留为早期设计记录，不再代表当前行为。

> 2026-08-06 后台形态变更：独立的后台反馈统计页与 `GET /api/admin/reaction` 已全部下线（`reaction/views/admin.py`、`reaction/urls/admin.py`、`src/admin/reaction/list.vue`、路由与菜单项均已删除）。取而代之，**后台题目列表**（`src/admin/problem/list.vue`）多一列「反馈」，只显示该题票数最高的那一个表情图标，tooltip 出「标签名 + 人数」；无人评价则留空，并列第一时按 `ReactionType` 的定义顺序取靠前的一个。数据来自 `GET /api/admin/problem` 新增的 `top_reaction: {type, count} | null` 字段，由 `reaction/services.py:get_top_reactions()` 对当页题目做一次聚合查询算出（比赛题目列表不返回该字段，前端也不显示该列）。本文「管理接口」「后台页面」两节仅为早期设计记录，占比排序、七列计数表、按题号筛选均已不存在。

日期：2026-08-06
涉及仓库：`OnlineJudge`（后端）、`ojnext`（前端）

## 背景与目标

现有的题目点评要求学生 AC 后填三项 1–5 星评分（题目描述是否清楚、难度是否匹配、综合评分）外加一段可选文字，一次性提交且不可修改。

两个实际问题：

1. **学生填不动。** 三个维度、三次打星，交互成本高，多数人随手全给 5 分，或者干脆跳过。
2. **收集到的数据没用。** 平均分对出题和教学没有参考价值；文字评价几乎没人写。

重写目标：把点评降到**一次点击**的成本，同时让每一次点击都是一条语义明确、可直接指导出题的数据。形态参考 GitHub issue 的 reaction 按钮。

## 设计决策

已确认，实现时不再重新讨论。每条的理由见文末「附录：设计取舍记录」。

| 决策 | 结论 |
|---|---|
| 交互形态 | 一排表情按钮，点击即表态，无表单无提交按钮 |
| 表情语义 | 做题场景定制的 7 个，非 GitHub 通用集 |
| 选择规则 | 多选 + 可取消，**最多同时选 3 个** |
| 前台布局 | 七个按钮**始终一排**，不换行，窄屏降级为图标 + 计数 |
| 文字评价 | **完全删除**，不保留任何输入框 |
| 点评门槛 | **必须 AC**，七个表情一视同仁，不按维度区分 |
| 计数可见性 | **自己点完之后**才能看到全部计数，由服务端保障 |
| 老数据 | **直接丢弃**，不迁移 |
| 后端模块 | 新建 `reaction` app，删除 `comment` app |
| 存储形态 | **一行一个表情**，`unique(problem, user, type)` |
| 表情渲染 | Iconify SVG 图标，**代码与数据库中不出现 Unicode emoji 字面量** |

## 表情集合

共七个，按钮渲染顺序即下表顺序：

| key | 中文标签 | Iconify 图标 | 收到之后的动作 |
|---|---|---|---|
| `too_easy` | 太简单 | `fluent-emoji:smiling-face-with-sunglasses` | 难度标低了，上调 |
| `too_hard` | 太难了 | `fluent-emoji:exploding-head` | 难度标高了，或缺前置铺垫 |
| `confusing` | 没看懂 | `fluent-emoji:face-with-spiral-eyes` | 改题面表述 |
| `buggy` | 题目有错 | `fluent-emoji:bug` | 立刻查样例与测试数据 |
| `learned` | 学到了 | `fluent-emoji:light-bulb` | 正面信号，多出这类题 |
| `interesting` | 有意思 | `fluent-emoji:star-struck` | 动机信号，这类题能提起兴趣 |
| `want_explain` | 想听讲解 | `fluent-emoji:books` | 排课参考，挂得多的优先讲 |

后端 `ReactionType` 与前端 `REACTIONS` 常量**必须保持同步**，属于跨项目同步项，与 `JudgeStatus` 同级。改动其一必须同时改另一个。

七个图标名均已在自建 Iconify 服务（`icon.xuyue.cc`）上验证返回 200。注意 `face-with-crossed-out-eyes` 与 `dizzy-face` 均为 404，不要使用。

## 后端设计（OnlineJudge）

### 模块与清理

新建 Django app `reaction`，结构遵循项目现有约定：

```
reaction/
├── models.py
├── serializers.py
├── views/
│   ├── oj.py
│   └── admin.py
└── urls/
    ├── oj.py
    └── admin.py
```

删除 `comment` app 整个目录，同时清理四处引用：

- `oj/settings.py` 的 `INSTALLED_APPS`：移除 `"comment"`，加入 `"reaction"`
- `oj/urls.py`：`comment.urls.oj` / `comment.urls.admin` 两条 include 替换为 reaction 对应路由
- `utils/constants.py`：`CacheKey.comment_stats` 替换为 `CacheKey.reaction_stats`
- 迁移：新增一个迁移删除 `comment` 表，老数据不做任何转换

### 数据模型

```python
class ReactionType(models.TextChoices):
    TOO_EASY     = "too_easy",     "太简单"
    TOO_HARD     = "too_hard",     "太难了"
    CONFUSING    = "confusing",    "没看懂"
    BUGGY        = "buggy",        "题目有错"
    LEARNED      = "learned",      "学到了"
    INTERESTING  = "interesting",  "有意思"
    WANT_EXPLAIN = "want_explain", "想听讲解"


class Reaction(models.Model):
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    type = models.CharField(max_length=20, choices=ReactionType.choices)
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reaction"
        unique_together = ("problem", "user", "type")
        indexes = [
            models.Index(fields=["problem", "type"], name="reaction_problem_type_idx"),
        ]
```

相比旧 `Comment`，去掉了 `submission` 外键、`language`、三个 rating 字段和 `content`。

### 用户接口

路由 `GET/POST /api/reaction`，两个方法都要求登录。

**GET** `?problem_id=X`

```json
{
  "mine": ["too_hard", "learned"],
  "counts": { "too_easy": 2, "too_hard": 8, "confusing": 3, "buggy": 0,
              "learned": 12, "interesting": 7, "want_explain": 4 }
}
```

`counts` 的下发规则：

- `mine` 为空时，`counts` 为 `null`。**「点完才显示计数」由服务端保障**，未表态的用户根本拿不到别人的数据，不依赖前端隐藏
- `mine` 非空时，`counts` 包含全部七个 key，计数为 0 的也要下发，前端不必补默认值

**POST** `{ "problem_id": X, "types": ["too_hard", "learned"] }`

`types` 是该用户对该题**期望的完整表情列表**，不是增量。返回结构与 GET 一致。

- 取消某个表情 = 传一个更短的数组
- 全部取消 = 传 `[]`
- 同一用户连续点击，最后一次请求生效；不存在跨用户并发问题

写入实现：

```python
with transaction.atomic():
    Reaction.objects.filter(user=..., problem=...).delete()
    Reaction.objects.bulk_create([Reaction(...) for t in types])
```

校验：

- `types` 中每一项必须属于 `ReactionType`，否则 400
- **`types` 去重后长度不超过 3**，超出返回 400。前端已做置灰限制，此处是服务端兜底，不可省略
- 该用户对该题必须存在 `result in (ACCEPTED, AST_CHECK_FAILED)` 的提交，否则拒绝写入（沿用旧 `CommentAPI.post` 的判定逻辑）
- 题目必须 `visible=True`

### 统计缓存

缓存键 `reaction_stats:{problem_id}`，TTL 3600 秒，POST 成功后删除对应键。沿用 `utils/async_helpers` 的 `async_cache_get` / `async_cache_set` / `async_cache_delete`。

### 管理接口

路由 `GET /api/admin/reaction`，`@super_admin_required`。

按题目聚合，统计、排序、分页全部由数据库完成：

```python
qs = (
    Reaction.objects.values("problem___id", "problem__title")
    .annotate(
        users        = Count("user", distinct=True),
        too_easy     = Count("id", filter=Q(type="too_easy")),
        too_hard     = Count("id", filter=Q(type="too_hard")),
        confusing    = Count("id", filter=Q(type="confusing")),
        buggy        = Count("id", filter=Q(type="buggy")),
        learned      = Count("id", filter=Q(type="learned")),
        interesting  = Count("id", filter=Q(type="interesting")),
        want_explain = Count("id", filter=Q(type="want_explain")),
    )
    .annotate(
        # 七个表情各一条，此处仅示意其中一个
        confusing_ratio = Cast("confusing", FloatField()) / Cast("users", FloatField()),
    )
)
```

**表情列按占比排序，不按数量。** 排序值是「点该表情的人数 ÷ 该题表态总人数」。占比排序时**过滤掉表态人数少于 3 的题**（`filter(users__gte=3)`），避免 1 人点 1 个表情就冲到 100% 占满首屏；按 `users` 排序时不加此过滤。

表格中每列显示的仍是**数量**，只有排序用占比——人数列就在旁边，占比是否值得关注管理员一眼能判断。

查询参数：

- `problem` — 按题目序号（`_id`）筛选，可选
- `ordering` — 排序字段，允许值为 `users`（按数量）及七个表情 key（按占比），前缀 `-` 表示降序；默认 `-users`。传入其它值一律回落到默认，不报错
- 分页沿用 `self.paginate_data`

旧 admin 接口的删除单条评论功能**去掉**。没有自由文字就没有不当言论需要清理。

## 前端设计（ojnext）

### 组件与挂载点

`src/oj/problem/components/ProblemComment.vue` → 重写为 `ProblemReaction.vue`。

挂载点不变，共四处，全部改为引用新组件：

- `src/oj/problem/detail.vue` 三处
- `src/oj/problem/components/SubmitCode.vue` 一处

`showStatistics` prop **删除**。计数可见性现在由「该用户是否已表态」决定，不再由调用方控制，`SubmitCode.vue` 中传的 `:showStatistics="false"` 一并去掉。

### 布局：七个按钮永远一排

容器 `flex-wrap: nowrap`，**不允许换行**，按屏宽分三档降级：

| 档位 | 按钮内容 | 说明 |
|---|---|---|
| 宽屏 | 图标 + 中文标签 + 计数 | 完整形态 |
| 窄屏 / 分屏 | 图标 + 计数 | 标签退到 tooltip，用 `shared/composables/breakpoints` 判断 |
| 极窄 | 图标 + 计数 | 容器 `overflow-x: auto` 横向滚动兜底 |

### 三种显示状态

```
未登录 / 未 AC
  [😎 太简单] [🤯 太难了] [😵 没看懂] [🐛 题目有错] [💡 学到了] [🤩 有意思] [📚 想听讲解]
  灰色禁用，提示「完成本题后可以评价」

已 AC 未表态
  [😎 太简单] [🤯 太难了] [😵 没看懂] [🐛 题目有错] [💡 学到了] [🤩 有意思] [📚 想听讲解]
  可点击，不显示任何数字

已表态（此例已选 2 个，还能再选 1 个）
  [😎 太简单 2] [🤯 太难了 8] [😵 没看懂 3] [🐛 题目有错 0] [💡 学到了 12] [🤩 有意思 7] [📚 想听讲解 4]
        ↑ 自己点过的高亮描边
```

计数为 0 的表情仍然显示按钮，只是不带数字，保持按钮位置稳定，避免点击后整排跳动。

### 交互

- 组件挂载时 `GET /api/reaction`，一次请求拿到 `mine` 与 `counts`；**未登录不发请求**，直接渲染禁用态
- **最多同时选中 3 个**。已选满时，未选中的按钮全部置灰不可点，tooltip 提示「最多选 3 个，先取消一个」；已选中的按钮仍可点击以取消
- 点击按钮：**乐观更新**，先切换本地高亮与计数，再发 POST；请求失败则回滚并提示
- 连续点击不做防抖。POST 传的是完整期望列表，后到的请求覆盖先到的，天然收敛
- 悬停 tooltip 显示完整文案，例如「8 人觉得太难了」

### 常量

在 `src/utils/constants.ts` 中新增：

```ts
export const REACTIONS = [
  { key: "too_easy",     label: "太简单",   icon: "fluent-emoji:smiling-face-with-sunglasses" },
  { key: "too_hard",     label: "太难了",   icon: "fluent-emoji:exploding-head" },
  { key: "confusing",    label: "没看懂",   icon: "fluent-emoji:face-with-spiral-eyes" },
  { key: "buggy",        label: "题目有错", icon: "fluent-emoji:bug" },
  { key: "learned",      label: "学到了",   icon: "fluent-emoji:light-bulb" },
  { key: "interesting",  label: "有意思",   icon: "fluent-emoji:star-struck" },
  { key: "want_explain", label: "想听讲解", icon: "fluent-emoji:books" },
] as const

export const MAX_REACTIONS = 3
```

### API 层与类型

- `src/oj/api.ts`：删除 `createComment` / `getComment` / `getCommentStatistics`，新增 `getReaction(problemID)` 与 `setReaction(problemID, types)`
- `src/admin/api.ts`：删除 `getCommentList` / `deleteComment`，新增 `getReactionStats(offset, limit, problem, ordering)`
- `src/utils/types.ts`：删除 `Comment` 接口，新增 `ReactionKey`、`ReactionStats` 等类型

### 后台页面

`src/admin/communication/comments.vue` → 改为 `reactions.vue`，路由与菜单项文案由「评论管理」改为「题目反馈」。删除 `components/CommentActions.vue`。

页面形态从「逐条评论 + 删除按钮」改为**按题目聚合的统计表**：

| 题目 | 表态人数 | 😎 太简单 | 🤯 太难了 | 😵 没看懂 | 🐛 题目有错 | 💡 学到了 | 🤩 有意思 | 📚 想听讲解 |

- 表头同样使用图标 + 文字，不要只放图标
- 七个表情列均**可点击排序**，服务端排序，配合分页
- 后台是宽屏场景，表格允许横向滚动，不做前台那套窄屏降级
- 题目列保留跳转到题目详情的链接（沿用现有实现）
- 顶部保留按题目序号筛选的输入框
- 无删除操作

排序是这张表的核心用法：点「没看懂」那一列降序，排在最上面的就是题面最需要修改的题。

## 验证方式

本地无 Docker、无数据库与判题沙箱，后端跑不起来。按项目约定：

- `makemigrations` 可以本地执行（不连库），`migrate` 只能在服务器上跑
- 后端改动通过代码审查与 `ruff check .` 静态检查验证，运行时验证在服务器上进行
- 不编写测试（项目测试策略）
- 前端通过 `npm run build` 验证编译通过，交互在开发服务器上人工验证

## 明确不做的事

- 不做表情的实时推送（不接 WebSocket），计数在页面加载时取一次即可
- 不做点评历史、不做撤销记录、不做审计日志
- 不给管理员提供删除某个学生表态的功能
- 不在题目列表页展示表情统计，只在题目详情页与后台展示
- 不做按班级/时间维度的分析界面。数据模型已经支持，等真的需要时再加
- 不做前台的表情换行布局。七个按钮始终一排，窄屏靠降级和横向滚动解决
- **不做后台配置表情的功能**。表情集合写死在后端 `ReactionType` 与前端 `REACTIONS` 常量中，改动需要改代码并发版

---

## 附录：设计取舍记录

以下是各项决策背后的推理。实现时不需要读，但日后想改动某项决策前应该先看这里，避免重复讨论已经讨论过的问题。

### 表情维度是怎么筛出来的

**筛选原则：系统已有的数据不占按钮。** 提交次数、耗时、使用语言、通过率都能从 submission 表算出来，不需要学生点。表情只收集系统看不见的东西——学生的感受和判断。据此排除了「花了好久」「一遍过」「蒙对的」等候选。

**已排除的维度：**

| 维度 | 排除原因 |
|---|---|
| 好题 | 与「学到了」收到的是同一批人，重复占位 |
| 差题 | 不可行动。难度不对有「太难了」，题面不清有「没看懂」，剩下的「差」是纯情绪，收到了也不知道改什么 |
| 有思路但写不出 | 与 AC 门槛互斥——AC 了就是写出来了 |
| 难度刚好 | 能提供基线（让「没人点」变得可解释），但优先级低于已选七项 |
| 没学过这个 | 教学进度错位的信号，价值高，但七个已是布局上限。若日后要加，优先考虑换掉「想听讲解」 |

**「学到了」与「有意思」不重复。** 前者是知识收获，后者是动机，两者正交：一道题可以很有收获但枯燥，也可以很好玩但没学到新东西。对中职学生而言动机信号单独有价值，因此并存。

### 「必须 AC」这个门槛的代价

门槛定为必须 AC 且不按维度区分。这对三个维度有实质影响，实现时不要试图「修正」：

- **「没看懂」**含义收窄为「最终做出来了，但题面读了很久 / 靠猜才明白要求」。仍是题面要改的有效信号，只是收不到被彻底卡死那批人的反馈。
- **「题目有错」**只能收到 AC 学生察觉得到的那半部分：样例输出印错、题面条件与实际数据不符（如题面写 `n ≤ 100` 实际到 10000）、题面说的判定规则与实际判定不一致。**收不到最严重的一类**——测试数据本身错误或标程错误导致正确代码恒 WA，受害者永远 AC 不了，也就永远点不了这个按钮。这类问题仍需其它途径发现。
- **「想听讲解」**含义变成「做出来了，但想听更好的解法」，而不是「被卡住求救」。价值打折但仍成立。

讨论过给「题目有错」和「想听讲解」单独放宽门槛（提交过即可点），结论是不做——按维度区分门槛会让前后端判定逻辑都变绕，收益不足以抵消。

### 为什么一行一个表情，而不是一行存数组

考虑过一个用户对一道题存一行、表情放 `ArrayField` 数组。否决原因是后台那张表：

核心产出是「按某个表情的占比排序、找出最该改的题」。关系模型下这是一条带排序和分页的 ORM 查询；数组模型下必须全表拉进内存做 Python 聚合、内存排序、内存分页，而且排序键是聚合值，数据库完全帮不上忙，每翻一页都要重算。此外后续若要按班级、时间段等维度切分，关系模型只需加 `filter`。

代价是行数约为数组方案的 1.5 倍，在本项目规模下无影响。写入复杂度两者相当，都能做整份覆盖，都不涉及读-改-写。

### 为什么排序按占比而不是数量

一道 200 人做过、5 人点「没看懂」的题，题面问题远小于一道 3 人做过、3 人全点「没看懂」的题。按数量排会把前者顶到上面，与「排在最上面的就是最该改的题」这个使用目的直接相悖。低样本噪声用 `users >= 3` 的过滤挡掉。

### 为什么不用 Unicode emoji 字面量

机房电脑 Chrome 版本低（<94），系统 emoji 字体覆盖不全，直接输出 Unicode emoji 会出豆腐块。因此数据库存语义 key，前端一律用 `@iconify/vue` 渲染 `fluent-emoji` 的 SVG，与系统字体彻底解耦。

按钮在宽屏下带中文标签，除了语义更清晰，也是一层降级保护：Iconify 服务不可达时至少还剩文字。但窄屏档位为了「一排显示」牺牲了标签，此时若图标加载失败按钮会变成一排空白——这是「一排显示」与「图标挂了仍可用」之间的取舍，已选前者。
