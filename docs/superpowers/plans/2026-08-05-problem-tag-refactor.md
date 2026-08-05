# 题目标签重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `ProblemTag` 从「编辑题目时顺手创建的自由文本」变成可集中管理的实体：名字规范化去重、有专门的管理后台（重命名/合并/删除）、题目列表支持批量打标签。

**Architecture:** 后端给 `ProblemTag.name` 加大小写不敏感唯一约束，配一次性数据迁移合并现存重复标签；新建 `problem/services.py` 收敛四处重复的标签 get-or-create 逻辑；新增两个 admin 接口（标签 CRUD、批量打标签）。前端新增标签管理页，并给题目管理列表加行选择 + 批量打标签弹窗。

**Tech Stack:** Django 6 + DRF + PostgreSQL / Vue 3 + TypeScript + Naive UI

**Spec:** `docs/superpowers/specs/2026-08-05-problem-tag-refactor-design.md`

## Global Constraints

- **不写测试。** 项目 `CLAUDE.md` 明确规定 "Do not write tests"。本计划不含 TDD 循环，每个任务用可执行的验证命令（`ruff`、Django shell、浏览器操作）替代测试步骤。执行者不得自行添加测试文件。
- 后端仓库 `OnlineJudge/`，前端仓库 `ojnext/`，**两者是独立的 git 仓库**，根目录 `OJ/` 不是仓库。跨仓库任务分别提交。后端当前分支 `yuetsh`，前端当前分支 `main`。
- 后端 lint：`ruff check .` 与 `ruff format .`（E/F/I 规则，行宽 180，双引号）。每次提交前必须通过。
- 前端格式化：`npm fmt`（Prettier）。每次提交前必须跑。
- 后端视图统一继承 `utils.api.APIView`（**不是** DRF 的 APIView），用 `self.success(data)` / `self.error(msg)` 返回。
- 权限装饰器是**类装饰器**（`account/decorators.py`），用法 `@problem_permission_required`，放在 `@validate_serializer(...)` **上面**（参考 `problem/views/admin.py:231-234`）。
- 前端自动导入已配置：Vue API、Vue Router、Pinia、VueUse、Naive UI 组件与 composable（`useMessage`/`useDialog`）、Naive UI 类型（`DataTableColumn`）**无需手动 import**。需要在 `h()` 里用的 Naive UI 组件必须**显式 import**（参考 `src/admin/problem/list.vue:2`）。
- 缓存后端是 `utils.cache.MyRedisCache`（继承 django_redis `RedisCache`），`KEY_PREFIX=""` 且 key 函数是恒等，因此 `cache.delete_pattern("problem_tags:*")` 可直接匹配真实 Redis key。
- **本次不动**：标签分类/分组、学生端多标签筛选（保持单选）、竞赛题目列表的批量打标签、`Contest.tag` 字段（同名但设计完全无关）。

---

## File Structure

### 后端（`OnlineJudge/`）

**新建：**

| 文件 | 职责 |
|---|---|
| `problem/services.py` | 标签解析/查找/缓存失效的共享方法，被 4 处题目保存逻辑和 2 个新接口复用 |
| `problem/migrations/0014_problem_tag_ci_unique.py` | 合并现存重复标签 + 加大小写不敏感唯一约束 |

**修改：**

| 文件 | 改动 |
|---|---|
| `problem/models.py:9-13` | `ProblemTag` 加 `save()` 去空格、加 `Meta.constraints` |
| `problem/serializers.py` | 新增 `TagAdminSerializer`、`EditTagSerializer`、`BatchProblemTagSerializer` |
| `problem/views/admin.py` | 4 处标签 get-or-create 改调 `resolve_tags`；新增 `TagAdminAPI`、`BatchProblemTagAPI` |
| `problem/urls/admin.py` | 注册 `problem/tag`、`problem/batch_tag` 两条路由 |

### 前端（`ojnext/`）

**新建：**

| 文件 | 职责 |
|---|---|
| `src/admin/problem/tags.vue` | 标签管理页：列表、搜索、重命名（撞名自动合并）、删除 |
| `src/admin/problem/components/BatchTagModal.vue` | 题目列表的批量添加/移除标签弹窗 |

**修改：**

| 文件 | 改动 |
|---|---|
| `src/utils/types.ts:102-105` | 新增 `AdminTag` 类型 |
| `src/admin/api.ts` | 新增 4 个标签相关 API 封装 |
| `src/routes.ts` | 加标签管理页路由 |
| `src/shared/layout/admin.vue` | 侧边菜单加入口 + `active` 计算加匹配规则 |
| `src/admin/problem/list.vue` | 加行选择、批量打标签按钮、跳转标签管理页按钮 |

---

## Task 1: 后端标签规范化与数据迁移

**Files:**
- Modify: `OnlineJudge/problem/models.py:9-13`
- Create: `OnlineJudge/problem/migrations/0014_problem_tag_ci_unique.py`

**Interfaces:**
- Produces: `ProblemTag` 保存时自动 `strip()` 名字；数据库层约束 `problem_tag_name_ci_unique` 保证 `Lower(name)` 唯一。后续任务的 `resolve_tags` 依赖这个约束来做「创建冲突则回查」。

- [ ] **Step 1: 修改 `problem/models.py` 的 `ProblemTag`**

把 `problem/models.py:9-13` 整段替换为：

```python
class ProblemTag(models.Model):
    name = models.TextField()

    class Meta:
        db_table = "problem_tag"
        constraints = [
            models.UniqueConstraint(Lower("name"), name="problem_tag_name_ci_unique"),
        ]

    def save(self, *args, **kwargs):
        self.name = (self.name or "").strip()
        super().save(*args, **kwargs)
```

