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

COPY ./ /app/
RUN mkdir -p /app/dist/
RUN chmod -R u=rwX,go=rX ./ && chmod +x ./deploy/entrypoint.sh

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python3 /app/deploy/health_check.py
EXPOSE 8000
ENTRYPOINT [ "/app/deploy/entrypoint.sh" ]
