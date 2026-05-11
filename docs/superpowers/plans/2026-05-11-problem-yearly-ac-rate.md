# Problem Yearly AC Rate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `GET /api/problem/yearly_ac` endpoint returning per-year AC stats for a single problem, and display results as a line chart below the existing pie chart on the problem info page.

**Architecture:** Backend adds `ProblemYearlyACRateAPI` to `problem/views/oj.py` using Django ORM `ExtractYear` + `Count(filter=...)` aggregation, cached in Redis. Frontend adds a `ProblemYearlyChart.vue` Line chart component and wires it into `ProblemInfo.vue`.

**Tech Stack:** Django 6, PostgreSQL, Redis, `django.db.models.functions.ExtractYear`; Vue 3, TypeScript, vue-chartjs, chart.js

---

### Task 1: Add CacheKey constant and write failing test

**Files:**
- Modify: `OnlineJudge/utils/constants.py`
- Create: `OnlineJudge/problem/tests.py`

- [ ] **Step 1: Add `problem_yearly_ac` to `CacheKey`**

In `OnlineJudge/utils/constants.py`, add one line to `CacheKey`:

```python
class CacheKey:
    waiting_queue = "waiting_queue"
    contest_rank_cache = "contest_rank_cache"
    website_config = "website_config"
    problem_authors = "problem_authors"
    problem_tags = "problem_tags"
    comment_stats = "comment_stats"
    user_activity_rank = "user_activity_rank"
    problem_yearly_ac = "problem_yearly_ac"   # ← add this line
```

- [ ] **Step 2: Write failing tests**

Create `OnlineJudge/problem/tests.py`:

```python
from datetime import datetime, UTC

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from problem.models import Problem, ProblemRuleType
from submission.models import JudgeStatus, Submission
from utils.constants import Difficulty

User = get_user_model()


def make_user():
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="pass",
    )


def make_problem(user, _id="P001"):
    return Problem.objects.create(
        _id=_id,
        title="Test Problem",
        description="",
        input_description="",
        output_description="",
        samples=[],
        test_case_id="abc123",
        test_case_score=[],
        languages=["Python3"],
        template={},
        created_by=user,
        time_limit=1000,
        memory_limit=256,
        rule_type=ProblemRuleType.ACM,
        difficulty=Difficulty.LOW,
    )


def make_submission(problem, result, year):
    sub = Submission.objects.create(
        problem=problem,
        user_id=1,
        username="testuser",
        code="print(1)",
        result=result,
        language="Python3",
    )
    # auto_now_add cannot be passed to create(); update afterward
    Submission.objects.filter(id=sub.id).update(
        create_time=datetime(year, 6, 1, tzinfo=UTC)
    )
    return sub


class ProblemYearlyACRateAPITest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user()
        self.problem = make_problem(self.user)
        # 2023: 3 judged, 1 AC  → ac_rate = 33.33
        make_submission(self.problem, JudgeStatus.ACCEPTED, 2023)
        make_submission(self.problem, JudgeStatus.WRONG_ANSWER, 2023)
        make_submission(self.problem, JudgeStatus.WRONG_ANSWER, 2023)
        # 2024: 2 judged, 2 AC  → ac_rate = 100.0
        make_submission(self.problem, JudgeStatus.ACCEPTED, 2024)
        make_submission(self.problem, JudgeStatus.ACCEPTED, 2024)

    def test_missing_problem_id_returns_error(self):
        res = self.client.get("/api/problem/yearly_ac")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["error"], "error")

    def test_nonexistent_problem_returns_error(self):
        res = self.client.get("/api/problem/yearly_ac?problem_id=NOPE")
        self.assertEqual(res.json()["error"], "error")

    def test_returns_yearly_data_sorted_by_year(self):
        res = self.client.get(f"/api/problem/yearly_ac?problem_id={self.problem._id}")
        body = res.json()
        self.assertIsNone(body["error"])
        rows = body["data"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["year"], 2023)
        self.assertEqual(rows[0]["total"], 3)
        self.assertEqual(rows[0]["accepted"], 1)
        self.assertAlmostEqual(rows[0]["ac_rate"], 33.33, places=1)
        self.assertEqual(rows[1]["year"], 2024)
        self.assertEqual(rows[1]["total"], 2)
        self.assertEqual(rows[1]["accepted"], 2)
        self.assertAlmostEqual(rows[1]["ac_rate"], 100.0)

    def test_excludes_pending_and_judging(self):
        make_submission(self.problem, JudgeStatus.PENDING, 2023)
        make_submission(self.problem, JudgeStatus.JUDGING, 2023)
        res = self.client.get(f"/api/problem/yearly_ac?problem_id={self.problem._id}")
        rows = res.json()["data"]
        # 2023 total must stay 3 (pending/judging excluded)
        self.assertEqual(rows[0]["total"], 3)
```