同时在文件顶部 import 区加上 `Lower`。`problem/models.py:1-6` 的 import 区改为：

```python
from django.db import models
from django.db.models.functions import Lower

from account.models import User
from contest.models import Contest
from utils.constants import Difficulty
from utils.models import RichTextField
```

- [ ] **Step 2: 生成迁移文件骨架**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
python manage.py makemigrations problem --name problem_tag_ci_unique
```

预期：生成 `problem/migrations/0014_problem_tag_ci_unique.py`，内容是一条 `AddConstraint`。

如果生成的文件名带了别的后缀，把它重命名成 `0014_problem_tag_ci_unique.py`。

- [ ] **Step 3: 在迁移里补上数据清理**

把 `problem/migrations/0014_problem_tag_ci_unique.py` 整个替换为下面内容（`dependencies` 保持 makemigrations 生成的那一行不变）：

```python
from collections import defaultdict

from django.db import migrations, models
from django.db.models.functions import Lower


def merge_duplicate_tags(apps, schema_editor):
    """加唯一约束前，把「去空格+转小写」后同名的标签合并成一个。

    每组保留关联题目数最多的（并列时保留 id 最小的）作为主标签，
    其余标签下的题目关系转移到主标签后删除。空名标签同样按此规则归并成一条，
    不做删除，留给管理员在标签管理页处理。
    """
    ProblemTag = apps.get_model("problem", "ProblemTag")
    Problem = apps.get_model("problem", "Problem")

    groups = defaultdict(list)
    for tag in ProblemTag.objects.all():
        groups[(tag.name or "").strip().lower()].append(tag)

    for tags in groups.values():
        counts = {tag.id: Problem.objects.filter(tags=tag).count() for tag in tags}
        tags.sort(key=lambda tag: (-counts[tag.id], tag.id))
        primary = tags[0]

        stripped = (primary.name or "").strip()
        if primary.name != stripped:
            primary.name = stripped
            primary.save(update_fields=["name"])

        for duplicate in tags[1:]:
            for problem in Problem.objects.filter(tags=duplicate):
                problem.tags.add(primary)
                problem.tags.remove(duplicate)
            duplicate.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("problem", "0013_remove_problem_io_mode_remove_problem_rule_type_and_more"),
    ]

    operations = [
        migrations.RunPython(merge_duplicate_tags, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="problemtag",
            constraint=models.UniqueConstraint(Lower("name"), name="problem_tag_name_ci_unique"),
        ),
    ]
```

注意：历史模型上没有自定义的 `save()`，所以 `primary.save(update_fields=["name"])` 不会自动 strip，必须像上面那样手动赋值。

- [ ] **Step 4: 造几条脏数据用于验证**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
python manage.py shell -c "
from problem.models import Problem, ProblemTag
p = Problem.objects.filter(contest__isnull=True).first()
a = ProblemTag.objects.create(name='ZzTest')
b = ProblemTag.objects.create(name='zztest')
c = ProblemTag.objects.create(name='  ZZTEST  ')
p.tags.add(a, b, c)
print('before:', ProblemTag.objects.filter(name__icontains='zztest').count(), '题目标签:', list(p.tags.values_list('name', flat=True)))
"
```

预期输出 `before: 3`，题目标签里包含三个变体。

> 注意：模型的 `save()` 会 strip，所以 `'  ZZTEST  '` 落库时已经是 `'ZZTEST'`，这不影响验证——它和另外两个仍然只有大小写差异。

- [ ] **Step 5: 跑迁移**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
python manage.py migrate problem
```

预期：无报错，`Applying problem.0014_problem_tag_ci_unique... OK`。

- [ ] **Step 6: 验证合并结果**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
python manage.py shell -c "
from problem.models import Problem, ProblemTag
print('after:', ProblemTag.objects.filter(name__icontains='zztest').count())
p = Problem.objects.filter(tags__name__icontains='zztest').first()
print('题目标签:', list(p.tags.values_list('name', flat=True)))
try:
    ProblemTag.objects.create(name='zZtEsT')
    print('约束未生效！')
except Exception as e:
    print('约束生效:', type(e).__name__)
"
```

预期：`after: 1`；题目标签里 zztest 只剩一个；最后打印 `约束生效: IntegrityError`。

- [ ] **Step 7: 清理验证数据**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
python manage.py shell -c "
from problem.models import ProblemTag
n, _ = ProblemTag.objects.filter(name__icontains='zztest').delete()
print('已删除', n)
"
```

- [ ] **Step 8: Lint 并提交**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
ruff format . && ruff check .
git add problem/models.py problem/migrations/0014_problem_tag_ci_unique.py
git commit -m "feat(problem): 标签名去空格并加大小写不敏感唯一约束

迁移时先合并已存在的重复标签，题目关系转移到保留的那个。

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 2: 收敛四处重复的标签创建逻辑

**Files:**
- Create: `OnlineJudge/problem/services.py`
- Modify: `OnlineJudge/problem/views/admin.py:251-256`、`313-319`、`367-372`、`437-443`

**Interfaces:**
- Produces: `problem.services.resolve_tags(names) -> list[ProblemTag]`（解析并按需创建，去空格、大小写不敏感复用）、`problem.services.find_tags(names) -> list[ProblemTag]`（只查不创建）、`problem.services.clear_tag_cache() -> None`（清 `problem_tags:*` 缓存）。Task 3、4 都会用到这三个函数。

- [ ] **Step 1: 新建 `problem/services.py`**

```python
from django.core.cache import cache
from django.db import IntegrityError

