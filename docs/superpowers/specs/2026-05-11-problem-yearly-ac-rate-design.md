# Problem Yearly AC Rate — Design Spec

**Date:** 2026-05-11  
**Status:** Approved

---

## Overview

Add a per-problem "historical AC rate by year" feature. A new backend API returns yearly submission statistics for a given problem; the frontend displays this as a line chart on the problem stats page, alongside the existing submission-result pie chart.

---

## Backend

### Endpoint

```
GET /api/problem/yearly_ac?problem_id=<_id>
```

- Public (user-facing), no authentication required
- `problem_id`: the problem's display ID (`Problem._id`, string)

### Query Logic

```python
Submission.objects.filter(
    problem_id=problem.id,
    contest_id__isnull=True,          # exclude contest submissions
    result__not_in=[JudgeStatus.PENDING, JudgeStatus.JUDGING],  # exclude in-flight submissions
)
.annotate(year=ExtractYear('create_time'))
.values('year')
.annotate(
    total=Count('id'),
    accepted=Count('id', filter=Q(result=JudgeStatus.ACCEPTED))
)
.order_by('year')
```

### Response Format

```json
{
  "error": null,
  "data": [
    {"year": 2023, "total": 120, "accepted": 54, "ac_rate": 45.0},
    {"year": 2024, "total": 88,  "accepted": 31, "ac_rate": 35.23}
  ]
}
```

- `ac_rate`: float, two decimal places, percentage (0–100)
- If `total == 0` for a year: `ac_rate = 0` (guards against division by zero)
- Empty list returned if no judged submissions exist

### Error Cases

| Condition | Response |
|---|---|
| `problem_id` missing | `error("problem_id is required")` |
| Problem not found / not visible | `error("Problem does not exist")` |

### Caching

- Redis cache key: `problem_yearly_ac:{problem._id}`
- TTL: 3600 seconds (1 hour), consistent with other problem caches

### Implementation Location

- View class: `ProblemYearlyACRateAPI` in `OnlineJudge/problem/views/oj.py`
- URL: `path("problem/yearly_ac", ProblemYearlyACRateAPI.as_view())` in `OnlineJudge/problem/urls/oj.py`

---

## Frontend

### New Component

`ojnext/src/oj/problem/components/ProblemYearlyChart.vue`

- Uses `vue-chartjs` Line chart (same library as `oj/contest/components/LineChart.vue`)
- Registers: `CategoryScale`, `LinearScale`, `PointElement`, `LineElement`, `Title`, `Tooltip`, `Filler`
- Props: `data: Array<{ year: number; total: number; accepted: number; ac_rate: number }>`
- X-axis: year (string labels)
- Y-axis: AC rate 0–100%
- Tooltip per point: year, AC rate, accepted/total counts
- Shows nothing (v-if) when data is empty or has only one point

### Chart Options

- `responsive: true`, `maintainAspectRatio: false`, height `250px`
- Dataset: `fill: true` (area chart feel), single line
- Y-axis: `min: 0`, `max: 100`, tick suffix `%`

### API Call

Add to `ojnext/src/oj/api.ts`:

```ts
export function getProblemYearlyAC(problemId: string) {
  return http.get<Array<{ year: number; total: number; accepted: number; ac_rate: number }>>(
    "/problem/yearly_ac",
    { params: { problem_id: problemId } }
  )
}
```

### Integration

In `ojnext/src/oj/problem/components/ProblemInfo.vue`:

- Import `getProblemYearlyAC` and call it on mount (alongside existing `getProblemBeatRate`)
- Render `<ProblemYearlyChart>` below the existing pie chart, with a section title "历年 AC 率"
- No loading spinner needed (chart simply absent until data arrives)

---

## Assumptions

- Contest submissions excluded; they represent a different access context
- PENDING (6) and JUDGING (7) excluded; PARTIALLY_ACCEPTED (8) and SYSTEM_ERROR (5) are included as final verdicts
- No migrations needed (query only, no model changes)
