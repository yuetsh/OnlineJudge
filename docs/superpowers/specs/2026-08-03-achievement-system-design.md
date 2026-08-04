# 成就系统设计

日期：2026-08-03
涉及仓库：`OnlineJudge`（后端）、`ojnext`（前端）

## 目标

给 OJ 加一套日式游戏风格的成就（トロフィー）系统，同时服务两个目的：

1. **激励学生持续刷题** —— 累积型成就，人人拿得到，靠进度条产生拉动力
2. **满足收集欲** —— 隐藏型成就，条件奇葩，靠打码和稀有度产生惊喜

成就是纯荣誉，不发放任何可消费的奖励（积分、道具、权限），不接入经济系统。

## 核心设计取舍

| 决策 | 选择 | 理由 |
|---|---|---|
| 规则定义位置 | 数据库可配 | 加成就不用部署 |
| 奇葩条件怎么办 | 代码注册**指标**，后台组合**条件** | 可配性和表达力的折中，见下文 |
| 判定时机 | 判题完成后异步（dramatiq） | 不阻塞、不拖累判题链路 |
| 指标数据来源 | 用户指标快照表 `UserStat` | 判定 O(1)，与"后台可配"形状对齐 |
| 一条成就的条件数 | 单条件 | 避免把后台做成规则引擎，复合需求用复合指标解决 |
| 与现有题单奖章的关系 | 分层共存 | 作用域不同，共享展示层和通知通道 |

### 关于"可配性"的边界

这是整个设计的关键，必须对齐认知：

| | 定义在哪 | 改动成本 |
|---|---|---|
| **能测量什么**（指标） | 代码 `achievement/metrics.py` | 写代码 + 部署 + 跑一次 recompute |
| **多少算达成、叫什么、藏不藏** | 后台表单 | 纯配置，即时生效 |

- 「凌晨提交 10 次 → 夜猫子」和「凌晨提交 100 次 → 生活作息已崩坏」是两条成就、同一个指标，纯后台加
- 「代码里写了 goto」是新维度，必须改代码

推论：**初始指标清单要一次性铺宽**，铺够之后很长一段时间只需要在后台配置。

### 与现有题单奖章（ProblemSetBadge）的关系

`problemset/` 已存在一套奖章系统：

| | 题单奖章 | 成就 |
|---|---|---|
| 作用域 | 绑定单个题单（`problemset` FK） | 全站 |
| 条件 | 3 种，限于该题单进度内 | 任意注册指标 |
| 触发 | 同步，`ProblemSetProgress` 更新时 | 判题后异步 |
| 生命周期 | 随题单删除而删除 | 独立 |

**采取分层共存**，概念上区分：奖章 = 关卡奖励（题单内），成就 = 奖杯（全站累积）。

两套模型各自保留，共享三样东西：

1. **解锁通知通道** —— 奖章现在是静默入库的，学生不知道自己拿到了；接入后终于有反馈
2. **奖杯馆页面** —— 奖章作为其中一个分区，按题单分组展示
3. **咬合点** —— `badge_count`（已获奖章数）、`problemset_completed`（完成题单数）成为成就的普通指标，于是可以配出「收集 10 枚奖章」这类**元成就**

顺带修复现有 `problemset/views/oj.py:_check_badges()` 的两个缺陷：

- 循环内逐条 `exists()` 查询（N+1）→ 改为一次查询取全部候选
- `UserBadge.objects.create()` 未用 `get_or_create` → 并发重复提交会撞 unique constraint 抛异常

## 数据模型

新建 Django app `achievement/`，沿用项目现有结构（`models.py` / `serializers.py` / `views/{oj,admin}.py` / `urls/{oj,admin}.py`）。