from utils.constants import CacheKey

from .models import ProblemTag


def clear_tag_cache():
    """标签列表接口按 keyword 分键缓存，标签一变就整批清掉"""
    cache.delete_pattern(f"{CacheKey.problem_tags}:*")


def find_tags(names):
    """按名字大小写不敏感查已有标签，查不到就跳过，不创建"""
    tags = []
    seen = set()
    for raw in names:
        name = (raw or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        tag = ProblemTag.objects.filter(name__iexact=name).first()
        if tag is not None:
            tags.append(tag)
    return tags


def resolve_tags(names):
    """把前端传来的标签名解析成 ProblemTag：去空格、大小写不敏感复用已有标签，没有才新建"""
    tags = []
    seen = set()
    created = False
    for raw in names:
        name = (raw or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        tag = ProblemTag.objects.filter(name__iexact=name).first()
        if tag is None:
            try:
                tag = ProblemTag.objects.create(name=name)
                created = True
            except IntegrityError:
                # 并发下另一个请求刚建好同名标签，回查复用
                tag = ProblemTag.objects.filter(name__iexact=name).first()
                if tag is None:
                    continue
        tags.append(tag)
    if created:
        clear_tag_cache()
    return tags
```

- [ ] **Step 2: 在 `problem/views/admin.py` 换掉四处重复逻辑**

先改 import。`problem/views/admin.py:22` 那行 `from ..models import Problem, ProblemTag` 保持不变（`ProblemTag` 后面 Task 3 还要用），在 `problem/views/admin.py:35` 的 `from ..utils import generate_sql_display` 后面加一行：

```python
from ..services import clear_tag_cache, find_tags, resolve_tags
```

然后把下面四处替换掉（每处都是 `problem.tags.set(resolve_tags(tags))` 一行）：

`ProblemAPI.post`，`problem/views/admin.py:251-256`，把

```python
        for item in tags:
            try:
                tag = ProblemTag.objects.get(name=item)
            except ProblemTag.DoesNotExist:
                tag = ProblemTag.objects.create(name=item)
            problem.tags.add(tag)
        return self.success(ProblemAdminSerializer(problem).data)
```

替换为

```python
        problem.tags.set(resolve_tags(tags))
        return self.success(ProblemAdminSerializer(problem).data)
```

`ProblemAPI.put`，`problem/views/admin.py:313-321`，把

```python
        problem.tags.remove(*problem.tags.all())
        for tag in tags:
            try:
                tag = ProblemTag.objects.get(name=tag)
            except ProblemTag.DoesNotExist:
                tag = ProblemTag.objects.create(name=tag)
            problem.tags.add(tag)

        return self.success()
```

替换为

```python
        problem.tags.set(resolve_tags(tags))
        return self.success()
```

`ContestProblemAPI.post`，`problem/views/admin.py:367-373`，把

```python
        for item in tags:
            try:
                tag = ProblemTag.objects.get(name=item)
            except ProblemTag.DoesNotExist:
                tag = ProblemTag.objects.create(name=item)
            problem.tags.add(tag)
        return self.success(ProblemAdminSerializer(problem).data)
```

替换为

```python
        problem.tags.set(resolve_tags(tags))
        return self.success(ProblemAdminSerializer(problem).data)
```

`ContestProblemAPI.put`，`problem/views/admin.py:437-444`，把

```python
        problem.tags.remove(*problem.tags.all())
        for tag in tags:
            try:
                tag = ProblemTag.objects.get(name=tag)
            except ProblemTag.DoesNotExist:
                tag = ProblemTag.objects.create(name=tag)
            problem.tags.add(tag)
        return self.success()
```

替换为

```python
        problem.tags.set(resolve_tags(tags))
        return self.success()
```

> `clear_tag_cache` 和 `find_tags` 这一步还没有调用点，Task 3、4 才用到。为了让 `ruff check .` 不报 F401 未使用 import，**这一步先只 import `resolve_tags`**：

```python
from ..services import resolve_tags
```

Task 3 和 Task 4 会各自把需要的名字加进这行 import。

- [ ] **Step 3: 验证四处替换后行为一致**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
python manage.py shell -c "
from problem.services import resolve_tags, find_tags
from problem.models import ProblemTag
tags = resolve_tags(['  服务测试  ', '服务测试', 'FUWU', 'fuwu', '', None])
print('解析出', len(tags), '个:', [t.name for t in tags])
print('库里:', ProblemTag.objects.filter(name__in=['服务测试', 'FUWU']).count())
print('find_tags 不创建:', [t.name for t in find_tags(['fUwU', '不存在的标签xyz'])])
ProblemTag.objects.filter(name__in=['服务测试', 'FUWU']).delete()
"
```

预期：`解析出 2 个: ['服务测试', 'FUWU']`；`库里: 2`；`find_tags 不创建: ['FUWU']`。

- [ ] **Step 4: 浏览器验证题目保存流程未被破坏**

启动后端 `python dev.py` 和前端 `npm start`，登录管理后台，编辑任意一道题，在标签处用 `n-dynamic-tags` 输入一个已有标签的大小写变体（例如已有 `循环`，输入 `循环 ` 带空格），保存后重新打开该题。

预期：标签仍然只有一个 `循环`，没有产生新标签。

- [ ] **Step 5: Lint 并提交**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
ruff format . && ruff check .
git add problem/services.py problem/views/admin.py
git commit -m "refactor(problem): 标签创建逻辑收敛到 services.resolve_tags

原本 4 处题目保存逻辑各自复制了一份 get-or-create，且大小写敏感、有竞态。

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 3: 标签管理接口（列表 / 重命名合并 / 删除）

**Files:**
- Modify: `OnlineJudge/problem/serializers.py`
- Modify: `OnlineJudge/problem/views/admin.py`
- Modify: `OnlineJudge/problem/urls/admin.py`

**Interfaces:**
- Consumes: `problem.services.resolve_tags`（Task 2）、`problem.services.clear_tag_cache`（Task 2）
- Produces: `GET/PUT/DELETE /api/admin/problem/tag`。
  - `GET ?keyword=` → `[{id, name, problem_count}]`
  - `PUT {id, name}` → `{merged: bool, id, name, affected_count}`（`merged=true` 时 `id`/`name` 是被合并进的目标标签）
  - `DELETE ?id=` → `null`
  Task 5、6 的前端会按这个契约调用。

- [ ] **Step 1: 在 `problem/serializers.py` 加两个序列化器**

在 `problem/serializers.py:106-109` 的 `TagSerializer` 后面插入：

```python
class TagAdminSerializer(serializers.ModelSerializer):
    problem_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProblemTag
        fields = ["id", "name", "problem_count"]


class EditTagSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField(max_length=32)
```

`serializers.CharField` 默认 `trim_whitespace=True` 且不允许空串，所以「全是空格的名字」在序列化器层就会被挡掉。

- [ ] **Step 2: 在 `problem/views/admin.py` 加 `TagAdminAPI`**

先把 Task 2 加的那行 import 扩成：

```python
from ..services import clear_tag_cache, resolve_tags
```

再把 `problem/views/admin.py:23-34` 的序列化器 import 块里加上 `EditTagSerializer` 和 `TagAdminSerializer`（保持字母序，ruff 的 I 规则会检查）：

```python
from ..serializers import (
    AddContestProblemSerializer,
    ContestProblemMakePublicSerializer,
    CreateContestProblemSerializer,
    CreateProblemSerializer,
    EditContestProblemSerializer,
    EditProblemSerializer,
    EditTagSerializer,
    ProblemAdminListSerializer,
    ProblemAdminSerializer,
    SQLTestCasePreviewSerializer,
    TagAdminSerializer,
    TestCaseUploadForm,
)
```

然后在 `ProblemVisibleAPI`（`problem/views/admin.py:522`）之前插入新类：

```python
class TagAdminAPI(APIView):
    @problem_permission_required
    def get(self, request):
        tags = ProblemTag.objects.annotate(problem_count=Count("problem"))
        keyword = request.GET.get("keyword", "").strip()
        if keyword:
            tags = tags.filter(name__icontains=keyword)
        tags = tags.order_by("-problem_count", "name")
        return self.success(TagAdminSerializer(tags, many=True).data)

    @problem_permission_required
    @validate_serializer(EditTagSerializer)
    def put(self, request):
        data = request.data
        try:
            tag = ProblemTag.objects.get(id=data["id"])
        except ProblemTag.DoesNotExist:
            return self.error("标签不存在，请刷新后重试")

        name = data["name"].strip()
        if not name:
            return self.error("标签名不能为空")

        target = ProblemTag.objects.filter(name__iexact=name).exclude(id=tag.id).first()
        if target is None:
            tag.name = name
            tag.save()
            clear_tag_cache()
            return self.success({"merged": False, "id": tag.id, "name": tag.name, "affected_count": 0})

        # 改名撞上已有标签，视为合并：题目关系转移过去，原标签删除
        affected_count = 0
        for problem in Problem.objects.filter(tags=tag):
            problem.tags.add(target)
            problem.tags.remove(tag)
            affected_count += 1
        tag.delete()
        clear_tag_cache()
        return self.success({"merged": True, "id": target.id, "name": target.name, "affected_count": affected_count})

    @problem_permission_required
    def delete(self, request):
        tag_id = request.GET.get("id")
        if not tag_id:
            return self.error("Invalid parameter, id is required")
        try:
            tag = ProblemTag.objects.get(id=tag_id)
        except ProblemTag.DoesNotExist:
            return self.error("标签不存在，请刷新后重试")
        # 删除标签行的同时，Django 会级联清掉 problem_tags 中间表里的关系
        tag.delete()
        clear_tag_cache()
        return self.success()
```

`Count` 已经在 `problem/views/admin.py:10` import 过了，不用重复加。

- [ ] **Step 3: 注册路由**

`problem/urls/admin.py` 的 import 块加上 `TagAdminAPI`（保持字母序），`urlpatterns` 里在 `path("problem/flowchart", ...)` 之后加一行：

```python
    path("problem/tag", TagAdminAPI.as_view()),
```

- [ ] **Step 4: 验证列表与重命名**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
python manage.py shell -c "
from problem.models import Problem, ProblemTag
p = Problem.objects.filter(contest__isnull=True).first()
a = ProblemTag.objects.create(name='标签甲')
b = ProblemTag.objects.create(name='标签乙')
p.tags.add(a, b)
print('a.id =', a.id, ' b.id =', b.id, ' problem.id =', p.id)
"
```

记下打印出的 `a.id` / `b.id`，然后启动后端 `python dev.py`，用浏览器以超级管理员身份登录后台后，在浏览器控制台执行（Cookie 会自动带上，CSRF token 从 cookie 取）：

```javascript
const csrf = document.cookie.match(/csrftoken=([^;]+)/)[1]
// 列表
await (await fetch('/api/admin/problem/tag?keyword=标签', {headers: {'X-CSRFToken': csrf}})).json()
// 重命名到一个不存在的名字
await (await fetch('/api/admin/problem/tag', {method: 'PUT', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf}, body: JSON.stringify({id: <a.id>, name: '标签丙'})})).json()
// 再把它改成已存在的「标签乙」，应触发合并
await (await fetch('/api/admin/problem/tag', {method: 'PUT', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf}, body: JSON.stringify({id: <a.id>, name: '标签乙'})})).json()
```

预期：列表返回两条带 `problem_count: 1` 的记录；第一次重命名返回 `{merged: false, name: "标签丙", affected_count: 0}`；第二次返回 `{merged: true, name: "标签乙", affected_count: 1}`。

- [ ] **Step 5: 验证合并后数据正确并清理**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
python manage.py shell -c "
from problem.models import Problem, ProblemTag
print('剩余标签:', list(ProblemTag.objects.filter(name__startswith='标签').values_list('name', flat=True)))
p = Problem.objects.filter(tags__name='标签乙').first()
print('题目还挂着标签乙:', p is not None)
ProblemTag.objects.filter(name__startswith='标签').delete()
"
```