- [ ] **Step 3: Run test to confirm it fails**

```bash
cd OnlineJudge && python manage.py test problem.tests.ProblemYearlyACRateAPITest -v 2
```

Expected: Failure with `404` or `ImportError` — endpoint does not exist yet.

---

### Task 2: Implement view and register URL

**Files:**
- Modify: `OnlineJudge/problem/views/oj.py`
- Modify: `OnlineJudge/problem/urls/oj.py`

- [ ] **Step 1: Add `ExtractYear` import to `problem/views/oj.py`**

At the top of `OnlineJudge/problem/views/oj.py`, the existing imports already include `from django.db.models import Count, Q`. Add one more:

```python
from django.db.models.functions import ExtractYear
```

Also confirm `from utils.constants import CacheKey` is present (it is, via existing cache usage).

- [ ] **Step 2: Add `ProblemYearlyACRateAPI` class at end of file**

Append to `OnlineJudge/problem/views/oj.py`:

```python
class ProblemYearlyACRateAPI(APIView):
    def get(self, request):
        problem_id = request.GET.get("problem_id")
        if not problem_id:
            return self.error("problem_id is required")

        cache_key = f"{CacheKey.problem_yearly_ac}:{problem_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return self.success(cached)

        try:
            problem = Problem.objects.get(
                _id=problem_id, contest_id__isnull=True, visible=True
            )
        except Problem.DoesNotExist:
            return self.error("Problem does not exist")

        rows = (
            Submission.objects.filter(
                problem_id=problem.id,
                contest_id__isnull=True,
            )
            .exclude(result__in=[JudgeStatus.PENDING, JudgeStatus.JUDGING])
            .annotate(year=ExtractYear("create_time"))
            .values("year")
            .annotate(
                total=Count("id"),
                accepted=Count("id", filter=Q(result=JudgeStatus.ACCEPTED)),
            )
            .order_by("year")
        )

        data = [
            {
                "year": row["year"],
                "total": row["total"],
                "accepted": row["accepted"],
                "ac_rate": round(row["accepted"] / row["total"] * 100, 2)
                if row["total"] > 0
                else 0.0,
            }
            for row in rows
        ]

        cache.set(cache_key, data, 3600)
        return self.success(data)
```

- [ ] **Step 3: Register URL in `problem/urls/oj.py`**

Replace the full contents of `OnlineJudge/problem/urls/oj.py` with:

```python
from django.urls import path

from ..views.oj import (
    ContestProblemAPI,
    PickOneAPI,
    ProblemAPI,
    ProblemAuthorAPI,
    ProblemSolvedPeopleCount,
    ProblemTagAPI,
    ProblemYearlyACRateAPI,
    SimilarProblemAPI,
)

urlpatterns = [
    path("problem/tags", ProblemTagAPI.as_view()),
    path("problem", ProblemAPI.as_view()),
    path("problem/beat_count", ProblemSolvedPeopleCount.as_view()),
    path("problem/similar", SimilarProblemAPI.as_view()),
    path("problem/author", ProblemAuthorAPI.as_view()),
    path("problem/yearly_ac", ProblemYearlyACRateAPI.as_view()),
    path("pickone", PickOneAPI.as_view()),
    path("contest/problem", ContestProblemAPI.as_view()),
]
```

- [ ] **Step 4: Run tests — expect all 4 to pass**

```bash
cd OnlineJudge && python manage.py test problem.tests.ProblemYearlyACRateAPITest -v 2
```

Expected output:
```
test_excludes_pending_and_judging ... ok
test_missing_problem_id_returns_error ... ok
test_nonexistent_problem_returns_error ... ok
test_returns_yearly_data_sorted_by_year ... ok

Ran 4 tests in ...s

OK
```

- [ ] **Step 5: Commit**

```bash
git -C OnlineJudge add utils/constants.py problem/views/oj.py problem/urls/oj.py problem/tests.py
git -C OnlineJudge commit -m "feat: add problem yearly AC rate API endpoint"
```

---

### Task 3: Frontend — add API function

**Files:**
- Modify: `ojnext/src/oj/api.ts`

- [ ] **Step 1: Add `YearlyACData` type and `getProblemYearlyAC` function**

In `ojnext/src/oj/api.ts`, add after the `getSimilarProblems` function (near the `// ==================== 相似题目推荐 ====================` section):

```typescript
export interface YearlyACData {
  year: number
  total: number
  accepted: number
  ac_rate: number
}

export function getProblemYearlyAC(problemId: string) {
  return http.get<YearlyACData[]>("problem/yearly_ac", {
    params: { problem_id: problemId },
  })
}
```

