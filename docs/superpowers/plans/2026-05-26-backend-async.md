# Backend Async Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current backend async work correct first, then establish safe patterns for expanding async views without changing API response shapes.

**Architecture:** Keep the existing custom `APIView`/DRF serializer stack. Add async-safe tests and helpers around `AsyncAPIView`, explicitly preload serializer relations in converted endpoints, and use `sync_to_async(..., thread_sensitive=True)` for synchronous serializer/cache/helper code that remains inside async views.

**Tech Stack:** Django 6.0.4, custom class-based API views, Django async ORM, DRF serializers, PostgreSQL, Redis cache, Channels ASGI.

---

## Async Rules For This Repository

1. Async conversion is valid only when the endpoint preserves URL, method, status code, JSON envelope, and permission behavior.
2. Every async view that serializes model instances must either preload all serializer relations with `select_related()` / `prefetch_related()` or run serializer `.data` through a sync boundary.
3. `asyncio.gather()` is only for independent reads. Do not use it around writes that depend on ordering or transaction semantics.
4. Keep file upload/download, SMTP, test-case pruning, judge heartbeat mutation paths, and contest permission-heavy flows sync until the async decorator and middleware work is complete.
5. Current sync `MiddlewareMixin` middleware means ASGI requests still cross sync boundaries. The first async milestone is correctness and latency cleanup, not a full event-loop purity claim.

---

### Task 1: Add Regression Coverage For Converted Async Detail Views

**Files:**
- Create: `utils/test_async_view_regressions.py`

- [ ] **Step 1: Write failing regression tests**

Create `utils/test_async_view_regressions.py`:

```python
from datetime import timedelta

from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.test import AsyncClient, TestCase
from django.utils import timezone

from account.models import UserProfile
from announcement.models import Announcement
from contest.models import Contest
from flowchart.models import FlowchartSubmission
from problem.models import Problem, ProblemRuleType
from utils.constants import ContestRuleType, Difficulty

User = get_user_model()


def make_user(username="async_user"):
    user = User.objects.create(username=username, email=f"{username}@example.com")
    user.set_password("pass1234")
    user.save()
    UserProfile.objects.create(user=user)
    return user


def make_problem(user):
    return Problem.objects.create(
        _id="ASYNC001",
        title="Async Problem",
        description="desc",
        input_description="input",
        output_description="output",
        samples=[],
        test_case_id="async-test-case",
        test_case_score=[],
        hint="",
        languages=["Python3"],
        template={},
        created_by=user,
        time_limit=1000,
        memory_limit=128,
        rule_type=ProblemRuleType.ACM,
        difficulty=Difficulty.LOW,
        share_submission=False,
        allow_flowchart=True,
        show_flowchart=True,
    )


class AsyncConvertedViewRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_user()
        cls.announcement = Announcement.objects.create(
            title="Async Announcement",
            content="content",
            tag="notice",
            visible=True,
            top=False,
            created_by=cls.user,
        )
        cls.contest = Contest.objects.create(
            title="Async Contest",
            description="contest desc",
            tag="weekly",
            real_time_rank=True,
            password=None,
            rule_type=ContestRuleType.ACM,
            start_time=timezone.now() - timedelta(hours=1),
            end_time=timezone.now() + timedelta(hours=1),
            created_by=cls.user,
            visible=True,
            allowed_ip_ranges=[],
        )
        cls.problem = make_problem(cls.user)
        cls.flowchart_submission = FlowchartSubmission.objects.create(
            user=cls.user,
            problem=cls.problem,
            mermaid_code="graph TD\nA-->B",
            flowchart_data={},
        )

    async def test_announcement_detail_serializes_created_by(self):
        response = await AsyncClient().get(f"/api/announcement?id={self.announcement.id}")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body["error"])
        self.assertEqual(body["data"]["created_by"]["username"], self.user.username)

    async def test_contest_detail_serializes_created_by(self):
        response = await AsyncClient().get(f"/api/contest?id={self.contest.id}")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body["error"])
        self.assertEqual(body["data"]["created_by"]["username"], self.user.username)

    async def test_flowchart_detail_serializes_user_and_problem(self):
        client = AsyncClient()
        await sync_to_async(client.force_login)(self.user)

        response = await client.get(f"/api/flowchart/submission?id={self.flowchart_submission.id}")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body["error"])
        self.assertEqual(body["data"]["username"], self.user.username)
        self.assertEqual(body["data"]["problem"], self.problem.id)
```