预期：`剩余标签: ['标签乙']`（标签甲/丙已被合并删除）；`题目还挂着标签乙: True`。

- [ ] **Step 6: Lint 并提交**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
ruff format . && ruff check .
git add problem/serializers.py problem/views/admin.py problem/urls/admin.py
git commit -m "feat(problem): 新增标签管理接口

列表带题目数，重命名撞名时自动合并并返回受影响题数，删除后清标签缓存。

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 4: 批量打标签接口

**Files:**
- Modify: `OnlineJudge/problem/serializers.py`
- Modify: `OnlineJudge/problem/views/admin.py`
- Modify: `OnlineJudge/problem/urls/admin.py`

**Interfaces:**
- Consumes: `problem.services.resolve_tags`、`find_tags`、`clear_tag_cache`（Task 2）
- Produces: `POST /api/admin/problem/batch_tag`，入参 `{problem_ids: number[], tag_names: string[], action: "add" | "remove"}`，返回 `{problem_count, tag_count}`。Task 7 的前端会按这个契约调用。

- [ ] **Step 1: 在 `problem/serializers.py` 加序列化器**

在 Task 3 加的 `EditTagSerializer` 后面插入：

```python
class BatchProblemTagSerializer(serializers.Serializer):
    problem_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    tag_names = serializers.ListField(child=serializers.CharField(max_length=32), allow_empty=False)
    action = serializers.ChoiceField(choices=["add", "remove"])
```

