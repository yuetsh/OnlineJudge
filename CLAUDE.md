# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**OnlineJudge** is the backend for an Online Judge platform. Built with Django 5 + Django REST Framework, PostgreSQL, Redis, Django Channels (WebSocket), and Dramatiq (async task queue). Python 3.12+, managed with `uv`.

## Commands

```bash
# Development
python dev.py                    # Start dev server (Daphne ASGI + Django runserver)
python manage.py runserver       # HTTP only (no WebSocket support)
python manage.py migrate         # Apply database migrations
python manage.py makemigrations  # Create new migrations

# Dependencies
uv sync                          # Install dependencies from uv.lock
uv add <package>                 # Add a dependency

# Testing
python manage.py test            # Run Django test suite
coverage run manage.py test      # Run with coverage
coverage report                  # Show coverage report
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

### URL Routing

All routes are registered in `oj/urls.py`:
- `api/` — user-facing endpoints
- `api/admin/` — admin-only endpoints

WebSocket routing is in `oj/routing.py`.

### Settings Structure

- `oj/settings.py` — base configuration
- `oj/dev_settings.py` — development overrides (imported when `OJ_ENV != "production"`)
- `oj/production_settings.py` — production overrides

### Base APIView

`utils/api/api.py` provides a custom `APIView` base class used by all views. It provides:
- `self.success(data)` — returns `{"error": null, "data": data}`
- `self.error(msg)` — returns `{"error": "error", "data": msg}`

All views inherit from this, not Django's generic views or DRF's `APIView` directly.

### Authentication & Permissions

`account/decorators.py` provides decorators used on view methods:
- `@login_required`
- `@super_admin_required`
- `@check_contest_permission`

### Judge System

- `judge/dispatcher.py` — dispatches submissions to the judge sandbox
- `judge/tasks.py` — Dramatiq async tasks for judging
- `judge/languages.py` — language configurations (compile/run commands, limits)

Judge status codes are defined in `utils/constants.py` and must match the frontend's `utils/constants.ts`.

### WebSocket (Channels)

`submission/consumers.py` — WebSocket consumer for real-time submission status updates. Uses `channels-redis` as the channel layer backend.

### Caching

Redis-backed via `django-redis`. Cache keys use MD5 hashing for consistency. See `utils/cache.py`.

### AI Integration

`utils/openai.py` — OpenAI client wrapper configured to work with OpenAI-compatible APIs (e.g., DeepSeek). Used by `ai/` app for submission analysis.

### Data Directory

Test cases and submission outputs are stored in a separate data directory (configured in settings, not in the repo). The `data/` directory in the repo contains configuration templates.

## Key Domain Concepts

| Concept | Details |
|---|---|
| Problem types | ACM (binary accept/reject) vs OI (partial scoring) |
| Judge statuses | Numeric codes -2 to 9 (defined in `utils/constants.py`) |
| User roles | Regular / Admin / Super Admin |
| Contest types | Public vs Password Protected |
| Supported languages | C, C++, Python2, Python3, Java, JavaScript, Golang, Flowchart |

## Related Repository

The frontend is at `D:\Projects\ojnext` — a Vue 3 + Rsbuild project. See its CLAUDE.md for frontend details.