### Achievement — 成就定义（管理员可配）

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | TextField | 成就名称 |
| `description` | TextField | 成就描述 |
| `icon` | TextField | emoji 或图标 URL |
| `rarity` | TextField(choices) | `bronze` / `silver` / `gold` / `platinum` |
| `hidden` | BooleanField | 隐藏成就：未解锁时前端显示 `???` 且描述打码 |
| `metric` | TextField(choices) | 指标名，choices 由代码注册表动态提供 |
| `operator` | TextField(choices) | `gte` / `lte` |
| `threshold` | IntegerField | 阈值 |
| `visible` | BooleanField | 是否上架；下架的不参与判定也不展示 |
| `unlock_count` | IntegerField | 已解锁人数计数器，解锁时 `F()+1` |
| `order` | IntegerField | 排序 |
| `create_time` | DateTimeField | |

**一条成就 = 一个条件**，不支持 AND/OR 组合。理由：组合条件会把后台变成小型规则编辑器，而「AC 100 题且连续登录 30 天」这类需求，注册一个复合指标（约 20 行 Python）远比做通用规则引擎便宜。真需要了再加。

**阶梯成就**（AC 10 / 50 / 100）就是三条同 `metric` 不同 `threshold` 的记录，前端按 `metric` 自动归组成系列，不需要额外字段。

`operator` 需要 `lte` 是因为存在「最短 AC 代码 ≤ 50 字符」这类成就。不提供 `eq` —— `gte`/`lte` 已覆盖全部 15 个指标，多一个选项只会让后台能配出永远解锁不了的成就。

### UserStat — 指标快照

```
user         OneToOneField(User)
metrics      JSONField   # {"accepted_count": 42, "midnight_submissions": 3, ...}
update_time  DateTimeField
```

所有指标存一个 JSONB，不开固定列 —— 加新指标零迁移。

**不复用 `UserProfile.accepted_number` / `submission_number`。** `UserStat` 是成就系统唯一的指标源，口径自己闭环，避免两处计数器互相漂移。

### UserAchievement — 解锁记录

```
user          ForeignKey(User)
achievement   ForeignKey(Achievement)
unlock_time   DateTimeField
backfilled    BooleanField   # 见"历史数据补发"
notified      BooleanField   # 是否已向用户弹过奖杯，见"解锁通知"
unique_together (user, achievement)
index (user, -unlock_time)
index (user, notified)        # pending 端点的查询路径
```

全站获得率不实时聚合，读 `Achievement.unlock_count / 分母`。

**分母定义**：`User.objects.filter(is_disabled=False).count()`，Redis 缓存 1 小时。不用"有过提交的用户数"之类的动态口径 —— 分母会随时间波动，导致同一个成就的获得率忽高忽低，学生会觉得是 bug。

## 指标注册表

`achievement/metrics.py`，key → 指标类的注册表。管理员后台 `metric` 下拉框的选项即这张表的 key 列表。

每个指标实现两个方法：

```python
@metric("midnight_submissions", "凌晨提交次数", "0:00–5:00 之间的提交")
class MidnightSubmissions:
    def on_submission(self, metrics, sub, ctx):
        """增量：判题后原地更新 metrics dict"""
        if 0 <= timezone.localtime(sub.create_time).hour < 5:
            metrics["midnight_submissions"] += 1

    def recompute(self, user):
        """全量：backfill / 口径变更 / 兜底重算"""
        return Submission.objects.filter(user_id=user.id, ...).count()
```

`recompute` 是安全网：加新指标、改口径、怀疑数据漂移时，一条管理命令全站重算，不依赖增量逻辑的历史正确性。

`ctx` 是每次判题预先查好一次的共享上下文（这道题此前提交次数、是否首次 AC、今天已 AC 题数等），所有指标复用，避免各自查库。

### 极小值型指标的初始值陷阱

`min_ac_code_chars` 这类"越小越好"的指标不能初始化为 `0`，否则「最短 AC 代码 ≤ 50 字符」对**从未 AC 过的新用户**恒成立（`0 <= 50`），注册当天就白送一个白金奖杯。

规则：**指标未产生过有效值时，key 在 `metrics` 中不存在**（而非置 0）。判定第 6 步遇到 `metric` 不在 `metrics` 里的成就直接跳过。

这条对所有指标统一适用，累积型指标（缺失即视为未达标）行为不变，极小值型指标由此被正确保护。前端进度条同理：指标缺失时显示 `0 / N` 而不是拿缺失值参与计算。