- [ ] **Step 2: 在 `problem/views/admin.py` 加 `BatchProblemTagAPI`**

把 services 的 import 扩成：

```python
from ..services import clear_tag_cache, find_tags, resolve_tags
```

序列化器 import 块里加上 `BatchProblemTagSerializer`（字母序在 `AddContestProblemSerializer` 之后、`ContestProblemMakePublicSerializer` 之前）。

在 Task 3 新增的 `TagAdminAPI` 后面插入：

```python
class BatchProblemTagAPI(APIView):
    @problem_permission_required
    @validate_serializer(BatchProblemTagSerializer)
    def post(self, request):
        data = request.data
        problems = Problem.objects.filter(id__in=data["problem_ids"], contest_id__isnull=True)
        if not request.user.can_mgmt_all_problem():
            problems = problems.filter(created_by=request.user)
        problems = list(problems)
        if not problems:
            return self.error("没有可操作的题目")

        # 添加时按需新建标签，移除时只认已有标签
        if data["action"] == "add":
            tags = resolve_tags(data["tag_names"])
        else:
            tags = find_tags(data["tag_names"])
        if not tags:
            return self.error("没有匹配的标签")

        for problem in problems:
            if data["action"] == "add":
                problem.tags.add(*tags)
            else:
                problem.tags.remove(*tags)

        # 题目数变化会影响前台标签列表（只展示 problem_count > 0 的）
        clear_tag_cache()
        return self.success({"problem_count": len(problems), "tag_count": len(tags)})
```

不存在的 `problem_id` 会被 `filter(id__in=...)` 自然忽略，符合 spec 的「忽略不存在的 id，正常处理其余」。

- [ ] **Step 3: 注册路由**

`problem/urls/admin.py` 的 import 块加上 `BatchProblemTagAPI`（字母序在最前），`urlpatterns` 里在 `path("problem/tag", ...)` 之后加一行：

```python
    path("problem/batch_tag", BatchProblemTagAPI.as_view()),
```

- [ ] **Step 4: 验证批量添加与移除**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
python manage.py shell -c "
from problem.models import Problem
ids = list(Problem.objects.filter(contest__isnull=True).values_list('id', flat=True)[:3])
print('problem_ids =', ids)
"
```

记下这三个 id，启动后端后在浏览器控制台（已登录超管）执行：

```javascript
const csrf = document.cookie.match(/csrftoken=([^;]+)/)[1]
const post = (body) => fetch('/api/admin/problem/batch_tag', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf}, body: JSON.stringify(body)}).then(r => r.json())
await post({problem_ids: [<id1>, <id2>, <id3>], tag_names: ['批量测试'], action: 'add'})
await post({problem_ids: [<id1>], tag_names: ['批量测试'], action: 'remove'})
```

预期：第一次返回 `{problem_count: 3, tag_count: 1}`；第二次返回 `{problem_count: 1, tag_count: 1}`。

- [ ] **Step 5: 验证结果并清理**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
python manage.py shell -c "
from problem.models import Problem, ProblemTag
print('还挂着批量测试的题目数:', Problem.objects.filter(tags__name='批量测试').count())
ProblemTag.objects.filter(name='批量测试').delete()
"
```

预期：`还挂着批量测试的题目数: 2`（3 个加上，移除了 1 个）。