- [ ] **Step 2: Run the regression tests**

Run:

```bash
rtk uv run python manage.py test utils.test_async_view_regressions -v 2
```

Expected before Task 2: at least one test returns `server-error` or raises async-unsafe lazy relation access.

- [ ] **Step 3: Commit the failing tests**

Run:

```bash
rtk git add utils/test_async_view_regressions.py
rtk git commit -m "test: cover async view serialization regressions"
```

---

### Task 2: Preload Relations For Already Converted Async Detail Views

**Files:**
- Modify: `announcement/views/oj.py`
- Modify: `contest/views/oj.py`
- Modify: `flowchart/views/oj.py`

- [ ] **Step 1: Fix announcement detail relation loading**

In `announcement/views/oj.py`, replace the detail query with:

```python
announcement = await (
    Announcement.objects.select_related("created_by")
    .filter(id=id, visible=True)
    .afirst()
)
if announcement is None:
    raise Announcement.DoesNotExist
```

- [ ] **Step 2: Fix contest detail relation loading**

In `contest/views/oj.py`, replace the detail query with:

```python
contest = await (
    Contest.objects.select_related("created_by")
    .filter(id=id, visible=True)
    .afirst()
)
if contest is None:
    raise Contest.DoesNotExist
```

- [ ] **Step 3: Fix flowchart submission detail relation loading**

In `flowchart/views/oj.py`, update `FlowchartSubmissionAPI.get()`:

```python
submission = await (
    FlowchartSubmission.objects.select_related("user", "problem")
    .filter(id=submission_id)
    .afirst()
)
if submission is None:
    raise FlowchartSubmission.DoesNotExist
```

- [ ] **Step 4: Fix flowchart retry permission relation loading**

In `flowchart/views/oj.py`, update `FlowchartSubmissionRetryAPI.post()`:

```python
submission = await (
    FlowchartSubmission.objects.select_related("problem")
    .filter(id=submission_id)
    .afirst()
)
if submission is None:
    raise FlowchartSubmission.DoesNotExist
```

- [ ] **Step 5: Fix flowchart completed-detail relation loading**

In `flowchart/views/oj.py`, update `FlowchartSubmissionDetailAPI.get()` before serialization:

```python
submissions = (
    FlowchartSubmission.objects.select_related("user", "problem")
    .filter(
        user=request.user,
        problem=problem,
        status=FlowchartSubmissionStatus.COMPLETED,
    )
    .order_by("create_time")
)
```

- [ ] **Step 6: Run the regression tests**

Run:

```bash
rtk uv run python manage.py test utils.test_async_view_regressions -v 2
```

Expected: all tests pass.

- [ ] **Step 7: Run Django system checks**

Run:

```bash
rtk uv run python manage.py check
```

Expected: `System check identified no issues`.

- [ ] **Step 8: Commit relation fixes**

Run:

```bash
rtk git add announcement/views/oj.py contest/views/oj.py flowchart/views/oj.py
rtk git commit -m "fix: preload relations in async detail views"
```

---

### Task 3: Add Async Serialization Helpers To `AsyncAPIView`

**Files:**
- Modify: `utils/api/api.py`
- Modify: `utils/test_async_api.py`

- [ ] **Step 1: Write tests for async serialization helper**

Create `utils/test_async_api.py`:

```python
import json

from django.test import AsyncRequestFactory, SimpleTestCase

from utils.api import AsyncAPIView, serializers, validate_serializer


class PayloadSerializer(serializers.Serializer):
    name = serializers.CharField()


class EchoSerializer(serializers.Serializer):
    name = serializers.CharField()


class AsyncValidatedEchoView(AsyncAPIView):
    @validate_serializer(PayloadSerializer)
    async def post(self, request):
        return self.success({"name": request.data["name"]})


class AsyncSerializationHelperTests(SimpleTestCase):
    async def test_validate_serializer_supports_async_view_methods(self):
        request = AsyncRequestFactory().post(
            "/api/echo",
            data=json.dumps({"name": "alice"}),
            content_type="application/json",
        )

        response = await AsyncValidatedEchoView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["error"], None)
        self.assertEqual(response.data["data"], {"name": "alice"})

    async def test_async_serialize_data_returns_serializer_data(self):
        view = AsyncAPIView()

        data = await view.async_serialize_data(
            EchoSerializer,
            [{"name": "alice"}, {"name": "bob"}],
            many=True,
        )

        self.assertEqual(data, [{"name": "alice"}, {"name": "bob"}])
```

