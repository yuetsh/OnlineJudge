# Debian Slim Backend Image Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Alpine backend image with Debian slim while improving dependency installation speed and preserving runtime behavior.

**Architecture:** Keep the existing single-stage backend image and process model. Use Debian runtime packages plus manylinux Python wheels, then adapt the shell entrypoint and nginx worker account to Debian conventions.

**Tech Stack:** Docker BuildKit, Python 3.12 slim-bookworm, Debian apt, POSIX shell, nginx, supervisord

---

### Task 1: Establish Migration Checks

**Files:**
- Inspect: `Dockerfile`
- Inspect: `deploy/entrypoint.sh`
- Inspect: `deploy/nginx/nginx.conf`

- [x] **Step 1: Verify the current base image check fails**

Run:

```bash
grep -q '^FROM python:3\.12-slim-bookworm$' Dockerfile
```

Expected: exit status 1 because the current image is Alpine.

- [x] **Step 2: Verify the current shell portability check fails**

Run:

```bash
sh -n deploy/entrypoint.sh
! grep -n '\[\[' deploy/entrypoint.sh
```

Expected: `sh -n` succeeds, but the grep assertion exits non-zero because the script contains `[[`.

- [x] **Step 3: Verify the current nginx user check fails**

Run:

```bash
grep -q '^user www-data;$' deploy/nginx/nginx.conf
```

Expected: exit status 1 because the configuration uses the Alpine `nginx` account.

### Task 2: Migrate the Docker Build

**Files:**
- Modify: `Dockerfile`

- [x] **Step 1: Replace the Alpine build with Debian slim**

Use this package and cache structure:

```dockerfile
FROM python:3.12-slim-bookworm
ARG TARGETARCH
ARG TARGETVARIANT

ENV OJ_ENV=production
WORKDIR /app

COPY ./deploy/requirements.txt /app/deploy/

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked,id=apt-cache-$TARGETARCH$TARGETVARIANT-final \
    --mount=type=cache,target=/root/.cache/pip,id=pip-cache-$TARGETARCH$TARGETVARIANT-final \
    <<EOS
set -ex
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates \
  clang-format \
  curl \
  libjpeg62-turbo \
  libpq5 \
  nginx \
  openssl \
  passwd \
  supervisor \
  unzip \
  zlib1g
pip install -r /app/deploy/requirements.txt
rm -rf /var/lib/apt/lists/*
EOS
```

Keep the existing application copy, permissions, health check, exposed port, and entrypoint.

- [x] **Step 2: Run Dockerfile static checks**

Run:

```bash
grep -q '^FROM python:3\.12-slim-bookworm$' Dockerfile
! grep -nE 'apk|alpine|gcc|python3-dev|--no-cache-dir' Dockerfile
grep -q 'target=/var/cache/apt' Dockerfile
grep -q 'target=/root/.cache/pip' Dockerfile
```

Expected: all checks exit 0.

### Task 3: Make Runtime Configuration Debian-Compatible

**Files:**
- Modify: `deploy/entrypoint.sh`
- Modify: `deploy/nginx/nginx.conf`

- [x] **Step 1: Replace non-POSIX tests and Alpine account commands**

Use POSIX `[ ]` tests. Replace runtime account creation with:

```sh
if ! getent group spj >/dev/null; then
    groupadd --system --gid 903 spj
fi
if ! id -u server >/dev/null 2>&1; then
    useradd --system --uid 900 --gid spj --no-create-home --shell /usr/sbin/nologin server
fi
```

Quote filesystem paths and variable expansions touched by the script.

- [x] **Step 2: Change the nginx worker user**

Set the first line of `deploy/nginx/nginx.conf` to:

```nginx
user www-data;
```

- [x] **Step 3: Run runtime configuration checks**

Run:

```bash
sh -n deploy/entrypoint.sh
! grep -n '\[\[' deploy/entrypoint.sh
! grep -nE 'addgroup|adduser' deploy/entrypoint.sh
grep -q 'groupadd --system --gid 903 spj' deploy/entrypoint.sh
grep -q 'useradd --system --uid 900 --gid spj' deploy/entrypoint.sh
grep -q '^user www-data;$' deploy/nginx/nginx.conf
```

Expected: all checks exit 0.

### Task 4: Build And Inspect The Image

**Files:**
- Verify: `Dockerfile`
- Verify: `deploy/entrypoint.sh`
- Verify: `deploy/nginx/nginx.conf`

- [ ] **Step 1: Build the backend image**

Run:

```bash
DOCKER_BUILDKIT=1 docker build --progress=plain -t onlinejudge-backend:slim .
```

Expected: exit status 0, with Python dependencies installed from wheels.

- [ ] **Step 2: Verify native dependencies and runtime tools**

Run:

```bash
docker run --rm --entrypoint /bin/sh onlinejudge-backend:slim -c \
  'python -c "from PIL import Image; import lxml.etree; import psycopg" &&
   clang-format --version &&
   nginx -t -c /app/deploy/nginx/nginx.conf &&
   supervisord --version &&
   openssl version &&
   groupadd --help >/dev/null &&
   useradd --help >/dev/null'
```

Expected: exit status 0.

- [ ] **Step 3: Exercise distribution-specific entrypoint startup**

Run the image with unreachable local service names and a timeout:

```bash
timeout 15 docker run --rm \
  -e POSTGRES_HOST=127.0.0.1 \
  -e REDIS_HOST=127.0.0.1 \
  -e JUDGE_SERVER_TOKEN=test \
  onlinejudge-backend:slim
```

Expected: the application may time out while retrying database migration, but output must not contain shell syntax errors, missing `groupadd`/`useradd`, missing shared libraries, or an unknown nginx user.

### Task 5: Final Verification

**Files:**
- Verify: all modified files

- [ ] **Step 1: Run repository checks**

Run:

```bash
git diff --check
sh -n deploy/entrypoint.sh
git status --short
git diff -- Dockerfile deploy/entrypoint.sh deploy/nginx/nginx.conf
```

Expected: no whitespace errors or shell syntax errors; the diff contains only the approved migration and its documentation.

- [ ] **Step 2: Record build evidence**

Record the image ID and size:

```bash
docker image inspect onlinejudge-backend:slim --format '{{.Id}} {{.Size}}'
```

Expected: one image ID and byte size.
