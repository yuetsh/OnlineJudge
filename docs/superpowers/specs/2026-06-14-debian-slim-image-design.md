# Debian Slim Backend Image Design

## Goal

Replace the backend Alpine image with Debian slim to prioritize predictable, fast dependency installation and long-term compatibility with binary Python packages.

## Scope

The migration covers the backend image in `Dockerfile` and the Linux distribution assumptions in its runtime configuration. It does not change the Redis, PostgreSQL, judge, or test-case rsync images.

## Base Image

Use `python:3.12-slim-bookworm`.

The image remains multi-architecture because no `--platform` value is pinned. Existing `TARGETARCH` and `TARGETVARIANT` arguments remain available for architecture-specific BuildKit cache IDs.

## System Packages

Replace Alpine `apk` commands with Debian `apt-get` commands. Install only runtime tools and libraries required by the application:

- `ca-certificates`
- `clang-format`
- `curl`
- `libjpeg62-turbo`
- `libpq5`
- `nginx`
- `openssl`
- `passwd`
- `supervisor`
- `unzip`
- `zlib1g`

Use `--no-install-recommends` and remove `/var/lib/apt/lists/*` in the same layer.

Do not install a compiler or Python development headers by default. The locked versions of Pillow, lxml, psycopg-binary, httptools, uvloop, and watchfiles publish CPython 3.12 manylinux wheels for the primary supported Linux architectures. A build failure caused by a missing wheel should fail visibly instead of silently introducing a full native build toolchain.

Retain the pip cache mount but remove `--no-cache-dir`, because disabling pip's cache prevents the BuildKit cache mount from improving clean rebuilds.

## Runtime Compatibility

Update `deploy/entrypoint.sh` to use POSIX shell syntax and Debian-compatible account creation:

- Replace `[[ ... ]]` with `[ ... ]`.
- Quote paths and variable expansions where the current script performs filesystem operations.
- Create the `spj` group with `groupadd` and the `server` system account with `useradd`.
- Make account creation idempotent so container restarts do not fail if account data is already present.

Update `deploy/nginx/nginx.conf` from Alpine's `nginx` user to Debian's `www-data` user.

The runtime process model remains unchanged: supervisord starts nginx, gunicorn, and Dramatiq.

## Build And Runtime Behavior

The requirements file remains the dependency source used by the image. No application dependency versions or Django behavior change.

The expected improvement is faster and more reliable cold dependency installation from manylinux wheels. The final image may be larger than the Alpine image; image size is not the primary optimization target.

## Verification

Verification must cover:

1. Build the backend image with BuildKit.
2. Import Pillow, lxml, and psycopg inside the built image.
3. Confirm `clang-format`, nginx, supervisord, and OpenSSL are installed.
4. Run a shell syntax check on `deploy/entrypoint.sh`.
5. Start a disposable container far enough to detect distribution-specific user, shell, nginx, or shared-library failures. Database-dependent startup may stop at connection retries when PostgreSQL is unavailable; those failures are not image compatibility failures.

## Non-Goals

- Converting other service images from Alpine.
- Splitting the backend into builder and runtime stages.
- Optimizing primarily for the smallest possible final image.
- Changing the current nginx and supervisord process architecture.