- [ ] **Step 2: Run helper tests and confirm failure**

Run:

```bash
rtk uv run python manage.py test utils.test_async_api -v 2
```

Expected before implementation: `AttributeError: 'AsyncAPIView' object has no attribute 'async_serialize_data'`.

- [ ] **Step 3: Add `sync_to_async` import**

In `utils/api/api.py`, add:

```python
from asgiref.sync import sync_to_async
```

- [ ] **Step 4: Add serializer helper methods**

In `AsyncAPIView`, before `async_paginate_data()`, add:

```python
    def serialize_data(self, object_serializer, data, **kwargs):
        return object_serializer(data, **kwargs).data

    async def async_serialize_data(self, object_serializer, data, **kwargs):
        return await sync_to_async(
            self.serialize_data,
            thread_sensitive=True,
        )(object_serializer, data, **kwargs)
```

- [ ] **Step 5: Use helper inside async pagination**

In `AsyncAPIView.async_paginate_data()`, replace:

```python
if object_serializer:
    results = object_serializer(results, many=True, context={"request": request}).data
```

with:

```python
if object_serializer:
    results = await self.async_serialize_data(
        object_serializer,
        results,
        many=True,
        context={"request": request},
    )
```

- [ ] **Step 6: Run helper and regression tests**

Run:

```bash
rtk uv run python manage.py test utils.test_async_api utils.test_async_view_regressions -v 2
```

Expected: all tests pass.

- [ ] **Step 7: Commit async serializer helper**

Run:

```bash
rtk git add utils/api/api.py utils/test_async_api.py
rtk git commit -m "feat: add async serializer helper"
```

---

### Task 4: Add Cache Helpers For Async Views

**Files:**
- Create: `utils/async_helpers.py`
- Create: `utils/test_async_helpers.py`
- Modify: `problem/views/oj.py`
- Modify: `comment/views/oj.py`

- [ ] **Step 1: Write cache helper tests**

Create `utils/test_async_helpers.py`:

```python
from django.test import SimpleTestCase, override_settings

from utils.async_helpers import async_cache_delete, async_cache_get, async_cache_set


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "async-helper-tests",
        }
    }
)
class AsyncCacheHelperTests(SimpleTestCase):
    async def test_async_cache_round_trip(self):
        await async_cache_set("async:key", {"value": 1}, 30)

        value = await async_cache_get("async:key")

        self.assertEqual(value, {"value": 1})

    async def test_async_cache_delete(self):
        await async_cache_set("async:delete", "present", 30)
        await async_cache_delete("async:delete")

        value = await async_cache_get("async:delete")

        self.assertIsNone(value)
```

- [ ] **Step 2: Run tests and confirm import failure**

Run:

```bash
rtk uv run python manage.py test utils.test_async_helpers -v 2
```

Expected before implementation: `ModuleNotFoundError: No module named 'utils.async_helpers'`.

- [ ] **Step 3: Create async cache helpers**

Create `utils/async_helpers.py`:

```python
from asgiref.sync import sync_to_async
from django.core.cache import cache


async def async_cache_get(key, default=None):
    return await sync_to_async(cache.get, thread_sensitive=True)(key, default)


async def async_cache_set(key, value, timeout=None):
    return await sync_to_async(cache.set, thread_sensitive=True)(key, value, timeout)


async def async_cache_delete(key):
    return await sync_to_async(cache.delete, thread_sensitive=True)(key)
```

- [ ] **Step 4: Convert async problem cache calls**

In `problem/views/oj.py`, add:

```python
from utils.async_helpers import async_cache_get, async_cache_set
```

In `ProblemTagAPI.get()`, replace:

```python
cached = cache.get(cache_key)
```

with:

```python
cached = await async_cache_get(cache_key)
```

Replace:

```python
cache.set(cache_key, data, 3600)
```

with:

```python
await async_cache_set(cache_key, data, 3600)
```

- [ ] **Step 5: Convert async comment cache calls**

