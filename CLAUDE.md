# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**OnlineJudge** is the backend for an Online Judge platform. Built with Django 5 + Django REST Framework, PostgreSQL, Redis, Django Channels (WebSocket), and Dramatiq (async task queue). Python 3.12+, managed with `uv`.

## Commands

```bash
# Development
python dev.py                    # Start dev server: Django on :8000 + Daphne WebSocket on :8001
python manage.py runserver       # HTTP only (no WebSocket support)
python manage.py migrate         # Apply database migrations
python manage.py makemigrations  # Create new migrations

# Dependencies
uv sync                          # Install dependencies from uv.lock
uv add <package>                 # Add a dependency

# Testing
python manage.py test            # Run all tests
python manage.py test account    # Run tests for a single app
python manage.py test account.tests.TestClassName  # Run a single test class
python run_test.py               # Run flake8 lint + coverage in one step
python run_test.py -m account    # Run flake8 + tests for a single module
python run_test.py -c            # Run flake8 + tests + open HTML coverage report

# Initial setup
python manage.py inituser --username admin --password <pw> --action create_super_admin
python manage.py inituser --username admin --password <pw> --action reset
```

## Architecture

### App Modules

Each Django app follows the same structure:
```
<app>/
├── models.py         # Django models
├── serializers.py    # DRF serializers
├── views/
│   ├── oj.py         # User-facing API views
│   └── admin.py      # Admin API views
└── urls/
    ├── oj.py         # User-facing URL patterns
    └── admin.py      # Admin URL patterns
```

Apps: `account`, `problem`, `submission`, `contest`, `ai`, `flowchart`, `problemset`, `class_pk`, `announcement`, `tutorial`, `message`, `comment`, `conf`, `options`, `judge`

`utils/` is itself a Django app (listed in `INSTALLED_APPS`) — not just a helpers package. It provides `RichTextField` (XSS-sanitized `TextField`), `APIError`, the base `APIView`, caching, WebSocket helpers, and the `inituser` management command. Import shared utilities from `utils.*`.

### URL Routing

All routes are registered in `oj/urls.py`:
- `api/` — user-facing endpoints
- `api/admin/` — admin-only endpoints

WebSocket routing is in `oj/routing.py`.

### Settings Structure

- `oj/settings.py` — base configuration (imports dev or production settings based on `OJ_ENV`)
- `oj/dev_settings.py` — development overrides (imported when `OJ_ENV != "production"`)
- `oj/production_settings.py` — production overrides

### Base APIView & View Patterns

`utils/api/api.py` provides the custom base classes and decorators used by **all** views:

- **`APIView`** — base class for all views (not DRF's `APIView`). Key methods:
  - `self.success(data)` — returns `{"error": null, "data": data}`
  - `self.error(msg)` — returns `{"error": "error", "data": msg}`
  - `self.paginate_data(request, query_set, serializer)` — offset/limit pagination
  - `self.invalid_serializer(serializer)` — standard validation error response
- **`CSRFExemptAPIView`** — same as `APIView` but CSRF-exempt
- **`@validate_serializer(SerializerClass)`** — decorator for view methods that validates `request.data` against a serializer before the method runs. On success, `request.data` is replaced with validated data.

Typical view method pattern:
```python
@validate_serializer(CreateProblemSerializer)
@super_admin_required
def post(self, request):
    # request.data is already validated
    return self.success(...)
```

### Authentication & Permissions

`account/decorators.py` provides decorators used on view methods:
- `@login_required` / `@admin_role_required` / `@super_admin_required`
- `@problem_permission_required`
- `@check_contest_permission(check_type)` — validates contest access, sets `self.contest`
- `ensure_created_by(obj, user)` — helper that raises `APIError` if user doesn't own the object

### Judge System

- `judge/dispatcher.py` — dispatches submissions to the judge sandbox (JudgeServer)
- `judge/tasks.py` — Dramatiq async tasks for judging
- `judge/languages.py` — language configurations (compile/run commands, limits)

Judge status codes are defined in `submission/models.py` (`JudgeStatus` class, codes -2 to 8) and must match the frontend's `utils/constants.ts`.

### Site Configuration (SysOptions)

`options/options.py` provides `SysOptions` — a metaclass-based system for site-wide configuration stored in the database with thread-local caching. Access settings like `SysOptions.smtp_config`, `SysOptions.languages`, etc.

### WebSocket (Channels)

`submission/consumers.py` — WebSocket consumer for real-time submission status updates. Uses `channels-redis` as the channel layer backend. Push updates via `utils/websocket.py:push_submission_update()`.

### Caching

Redis-backed via `django-redis`. Cache keys use MD5 hashing for consistency. See `utils/cache.py`.

### AI Integration

`utils/openai.py` — OpenAI client wrapper configured to work with OpenAI-compatible APIs (e.g., DeepSeek). Used by `ai/` app for submission analysis.

### Data Directory

Test cases and submission outputs are stored in a separate data directory (configured in settings, not in the repo). The `data/` directory in the repo contains configuration templates and `secret.key`.

## Key Domain Concepts

| Concept | Details |
|---|---|
| Problem types | ACM (binary accept/reject) vs OI (partial scoring) |
| Judge statuses | COMPILE_ERROR(-2), WRONG_ANSWER(-1), ACCEPTED(0), CPU_TLE(1), REAL_TLE(2), MLE(3), RE(4), SE(5), PENDING(6), JUDGING(7), PARTIALLY_ACCEPTED(8) |
| User roles | Regular / Admin / Super Admin |
| Contest types | Public vs Password Protected |
| Supported languages | C, C++, Python2, Python3, Java, JavaScript, Golang, Flowchart |

## Related Repository

The frontend is at `../ojnext` — a Vue 3 + Rsbuild project. See its CLAUDE.md for frontend details.