### AC 的口径

判断一次提交是否算通过，一律使用 `submission/models.py` 的 `is_accepted()`，即 `result in (ACCEPTED, AST_CHECK_FAILED)`。

`AST_CHECK_FAILED`（状态码 10）表示测试用例全部通过、但违反了教师配置的代码结构规则。项目里每一处统计 AC 的地方都把它算作通过（个人主页的已通过题数、题目的通过人数、比赛排名等），成就必须跟随同一口径——否则学生个人主页显示「已通过 50 题」而成就进度条显示 47，会被当成 bug 来问。

ORM 过滤无法调用该函数，用 `result__in=(JudgeStatus.ACCEPTED, JudgeStatus.AST_CHECK_FAILED)`。

### 比赛提交不计入成就

**所有基于提交的指标只统计 `contest_id IS NULL` 的提交。** 比赛里做的题不算进「AC 100 题」这类成就。

理由：`UserProfile.acm_problems_status` 本就把 `problems` 和 `contest_problems` 分开存，`dispatcher.judge()` 对比赛分支在 `judge/dispatcher.py:213` 也有独立处理路径；成就跟随平时练习的口径，与现有数据模型一致。

唯一例外是 `contest_joined` —— 它统计的是参赛场次而非题数，本就属于比赛维度。

### 初始指标清单

**累积型**（养习惯，人人可得）

| key | 含义 |
|---|---|
| `accepted_count` | 去重 AC 题目数 |
| `submission_count` | 提交总数 |
| `max_ac_streak_days` | 最长连续 AC 天数 |
| `active_days` | 有提交的累计天数 |
| `languages_used` | 用过的语言种类数 |
| `contest_joined` | 参加过的比赛数 |
| `badge_count` | 获得的题单奖章数 |
| `problemset_completed` | 完成的题单数 |

**隐藏型**（收集癖，奇葩维度）

| key | 含义 |
|---|---|
| `first_try_ac_count` | 一发入魂：首次提交即 AC 的次数 |
| `midnight_submissions` | 0:00–5:00 的提交次数 |
| `compile_error_count` | 编译错误累计次数 |
| `max_wa_before_ac` | 屡败屡战：单题失败最多次后终于通过 |
| `max_ac_in_one_day` | 单日最多 AC 题数 |
| `min_ac_code_chars` | 最短 AC 代码字符数（配 `lte`） |
| `max_code_lines` | 最长代码行数 |

**元指标**（用于白金档的全收集成就）

| key | 含义 |
|---|---|
| `achievement_unlocked_count` | 已解锁的成就数（不含白金档自身） |

这个指标自引用：解锁成就会改变它，进而可能解锁新成就。**判定流程因此限定为最多两轮**：

1. 第一轮用 `on_submission` 更新的普通指标判定，解锁普通成就
2. 若第一轮有解锁，重算一次 `achievement_unlocked_count`，第二轮**只判定依赖该指标的成就**
3. 第二轮结果不触发第三轮

`achievement_unlocked_count` 的口径排除 `rarity=platinum` 的成就，避免「集齐 30 个成就」这类白金奖杯把自己算进分子。

## 判定流程

**投递点：`judge/tasks.py:judge_task` 的末尾**，`dispatcher.judge()` 返回之后。

不挂在 `JudgeDispatcher` 内部：`judge()` 对比赛分支在 `judge/dispatcher.py:213` 会提前 `return`，挂在里面会漏掉那条路径；挂在 actor 末尾则同时覆盖 `JudgeDispatcher` 和 `SQLJudgeDispatcher` 两条判题链路。

```
check_achievements(user_id, submission_id)
  1. select_for_update 取 UserStat（无则建）
  2. 预查一次 ctx
  3. 遍历注册表，各指标增量更新 metrics JSONB
  4. 保存 UserStat
  5. 一次查询取出：visible=True 且该用户尚未解锁的全部 Achievement
  6. 内存中比对 metric / operator / threshold —— 零额外查询
  7. bulk_create UserAchievement(ignore_conflicts=True, notified=False)
  8. F() 批量 +1 unlock_count
  9. 若第 7 步有新解锁 → 重算 achievement_unlocked_count，重复 5–8 但只判定依赖它的成就（第二轮，不再有第三轮）
 10. WebSocket 尝试推送新解锁列表（推送失败不影响已入库的解锁记录）
```