In `comment/views/oj.py`, add:

```python
from utils.async_helpers import async_cache_delete, async_cache_get, async_cache_set
```

In `CommentAPI.post()`, replace:

```python
cache.delete(f"{CacheKey.comment_stats}:{problem.id}")
```

with:

```python
await async_cache_delete(f"{CacheKey.comment_stats}:{problem.id}")
```

In `CommentStatisticsAPI.get()`, replace `cache.get()` and `cache.set()` with:

```python
cached = await async_cache_get(cache_key)
```

and:

```python
await async_cache_set(cache_key, data, 3600)
```

- [ ] **Step 6: Run helper and targeted async tests**

Run:

```bash
rtk uv run python manage.py test utils.test_async_helpers utils.test_async_api utils.test_async_view_regressions -v 2
```

Expected: all tests pass.

- [ ] **Step 7: Commit cache helper work**

Run:

```bash
rtk git add utils/async_helpers.py utils/test_async_helpers.py problem/views/oj.py comment/views/oj.py
rtk git commit -m "feat: add async cache helpers"
```

---

### Task 5: Make Permission Decorators Async-Aware Before More Conversions

**Files:**
- Modify: `account/decorators.py`
- Create: `account/test_async_decorators.py`

- [ ] **Step 1: Write tests for async `login_required`**

Create `account/test_async_decorators.py`:

```python
from django.contrib.auth.models import AnonymousUser
from django.test import AsyncRequestFactory, SimpleTestCase

from account.decorators import login_required
from utils.api import AsyncAPIView


class DisabledUser:
    is_authenticated = True
    is_disabled = True


class ActiveUser:
    is_authenticated = True
    is_disabled = False


class ProtectedAsyncView(AsyncAPIView):
    @login_required
    async def get(self, request):
        return self.success("ok")


class AsyncPermissionDecoratorTests(SimpleTestCase):
    async def test_async_login_required_allows_active_user(self):
        request = AsyncRequestFactory().get("/api/protected")
        request.user = ActiveUser()

        response = await ProtectedAsyncView.as_view()(request)

        self.assertEqual(response.data["error"], None)
        self.assertEqual(response.data["data"], "ok")

    async def test_async_login_required_rejects_anonymous_user(self):
        request = AsyncRequestFactory().get("/api/protected")
        request.user = AnonymousUser()

        response = await ProtectedAsyncView.as_view()(request)

        self.assertEqual(response.data["error"], "permission-denied")
        self.assertEqual(response.data["data"], "Please login first")

    async def test_async_login_required_rejects_disabled_user(self):
        request = AsyncRequestFactory().get("/api/protected")
        request.user = DisabledUser()

        response = await ProtectedAsyncView.as_view()(request)

        self.assertEqual(response.data["error"], "permission-denied")
        self.assertEqual(response.data["data"], "Your account is disabled")
```

- [ ] **Step 2: Run decorator tests**

Run:

```bash
rtk uv run python manage.py test account.test_async_decorators -v 2
```

Expected before implementation: this may pass because `AsyncAPIView.dispatch()` awaits returned coroutine. Keep the test anyway as a contract before refactoring.

- [ ] **Step 3: Refactor `BasePermissionDecorator` with explicit async path**

In `account/decorators.py`, add:

```python
import inspect
```

Replace `BasePermissionDecorator.__get__()` with:

```python
    def __get__(self, obj, obj_type):
        if inspect.iscoroutinefunction(self.func):
            return functools.partial(self._async_call, obj)
        return functools.partial(self.__call__, obj)
```

Add this method to `BasePermissionDecorator`:

```python
    async def _async_call(self, *args, **kwargs):
        self.request = args[1]

        if self.check_permission():
            if self.request.user.is_disabled:
                return self.error("Your account is disabled")
            return await self.func(*args, **kwargs)
        return self.error("Please login first")
```

- [ ] **Step 4: Run decorator and async view tests**

Run:

```bash
rtk uv run python manage.py test account.test_async_decorators utils.test_async_api utils.test_async_view_regressions -v 2
```

Expected: all tests pass.

- [ ] **Step 5: Commit decorator refactor**

Run:

```bash
rtk git add account/decorators.py account/test_async_decorators.py
rtk git commit -m "refactor: make permission decorators async-aware"
```

---

### Task 6: Convert One Endpoint Family At A Time

