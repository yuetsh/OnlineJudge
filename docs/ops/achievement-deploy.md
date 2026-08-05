# 成就系统上线与运维

首次上线日期：待填（部署当天补）
设计文档：`docs/superpowers/specs/2026-08-03-achievement-system-design.md`
实施计划：`docs/superpowers/plans/2026-08-03-achievement-system.md`

## 这套系统在做什么

学生刷题时后台异步累积一批**指标**（AC 题数、连续 AC 天数、凌晨提交次数……），管理员在后台把「指标 + 比较符 + 阈值」组合成**成就**。判题完成后投递一个 dramatiq 任务重算该用户的指标并判定解锁，解锁后弹奖杯。

关键分工，配置时必须理解：

| | 定义在哪 | 改动成本 |
|---|---|---|
| **能测量什么**（指标） | 代码 `achievement/metrics.py` | 改代码 + 部署 + 跑重算 |
| **多少算达成、叫什么、藏不藏** | 管理后台表单 | 纯配置，即时生效 |

所以「凌晨提交 10 次 → 夜猫子」和「凌晨提交 100 次 → 作息已崩坏」是两条成就、同一个指标，纯后台加即可。「代码里写了 goto」则是新维度，必须先改代码。

## 部署

`deploy/entrypoint.sh` 会自动 `migrate --no-input`，`deploy/supervisord.conf` 的 dramatiq 随容器重启。**正常重新部署即可完成迁移和 worker 加载，不需要手动做这两步**，但必须确认它们成功了。

前后端尽量一起发：前端在每次路由切换时请求 `/api/achievements/pending`，后端没上会在日志里刷一片 404（失败是静默吞掉的，不会白屏）。

### 第一步 确认基础设施

```bash
python manage.py showmigrations achievement          # 应为 [X] 0001_initial
grep -c "check_achievements" /data/log/dramatiq.log  # 应 > 0
```

**worker 日志里没有 `check_achievements` 这个 actor，说明它没加载新代码——成就永远不会判定，而且不报任何错。** 这是最容易被忽略的失败模式。

### 第二步 跑自检

```bash
python manage.py check_achievement_deploy
```

只读，可反复跑，七项检查。此刻大部分是 `[SKIP]`（还没配成就、还没重算），**但这两项必须现在就 PASS**：

- **极小值指标对零 AC 用户返回 None** —— 不 PASS 就别配任何 `lte` 类成就。这类指标若返回 `0`，「最短 AC 代码 ≤ 50 字符」之流会白送给每一个从没做出过题的新生。线上目前没有 `lte` 成就，本项会 SKIP，配了才开始检查。
- **JSONB 阈值比较按整数** —— 不 PASS 的话，以后在后台调低阈值触发的补发会发给错误的人群。JSONB 里的数字若不显式 cast，Postgres 按字符串序比较，`"9" > "50"` 成立。

### 第三步 单人试跑重算

```bash
python manage.py recompute_achievements --user <某活跃学生id>
python manage.py check_achievement_deploy
```

「重算重建了增量辅助键」这项应从 SKIP 变 PASS。不 PASS 的话，那个学生**下次提交时活跃天数会从几十掉回 1**，并且要等到下一次重算才恢复。

### 第四步 配成就并全量补发

在管理后台「成就」页配置。累积型设 `hidden=False`、隐藏型设 `hidden=True`。实施计划文档 Task 13 里有一份 17 条的初始参考表，但线上早已在其之上迭代（2026-08-05 起 38 条），**以管理后台的实际配置为准，别照着计划文档重配**。

配阈值前先看真实分布，别拍脑袋——线上踩过的坑：`contest_joined` 最高只有 7（各班只打自己班的比赛），配 ≥10 是零解锁；`min_ac_code_chars` 最小值 8（有道题 8 个字符能过），已因此删除该指标。分布查询：

```bash
python manage.py shell -c "
from achievement.models import UserStat
k = 'hard_ac_count'
v = sorted((s.metrics[k] for s in UserStat.objects.all() if k in s.metrics), reverse=True)
print('n=', len(v), 'top20=', v[:20], 'p95/p99=', v[int(len(v)*0.05)], v[int(len(v)*0.01)])
"
```

**阈值只能从严往松调**：调低会自动补发，调高不撤销已发出的记录。新成就先配高阈值看 `unlock_count`，太少再往下调；配松了想收紧只能删掉成就（级联删解锁记录）重建。

