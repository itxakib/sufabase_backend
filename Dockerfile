# syntax=docker/dockerfile:1
#
# SUFABASE backend — Django 6 + DRF, served by gunicorn on WSGI.
#
#   docker build -t sufabase-backend .
#   docker run --rm -p 8000:8000 --env-file .env -v sufabase-media:/app/media sufabase-backend
#
# Configuration is env-only: `.env` is excluded from the build context (see
# .dockerignore), so nothing secret is baked into a layer. python-decouple reads
# the process environment first and the file second, so passing values with
# `--env-file` / compose `environment:` is all that is needed.
#
# Required at startup — `config/settings.py` calls config('SECRET_KEY'),
# config('DB_NAME'), config('DB_USER') and config('DB_PASSWORD') with no
# defaults, so the container exits immediately without them:
#
#   SECRET_KEY=…                 a long random string; not the dev one
#   DEBUG=false                  default is True, which is wrong anywhere real
#   ALLOWED_HOSTS=api.example.com
#   DB_NAME / DB_USER / DB_PASSWORD / DB_HOST / DB_PORT
#   CORS_ALLOWED_ORIGINS=https://app.example.com
#
# Postgres is not part of this image — point DB_HOST at a database container or
# a managed instance.
#
#   docker run --rm -p 8000:8000 --env-file .env \
#     -e DB_HOST=host.docker.internal -v sufabase-media:/app/media \
#     sufabase-backend

FROM python:3.12-slim

# Byte-code files stay out of the image (they are per-interpreter anyway),
# stdout/stderr are unbuffered so `docker logs` shows output as it happens, and
# Poetry is told to install into the system environment instead of a venv
# inside a venv.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=2.4.3 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

# libpq is what psycopg talks to. Pillow and psycopg ship manylinux wheels, so
# no compiler toolchain is installed — which is the point: slim stays slim and
# the build does not depend on gcc being available for the right arch.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install "poetry==${POETRY_VERSION}"

WORKDIR /app

# Lockfile first: the dependency layer is cached until pyproject/poetry.lock
# change, so day-to-day source edits do not reinstall Django.
#
# `--only main` skips dev groups; `--no-root` skips installing this project
# itself, which has no package to install (poetry-core with no `packages`).
# A pyproject.toml edited without running `poetry lock` fails here on purpose —
# an image built against a stale lock is worse than a failed build.
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root --no-ansi

COPY . .

# gunicorn is not a Poetry dependency (the project is run by `manage.py
# runserver` locally), so it is installed here rather than left out of the
# image. Add it to pyproject.toml to have it version-pinned by the lockfile.
RUN pip install "gunicorn>=23.0,<24.0"

# `manage.py collectstatic` is deliberately NOT run: config/settings.py defines
# STATIC_URL but no STATIC_ROOT, and Django refuses to collect without one.
# Nothing in this image serves static files yet, so adding a broken step would
# only make the build fail. Give settings a STATIC_ROOT (plus WhiteNoise or a
# proxy in front) before enabling it — the admin and /api/docs/ need it.

# Unprivileged runtime user. Owns /app so uploaded media and any future
# staticfiles directory are writable, and so nothing runs as root.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/media \
    && chown -R app:app /app

USER app

EXPOSE 8000

# /api/schema/ is the OpenAPI view (drf-spectacular, AllowAny), so it answers
# without a token: a health check that needs a login would report an unhealthy
# container whenever the credentials rotated.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS -o /dev/null http://127.0.0.1:8000/api/schema/ || exit 1

# Migrations run before gunicorn because every start of this container is a
# deploy: `simplejwt.token_blacklist` and the custom `users.User` model both
# need their tables before the first request arrives.
#
# The trade-off to know: with more than one replica they race (Django's migrate
# takes a lock, so they serialise rather than corrupt, but the losers wait). Run
# `manage.py migrate` as a separate job before scaling out.
#
# `exec` hands PID 1 to gunicorn, so SIGTERM from `docker stop` reaches it and
# requests drain instead of being cut off. Worker count and timeout are env vars
# because the right numbers depend on the box, not on the code.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers ${WEB_CONCURRENCY:-3} --timeout ${WEB_TIMEOUT:-60} --access-logfile - --error-logfile -"]