第 5 步一次取全部候选、第 6 步纯内存比对，是刻意与现有 `_check_badges()` 逐条查询相反的写法。整个任务对一次判题只多 3~4 条 SQL。

**任务内异常全部捕获并记日志** —— 成就算错绝不能影响判题结果，这也是选异步的意义。

## 解锁通知：推拉结合

现有 WebSocket **不是常驻连接**：`useSubmissionWebSocket` 全项目只有一处调用（`ojnext/src/oj/problem/composables/useSubmissionMonitor.ts:85`），连接只在问题页且有提交在监听时存在。纯靠 WebSocket 推送会丢消息：

- 用户看完判题结果立刻跳走，异步任务稍后才推送，`group_send` 不为未来成员排队 → 消息丢失
- 题单奖章解锁发生在题单进度 API，那些页面根本没建连接 → 一条都推不到

因此通知走**推拉结合**，`UserAchievement.notified` 是唯一的真相来源：

| 通道 | 作用 | 覆盖场景 |
|---|---|---|
| **拉**（主）| `GET /api/achievements/pending` 返回 `notified=False` 的解锁，弹完由前端 `POST` 标记已读 | 全部场景，绝不丢 |
| **推**（增强）| `utils/websocket.py:push_to_user()` | 判题当场在问题页，即时弹出 |

前端在布局层（`shared/layout/default.vue`）路由切换时拉一次 pending，这样任何页面、任何时刻解锁的成就最终都会弹到。WebSocket 只负责把"当场那一下"的延迟从"下次导航"压到几百毫秒。

推送封装为 `achievement/notify.py` 的独立函数，题单奖章解锁时也调用它（奖章同样写入一条待通知记录）。

### 前端必须改的现有文件

`push_to_user()` 复用了 `submission_update` 这个 channel layer handler 名（`submission/consumers.py` 文档中明写"不可改名"），只把自定义 `type` 塞进内层 data。而 `SubmissionWebSocket` 的泛型是 `SubmissionUpdate`，`useSubmissionMonitor` 的 handler 会把 `type: "achievement_unlocked"` 的帧当成提交更新去读 `submission_id` / `result`。

**`useSubmissionMonitor.handleSubmissionUpdate` 必须先按 `data.type === "submission_update"` 过滤**，成就消息单独分流给成就 store。这是修改现有文件，不是新增。

## 前端：奖杯馆

新页面 `ojnext/src/oj/achievement/index.vue`，路由 `/achievement?name=xxx`（不传 = 自己），与现有 `/user?name=xxx` 约定一致，公开查看他人成就天然成立。路由 meta 保持 `requiresAuth: true`，与 `/user` 一致。

### 页面结构

1. **顶部总览条** —— 总完成度大字百分比，右侧四档稀有度计数（`🥉 12/20　🥈 5/15　🥇 2/10　💎 0/1`）。白金档留给「全收集」类成就。

2. **成就网格**，三种视觉状态：

| 状态 | 显示内容 |
|---|---|
| 已解锁 | 彩色图标、名称、描述、解锁日期、全站获得率（「仅 3.2% 的人获得」） |
| 未解锁·公开 | 灰度图标、描述可见、进度条（42/100） |
| 未解锁·隐藏 | 剪影/问号、名称 `???`、描述打码，仅露稀有度 |

3. **分区 tab**：全部 / 已获得 / 未获得 / 题单奖章。最后一个 tab 按题单分组，复用现有 `getUserBadges`。

日式味道来自三个细节：**进度条**（未解锁也看得见离目标多远，拉动力来源）、**获得率**（炫耀的硬通货）、**隐藏成就打码**（收集欲来源）。获得率低于 5% 的自动加稀有闪光边框。