```bash
python manage.py recompute_achievements --silent
python manage.py check_achievement_deploy    # 七项应全部 PASS
```

**`--silent` 不能省。** 省了的话，几百个学生下次登录会被几十个奖杯连续糊脸，一个接一个弹三秒。

`--silent` 只在首次上线用。以后加了新指标再跑重算时不带这个参数，新解锁会正常弹出。

## 日常运维

### 加一条成就

后台直接配。若指标已存在，不需要部署。

新建和「放宽条件」（改 metric / 改比较符 / 调阈值 / 从下架转上架）会自动触发 `rescan_achievement` 补发给已达标的存量用户——判定只在判题时发生，不补发的话他们要等到下次提交才拿到。

### 加一个新指标

必须改 `achievement/metrics.py`：

1. 写一个 `@metric(...)` 类，实现 `on_submission`（增量）和 `recompute`（全量）
2. **如果 `on_submission` 依赖 `_` 前缀的辅助键，必须同时实现 `recompute_state`** —— 否则全量重算丢掉辅助键后，用户下一次提交会把该指标打回初始值
3. 部署后跑 `python manage.py recompute_achievements`（不带 `--silent`，让新解锁正常弹出）
4. 跑 `check_achievement_deploy` 确认

### 定期检查

每周跑一次自检，重点看「疑似配错阈值的成就」。**公开成就配置一周后仍然零解锁，多半是阈值配错了而不是太难**——学生拿不到不会来问你，管理后台列表的「已解锁人数」列是唯一的信号。

## 出问题了怎么办

### 配错了想重来

```bash
python manage.py shell -c "
from achievement.models import Achievement, UserAchievement
UserAchievement.objects.all().delete()
Achievement.objects.update(unlock_count=0)   # 这行别忘
"
python manage.py recompute_achievements --silent
```

**`unlock_count` 是独立的计数器，删解锁记录不会清零它。** 忘了这行再重跑，获得率会翻倍显示。`check_achievement_deploy` 的「unlock_count 与实际解锁人数一致」这项就是在防这个。

### 某个学生的指标看起来不对

```bash
python manage.py recompute_achievements --user <id>
```

全量重算是增量逻辑的安全网，怀疑漂移时对单人跑一次即可。

### 想临时关掉某条成就

后台把它改成下架（`visible=False`）。已解锁记录保留，只是不再展示也不再判定。重新上架会自动补发给期间达标的人。

## 已知未验证的部分

**这套系统开发全程没有可用的数据库**，后端全部逻辑只经过静态审查。开发期修掉的六个缺陷里没有一个是转录错误，全是设计疏漏——这说明纸面审查有效，但它抓不到运行期行为。

`check_achievement_deploy` 就是为这一层准备的。下面这些只有真跑起来才能确认，**都属于"错了也不报错、只是悄悄发错奖杯"**：

- JSONB 阈值比较是否真按整数（自检第 4 项）
- 极小值指标对零 AC 用户是否返回 `None`（自检第 3 项）
- 重算是否重建了增量辅助键（自检第 5 项）
- 并发判题时 `unlock_count` 是否重复累加（自检第 6 项）

另有一份逐条的验证清单在 `.superpowers/sdd/2026-08-03-achievement-system/deferred-verification.md`（附命令与期望输出）。

## 已知遗留问题

按影响排序，都不阻塞上线：

1. **题单奖章的管理员重算路径仍然静默发放。** `problemset/models.py:recalculate_user_badges` 不调 `notify_badges`，学生不会收到弹窗。提交触发的路径（`_check_badges`）已经接了通知。
2. **奖章的条件判断逻辑有两份。** `problemset/views/oj.py:_check_badges` 和 `problemset/models.py:_is_eligible` 各自实现了同样三个条件，今天一致。将来加条件类型时只改一处，`recalculate_user_badges` 会把另一条路径发出的奖章当作"不再符合条件"而删掉。
3. **全量重算时 4 个指标的查询跑两遍**（`recompute` 和 `recompute_state` 各一次）。离线批处理命令，不影响正确性。
4. **`POST /api/achievements/pending` 的 `ids` 未做元素类型校验。** 传非整数会在 ORM 层抛异常，表现为不透明的 500。需要登录，无越权风险。
5. **`threshold` 的校验用 `isinstance(x, int)`，Python 里 `bool` 是 `int` 的子类**，所以 `{"threshold": true}` 会被存成 1。仅管理员可达。