- [ ] **Step 2: Commit**

```bash
git -C ojnext add src/oj/api.ts
git -C ojnext commit -m "feat: add getProblemYearlyAC API function"
```

---

### Task 4: Frontend — create `ProblemYearlyChart.vue`

**Files:**
- Create: `ojnext/src/oj/problem/components/ProblemYearlyChart.vue`

- [ ] **Step 1: Create the component**

Create `ojnext/src/oj/problem/components/ProblemYearlyChart.vue` with the following content:

```vue
<template>
  <div class="yearly-chart" v-if="props.data.length > 1">
    <Line :data="chartData" :options="chartOptions" />
  </div>
</template>

<script setup lang="ts">
import { Line } from "vue-chartjs"
import {
  Chart as ChartJS,
  CategoryScale,
  Filler,
  LinearScale,
  LineElement,
  PointElement,
  Title,
  Tooltip,
} from "chart.js"
import type { YearlyACData } from "oj/api"

ChartJS.register(
  CategoryScale,
  Filler,
  LinearScale,
  LineElement,
  PointElement,
  Title,
  Tooltip,
)

const props = defineProps<{ data: YearlyACData[] }>()

const chartData = computed(() => ({
  labels: props.data.map((d) => String(d.year)),
  datasets: [
    {
      label: "AC 率",
      data: props.data.map((d) => d.ac_rate),
      fill: true,
      tension: 0.3,
      backgroundColor: "rgba(99, 179, 237, 0.2)",
      borderColor: "rgba(99, 179, 237, 1)",
      pointBackgroundColor: "rgba(99, 179, 237, 1)",
    },
  ],
}))

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    title: {
      display: true,
      text: "历年 AC 率",
      font: { size: 20 },
    },
    tooltip: {
      callbacks: {
        label: (context: any) => {
          const d = props.data[context.dataIndex]
          return [`AC 率: ${d.ac_rate}%`, `通过: ${d.accepted} / ${d.total}`]
        },
      },
    },
  },
  scales: {
    y: {
      min: 0,
      max: 100,
      ticks: {
        callback: (value: any) => `${value}%`,
      },
    },
  },
}))
</script>

<style scoped>
.yearly-chart {
  width: 100%;
  max-width: 500px;
  height: 250px;
  margin: 24px auto;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git -C ojnext add src/oj/problem/components/ProblemYearlyChart.vue
git -C ojnext commit -m "feat: add ProblemYearlyChart component"
```

---

### Task 5: Frontend — integrate chart into `ProblemInfo.vue`

**Files:**
- Modify: `ojnext/src/oj/problem/components/ProblemInfo.vue`

- [ ] **Step 1: Add imports**

In the `<script setup lang="ts">` block, add two imports alongside the existing ones:

```typescript
import { getProblemYearlyAC, type YearlyACData } from "oj/api"
import ProblemYearlyChart from "./ProblemYearlyChart.vue"
```

- [ ] **Step 2: Add reactive data and fetch function**

After `const beatRate = ref("0")`, add:

```typescript
const yearlyACData = ref<YearlyACData[]>([])
```

Add a new async function:

```typescript
async function getYearlyAC() {
  const res = await getProblemYearlyAC(problem.value!._id)
  yearlyACData.value = res.data
}
```

- [ ] **Step 3: Replace `onMounted` call**

Replace the existing:

```typescript
onMounted(getBeatRate)
```

With:

```typescript
onMounted(() => {
  getBeatRate()
  getYearlyAC()
})
```

- [ ] **Step 4: Add chart to template**

In the `<template>`, after the existing `.pie` div, add `<ProblemYearlyChart>`:

```html
  <div class="pie" v-if="problem && problem.submission_number > 0">
    <Pie :data="data" :options="options" />
  </div>
  <ProblemYearlyChart :data="yearlyACData" />
</template>
```

- [ ] **Step 5: Start dev server and verify manually**

```bash
cd ojnext && npm start
```

Open a problem page and navigate to the info/stats tab. Verify:

1. A problem with submissions spanning **multiple years**: line chart appears below the pie chart, Y-axis shows 0–100%, hovering shows "AC 率: X%" and "通过: Y / Z"
2. A problem with submissions only in **one year** (or zero): chart is hidden (`v-if="props.data.length > 1"`)
3. No console errors in the browser devtools

- [ ] **Step 6: Commit**

```bash
git -C ojnext add src/oj/problem/components/ProblemInfo.vue
git -C ojnext commit -m "feat: show yearly AC rate chart on problem info page"
```