**Files:**
- Modify only the endpoint family being converted in each batch.
- Add or update tests in the same app, using `AsyncClient` for converted URLs.

- [ ] **Step 1: Choose the next low-risk batch**

Use this order:

```text
1. Pure public GET list/detail endpoints already close to async:
   - announcement list/detail
   - contest list/detail
   - problem tag/list/detail

2. Authenticated read-only list endpoints:
   - message list
   - submission list
   - flowchart list/detail/current

3. Simple create/update endpoints with no contest permission decorator:
   - message create
   - comment create
   - flowchart retry/create
```

- [ ] **Step 2: For each endpoint, write one async smoke test**

Use this template and replace the URL and assertions with the exact endpoint response:

```python
from django.test import AsyncClient, TestCase


class EndpointAsyncSmokeTests(TestCase):
    async def test_endpoint_returns_success_envelope(self):
        response = await AsyncClient().get("/api/endpoint?limit=10")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("error", body)
        self.assertIn("data", body)
```

- [ ] **Step 3: Convert ORM access only where async ORM exists**

Use these replacements:

```python
obj = await Model.objects.aget(id=id)
count = await queryset.acount()
first = await queryset.afirst()
last = await queryset.alast()
items = [item async for item in queryset[offset:offset + limit]]
created = await Model.objects.acreate(field=value)
await instance.asave(update_fields=["field"])
```

- [ ] **Step 4: Keep sync-only helpers behind `sync_to_async`**

Use this pattern:

```python
from asgiref.sync import sync_to_async

result = await sync_to_async(sync_helper, thread_sensitive=True)(arg1, arg2)
```

- [ ] **Step 5: Run targeted app tests and system check after each batch**

Run:

```bash
rtk uv run python manage.py test <app_label> -v 2
rtk uv run python manage.py check
```

Expected: targeted tests pass and system check reports no issues.

- [ ] **Step 6: Commit each endpoint family separately**

Run:

```bash
rtk git add <changed-files>
rtk git commit -m "refactor: async <endpoint-family> endpoints"
```

---

### Task 7: Audit Middleware Before Claiming Full Async Benefit

**Files:**
- Modify: `account/middleware.py`
- Add tests only for behavior that changes.

- [ ] **Step 1: Record current sync middleware boundaries**

Before changing middleware, note these current sync classes:

```text
account.middleware.APITokenAuthMiddleware
account.middleware.AdminRoleRequiredMiddleware
account.middleware.SessionRecordMiddleware
```

- [ ] **Step 2: Keep middleware sync during endpoint correctness work**

Do not convert middleware in the same commit as endpoint conversions. Middleware affects every request and needs its own review.

- [ ] **Step 3: If middleware conversion is pursued, convert one class per commit**

Use Django new-style middleware with explicit sync and async handling. `__acall__` is a local helper; `__call__` dispatches to it when Django passes an async `get_response`:

```python
from asgiref.sync import iscoroutinefunction, markcoroutinefunction, sync_to_async


class ExampleMiddleware:
    sync_capable = True
    async_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        self.is_async = iscoroutinefunction(get_response)
        if self.is_async:
            markcoroutinefunction(self)

    def __call__(self, request):
        if self.is_async:
            return self.__acall__(request)
        response = self.process_request(request)
        if response is not None:
            return response
        return self.get_response(request)

    async def __acall__(self, request):
        response = await self.aprocess_request(request)
        if response is not None:
            return response
        return await self.get_response(request)

    def process_request(self, request):
        return None

    async def aprocess_request(self, request):
        return await sync_to_async(self.process_request, thread_sensitive=True)(request)
```

- [ ] **Step 4: Run full backend test command after middleware work**

Run:

```bash
rtk uv run python manage.py test -v 2
rtk uv run python manage.py check
```

Expected: all tests pass and system check reports no issues.

---

## Definition Of Done

- `rtk uv run python manage.py check` passes.
- Async regression tests cover converted detail serializers that depend on FK relations.
- Converted async views do not call DRF serializer `.data` directly unless the data is primitive and relation-free.
- Cache access from async views uses async helper wrappers.
- New endpoint conversions are committed in endpoint-family-sized commits.
- No file upload/download, SMTP, judge heartbeat, test-case prune, or contest permission-heavy endpoint is converted without a separate focused plan.