### 解锁弹窗

`AchievementToast.vue` 挂在布局层，数据来自上面的推拉两个通道：

- 右下角滑入、奖杯光效、3 秒淡出
- 多个同时解锁**排队依次弹出**，不重叠堆积
- 弹完后 `POST` 标记 `notified=True`，避免下次导航重复弹
- 题单奖章解锁复用同一组件

### 炫耀入口

- `oj/user/index.vue` 个人主页加成就摘要区：最近 5 枚 + 完成度 + 跳转奖杯馆
- `oj/rank/list.vue` 排行榜每行挂最稀有的 1–2 枚徽章

## 历史数据补发

老用户已积累数百次 AC，上线当天必须补发，否则成就系统对现有用户是空的。

**`python manage.py recompute_achievements [--user <id>] [--silent]`**

遍历用户 → 对每个指标调 `recompute()` 重建 `UserStat` → 判定 → `bulk_create`。

### 补发不伪造解锁时间

`UserAchievement.backfilled` 为 `True` 的记录，前端不显示具体日期，只显示「已获得」。把数百条历史成就全盖上上线当天的时间戳，会让「最近获得」板块从第一天起就失去意义。

### 首次上线使用 `--silent`

补发的记录直接以 `notified=True` 入库 —— 学生一登录被 30 个奖杯糊脸是灾难。改为个人主页顶部一条一次性提示：「成就系统上线了，你已解锁 23 个成就 →」。

`--silent` 是开关而非硬编码：以后加了新指标再跑重算时不带这个参数，新解锁以 `notified=False` 入库，下次导航正常弹出。

### 阈值下调的补发

管理员把阈值从 100 调到 50 时，已达标的老用户不会自动解锁（判定只在判题时发生）。解法：`Achievement` 保存时若为新建或阈值降低，触发一个只扫这一条成就的 dramatiq 任务。

**实现陷阱**：用 JSONB 筛选达标用户时，`UserStat.objects.filter(metrics__accepted_count__gte=50)` 在 Django JSONField 上走的是 **JSON 值比较**，数字按字符串序比较（`"9" > "50"`），结果错误。必须显式 cast：

```python
from django.db.models.functions import Cast
from django.db.models.fields.json import KeyTextTransform

UserStat.objects.annotate(
    v=Cast(KeyTextTransform("accepted_count", "metrics"), IntegerField())
).filter(v__gte=50)
```

## API

### 用户侧（`achievement/urls/oj.py`）

| 路径 | 说明 |
|---|---|
| `GET /api/achievements?name=<username>` | 奖杯馆数据：全部成就定义 + 该用户解锁状态 + 进度值 + 获得率。隐藏且未解锁的成就，`name`/`description` 在序列化层就替换为占位符，不下发真实内容 |
| `GET /api/achievements/summary?name=<username>` | 个人主页摘要：完成度、各稀有度计数、最近 5 枚 |
| `GET /api/achievements/pending` | 当前用户 `notified=False` 的解锁记录，供布局层拉取弹窗 |
| `POST /api/achievements/pending/read` | 标记指定解锁记录为已弹出 |

### 管理侧（`achievement/urls/admin.py`）

| 路径 | 说明 |
|---|---|
| `GET/POST/PUT/DELETE /api/admin/achievement` | 成就 CRUD |
| `GET /api/admin/achievement/metrics` | 可用指标列表（key + 中文名 + 说明），供后台下拉框 |

管理列表页必须显示每条成就的 `unlock_count` —— 阈值配错（手滑写成 10000）时学生永远拿不到也永远不会来问，这个计数器是唯一的仪表盘。配置一周后仍为 0，多半是配错而非太难。

## 不做的事（YAGNI）

- 成就不发放任何可消费奖励，不接积分/道具/权限体系
- 不做 AND/OR 组合条件
- 不做成就的用户自定义展示顺序、不做「佩戴徽章」
- 不做事件流表（`AchievementEvent`）
- 不做定时全量兜底扫描（`recompute_achievements` 手动跑即可）