- [ ] **Step 6: Lint 并提交**

```bash
cd /home/xuyue/Projects/OJ/OnlineJudge
ruff format . && ruff check .
git add problem/serializers.py problem/views/admin.py problem/urls/admin.py
git commit -m "feat(problem): 新增批量给题目添加/移除标签接口

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 5: 前端类型与 API 封装

**Files:**
- Modify: `ojnext/src/utils/types.ts:102-105`
- Modify: `ojnext/src/admin/api.ts`

**Interfaces:**
- Consumes: Task 3 的 `/api/admin/problem/tag`、Task 4 的 `/api/admin/problem/batch_tag`
- Produces: `AdminTag` 类型；`getTagAdminList(keyword)`、`renameTag(id, name)`、`deleteTag(id)`、`batchTagProblems(problemIds, tagNames, action)` 四个函数。Task 6、7 会用。

- [ ] **Step 1: 加 `AdminTag` 类型**

在 `ojnext/src/utils/types.ts:102-105` 的 `Tag` 接口后面插入：

```ts
export interface AdminTag {
  id: number
  name: string
  problem_count: number
}
```

- [ ] **Step 2: 加 API 封装**

`ojnext/src/admin/api.ts` 顶部的类型 import 块里加上 `AdminTag`（字母序在 `AdminProblem` 之后）：

```ts
import type {
  AdminProblem,
  AdminTag,
  Announcement,
  ...
```

在 `getContestProblem`（`src/admin/api.ts:83-85`）之后插入：

```ts
// 标签管理
export function getTagAdminList(keyword = "") {
  return http.get<AdminTag[]>("admin/problem/tag", { params: { keyword } })
}

export function renameTag(id: number, name: string) {
  return http.put<{
    merged: boolean
    id: number
    name: string
    affected_count: number
  }>("admin/problem/tag", { id, name })
}

export function deleteTag(id: number) {
  return http.delete("admin/problem/tag", { params: { id } })
}

export function batchTagProblems(
  problemIds: number[],
  tagNames: string[],
  action: "add" | "remove",
) {
  return http.post<{ problem_count: number; tag_count: number }>(
    "admin/problem/batch_tag",
    { problem_ids: problemIds, tag_names: tagNames, action },
  )
}
```

- [ ] **Step 3: 验证类型检查通过**

```bash
cd /home/xuyue/Projects/OJ/ojnext
npm run build
```

预期：构建成功，无 TS 报错。

- [ ] **Step 4: 格式化并提交**

```bash
cd /home/xuyue/Projects/OJ/ojnext
npm fmt
git add src/utils/types.ts src/admin/api.ts
git commit -m "feat(admin): 标签管理与批量打标签的 API 封装

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 6: 标签管理页面

**Files:**
- Create: `ojnext/src/admin/problem/tags.vue`
- Modify: `ojnext/src/routes.ts`
- Modify: `ojnext/src/shared/layout/admin.vue`

**Interfaces:**
- Consumes: Task 5 的 `getTagAdminList`、`renameTag`、`deleteTag`、`AdminTag`
- Produces: 路由 `admin tag list`（路径 `/admin/problem/tags`）。Task 7 的题目列表页会跳转到它。

- [ ] **Step 1: 新建 `src/admin/problem/tags.vue`**

```vue
<script setup lang="ts">
import { NButton, NFlex, NInput } from "naive-ui"
import type { AdminTag } from "utils/types"
import { deleteTag, getTagAdminList, renameTag } from "../api"

const message = useMessage()
const dialog = useDialog()

const tags = ref<AdminTag[]>([])
const keyword = ref("")
const editingId = ref<number | null>(null)
const editingName = ref("")

const columns: DataTableColumn<AdminTag>[] = [
  { title: "ID", key: "id", width: 80 },
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
        : row.name,
  },
  { title: "题目数", key: "problem_count", width: 100 },
  {
    title: "选项",
    key: "actions",
    width: 200,
    render: (row) =>
      h(NFlex, { size: 8 }, () =>
        editingId.value === row.id
          ? [
              h(
                NButton,
                { size: "small", type: "primary", onClick: () => saveTag(row) },
                () => "保存",
              ),
              h(NButton, { size: "small", onClick: cancelEdit }, () => "取消"),
            ]
          : [
              h(
                NButton,
                { size: "small", onClick: () => startEdit(row) },
                () => "重命名",
              ),
              h(
                NButton,
                {
                  size: "small",
                  type: "error",
                  onClick: () => confirmDelete(row),
                },
                () => "删除",
              ),
            ],
      ),
  },
]

async function listTags() {
  const res = await getTagAdminList(keyword.value)
  tags.value = res.data
}

function startEdit(tag: AdminTag) {
  editingId.value = tag.id
  editingName.value = tag.name
}

function cancelEdit() {
  editingId.value = null
  editingName.value = ""
}

async function saveTag(tag: AdminTag) {
  const name = editingName.value.trim()
  if (!name) {
    message.error("标签名不能为空")
    return
  }
  if (name === tag.name) {
    cancelEdit()
    return
  }
  const res = await renameTag(tag.id, name)
  if (res.data.merged) {
    message.success(
      `已合并到「${res.data.name}」，影响 ${res.data.affected_count} 道题`,
    )
  } else {
    message.success("已重命名")
  }
  cancelEdit()
  listTags()
}

function confirmDelete(tag: AdminTag) {
  dialog.warning({
    title: "删除标签",
    content: `确定删除标签「${tag.name}」吗？当前有 ${tag.problem_count} 道题在使用它，删除后这些题目会失去该标签。`,
    positiveText: "删除",
    negativeText: "取消",
    onPositiveClick: async () => {
      await deleteTag(tag.id)
      message.success("已删除")
      listTags()
    },
  })
}

onMounted(listTags)

watchDebounced(keyword, listTags, { debounce: 500, maxWait: 1000 })
</script>

<template>
  <n-flex class="titleWrapper" justify="space-between">
    <n-flex align="center">
      <h2 class="title">标签管理</h2>
      <n-button @click="$router.push({ name: 'admin problem list' })">
        返回题目列表
      </n-button>
    </n-flex>
    <n-input
      v-model:value="keyword"
      style="width: 200px"
      placeholder="搜索标签"
      clearable
    />
  </n-flex>
  <n-data-table striped :columns="columns" :data="tags" />
</template>

<style scoped>
.titleWrapper {
  margin-bottom: 16px;
}

.title {
  margin: 0;
}
</style>
```

- [ ] **Step 2: 加路由**

`ojnext/src/routes.ts` 的 `admins.children` 里，在 `admin problem create`（`path: "problem/create"`）那一项**之前**插入：

```ts
    {
      path: "problem/tags",
      name: "admin tag list",
      component: () => import("admin/problem/tags.vue"),
      meta: { requiresProblemPermission: true },
    },
```

放在 `problem/create` 之前是为了让静态路径优先于后面的动态段匹配。

- [ ] **Step 3: 侧边菜单加匹配规则**

`ojnext/src/shared/layout/admin.vue` 的 `active` 计算属性（`src/shared/layout/admin.vue:170-184`）里，在 `if (path.startsWith("/admin/problem/stuck")) ...` 那行**后面**加一行：

```ts
  if (path.startsWith("/admin/problem/tags")) return "admin problem list"
```

必须加在 `if (path.startsWith("/admin/problem"))` **之前**，否则不会命中。这里返回 `"admin problem list"` 是让侧边栏「题目」项保持高亮——标签管理不单独占一个菜单项，入口在题目列表页上（Task 7 加）。

- [ ] **Step 4: 浏览器验证**

启动前后端，以超级管理员登录，访问 `/admin/problem/tags`。

预期：
1. 表格按题目数降序列出所有标签（包括题目数为 0 的），侧边栏「题目」高亮
2. 搜索框输入关键字能过滤
3. 点「重命名」，输入一个全新名字保存 → 提示「已重命名」，列表刷新
4. 再点「重命名」，输入一个**已存在**标签的名字（大小写不同也算）保存 → 提示「已合并到「xxx」，影响 N 道题」，列表里原标签消失
5. 点「删除」→ 弹窗显示「当前有 N 道题在使用它」，确认后标签消失

- [ ] **Step 5: 格式化并提交**

```bash
cd /home/xuyue/Projects/OJ/ojnext
npm fmt
npm run build
git add src/admin/problem/tags.vue src/routes.ts src/shared/layout/admin.vue
git commit -m "feat(admin): 标签管理页

支持搜索、重命名（撞名自动合并并提示影响题数）、删除（二次确认）。

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 7: 题目列表批量打标签

**Files:**
- Create: `ojnext/src/admin/problem/components/BatchTagModal.vue`
- Modify: `ojnext/src/admin/problem/list.vue`

**Interfaces:**
- Consumes: Task 5 的 `batchTagProblems`、`getTagAdminList`、`AdminTag`；Task 6 的路由名 `admin tag list`
- Produces: 无（终端任务）

- [ ] **Step 1: 新建 `src/admin/problem/components/BatchTagModal.vue`**

```vue
<script setup lang="ts">
import type { AdminTag } from "utils/types"
import { batchTagProblems, getTagAdminList } from "admin/api"

interface Props {
  show: boolean
  problemIds: number[]
  action: "add" | "remove"
}

const props = defineProps<Props>()
const emit = defineEmits<{
  "update:show": [value: boolean]
  done: []
}>()

const message = useMessage()

const tags = ref<AdminTag[]>([])
const selected = ref<string[]>([])
const newTags = ref<string[]>([])

const title = computed(() =>
  props.action === "add" ? "批量添加标签" : "批量移除标签",
)

const selectedSet = computed(() => new Set(selected.value))

const names = computed(() =>
  props.action === "add"
    ? Array.from(new Set([...selected.value, ...newTags.value]))
    : selected.value,
)

function toggleTag(name: string) {
  const set = new Set(selected.value)
  if (set.has(name)) set.delete(name)
  else set.add(name)
  selected.value = Array.from(set)
}

async function listTags() {
  const res = await getTagAdminList()
  tags.value = res.data
}

function close() {
  emit("update:show", false)
}

async function submit() {
  if (!names.value.length) {
    message.error("请先选择标签")
    return
  }
  const res = await batchTagProblems(
    props.problemIds,
    names.value,
    props.action,
  )
  const verb = props.action === "add" ? "添加" : "移除"
  message.success(
    `已为 ${res.data.problem_count} 道题${verb} ${res.data.tag_count} 个标签`,
  )
  close()
  emit("done")
}

watch(
  () => props.show,
  (show) => {
    if (!show) return
    selected.value = []
    newTags.value = []
    listTags()
  },
)
</script>

<template>
  <n-modal
    :show="show"
    preset="card"
    :title="title"
    style="width: 600px"
    :mask-closable="false"
    @close="close"
  >
    <n-flex vertical size="large">
      <div>已选中 {{ problemIds.length }} 道题目</div>
      <n-flex size="small">
        <n-tag
          v-for="tag in tags"
          :key="tag.id"
          checkable
          :checked="selectedSet.has(tag.name)"
          @update:checked="toggleTag(tag.name)"
        >
          {{ tag.name }}（{{ tag.problem_count }}）
        </n-tag>
      </n-flex>
      <n-dynamic-tags v-if="action === 'add'" v-model:value="newTags" />
      <n-flex justify="end">
        <n-button @click="close">取消</n-button>
        <n-button type="primary" @click="submit">确定</n-button>
      </n-flex>
    </n-flex>
  </n-modal>
</template>
```

移除模式下不显示 `n-dynamic-tags`——后端 `find_tags` 只认已有标签，让用户手输新名字没有意义。

- [ ] **Step 2: 改 `src/admin/problem/list.vue` 的 script**

在 `src/admin/problem/list.vue:13` 的 `import AuthorSelect from "shared/components/AuthorSelect.vue"` 后面加：

```ts
import type { DataTableRowKey } from "naive-ui"
import BatchTagModal from "./components/BatchTagModal.vue"
```

在 `const problems = ref<AdminProblemFiltered[]>([])`（`src/admin/problem/list.vue:37`）后面加：

```ts
const selectedRowKeys = ref<DataTableRowKey[]>([])
const batchTagAction = ref<"add" | "remove">("add")
const [showBatchTag, toggleBatchTag] = useToggle(false)

const selectedProblemIds = computed(() =>
  selectedRowKeys.value.map((key) => Number(key)),
)

const rowKey = (row: AdminProblemFiltered) => row.id

function chooseProblems(rowKeys: DataTableRowKey[]) {
  selectedRowKeys.value = rowKeys
}

function openBatchTag(action: "add" | "remove") {
  batchTagAction.value = action
  toggleBatchTag(true)
}

function onBatchTagDone() {
  selectedRowKeys.value = []
  listProblems()
}
```

用 `selectedProblemIds` 这个 computed 把 `DataTableRowKey[]` 转成 `number[]`，避免在模板里写类型断言。

把 `columns` 从常量数组改成 computed，让复选框列只在普通题目列表出现——比赛题目列表本次不接批量操作，不该显示无用的复选框。

把 `const columns: DataTableColumn<AdminProblemFiltered>[] = [`（`src/admin/problem/list.vue:60`）改成：

```ts
const baseColumns: DataTableColumn<AdminProblemFiltered>[] = [
```

数组结尾 `]`（`src/admin/problem/list.vue:142`）之后加：

```ts
const columns = computed<DataTableColumn<AdminProblemFiltered>[]>(() =>
  isContestProblemList.value
    ? baseColumns
    : [{ type: "selection" }, ...baseColumns],
)
```

- [ ] **Step 3: 改 `src/admin/problem/list.vue` 的 template**

在标题栏左侧那组按钮里（`src/admin/problem/list.vue:209-214` 的「年度趋势」按钮之后）加一个入口：

```vue
      <n-button
        v-if="!isContestProblemList"
        @click="$router.push({ name: 'admin tag list' })"
      >
        标签管理
      </n-button>
```

在右侧那组（`<n-flex>` 开头，`src/admin/problem/list.vue:216`）的最前面加两个批量按钮：

```vue
      <template v-if="!isContestProblemList && selectedProblemIds.length">
        <n-button type="primary" @click="openBatchTag('add')">
          添加标签（{{ selectedProblemIds.length }}）
        </n-button>
        <n-button @click="openBatchTag('remove')">移除标签</n-button>
      </template>
```

`columns` 现在是 computed，模板里 `:columns="columns"` 写法不变，无需调整。

把表格那行（`src/admin/problem/list.vue:241`）：

```vue
  <n-data-table striped :columns="columns" :data="problems" />
```

改成：

```vue
  <n-data-table
    striped
    :columns="columns"
    :data="problems"
    :row-key="rowKey"
    @update:checked-row-keys="chooseProblems"
  />
```

在 `<Modal ... />`（`src/admin/problem/list.vue:247-252`）之后加：

```vue
  <BatchTagModal
    v-model:show="showBatchTag"
    :problem-ids="selectedProblemIds"
    :action="batchTagAction"
    @done="onBatchTagDone"
  />
```

- [ ] **Step 4: 浏览器验证**

启动前后端，以超级管理员登录，访问 `/admin/problem/list`。

预期：
1. 每行左侧出现复选框，勾选后右上角出现「添加标签（N）」和「移除标签」按钮
2. 点「添加标签」→ 弹窗显示「已选中 N 道题目」、可勾选的已有标签、可输入新标签的输入框
3. 勾一个标签点确定 → 提示「已为 N 道题添加 1 个标签」，表格刷新后这些题目的标签列出现该标签，选中状态清空
4. 再勾选其中一道题，点「移除标签」→ 弹窗**不显示**新标签输入框；勾同一个标签确定 → 该题标签列里它消失了
5. 点标题栏「标签管理」能跳到标签管理页
6. 比赛题目列表页（`/admin/contest/:id/problem/list`）**不**出现复选框列、批量按钮和「标签管理」按钮

- [ ] **Step 5: 验证前台标签筛选同步更新**

打开前台题目列表页（`/`），检查左侧标签筛选栏。

预期：Step 4 中新加的标签立即出现在筛选栏里（不需要等一小时缓存过期）——这验证了 Task 4 的 `clear_tag_cache()` 生效。

- [ ] **Step 6: 格式化并提交**

```bash
cd /home/xuyue/Projects/OJ/ojnext
npm fmt
npm run build
git add src/admin/problem/components/BatchTagModal.vue src/admin/problem/list.vue
git commit -m "feat(admin): 题目列表支持批量添加/移除标签

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
