FROM python:3.12.2-alpine
ARG TARGETARCH
ARG TARGETVARIANT

RUN sed -i 's|dl-cdn.alpinelinux.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apk/repositories

ENV OJ_ENV=production
WORKDIR /app

COPY ./deploy/requirements.txt /app/deploy/

RUN --mount=type=cache,target=/var/cache/apk,id=apk-cache-$TARGETARCH$TARGETVARIANT-final \
    --mount=type=cache,target=/root/.cache/pip,id=pip-cache-$TARGETARCH$TARGETVARIANT-final \
    <<EOS
set -ex
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
apk add --no-cache \
  gcc libc-dev python3-dev \
  libpq libpq-dev \
  libjpeg-turbo libjpeg-turbo-dev \
  zlib zlib-dev \
  freetype freetype-dev \
  supervisor openssl nginx curl unzip
pip install --no-cache-dir -r /app/deploy/requirements.txt
apk del gcc libc-dev python3-dev libpq-dev libjpeg-turbo-dev zlib-dev freetype-dev
EOS

COPY ./ /app/
RUN mkdir -p /app/dist/
RUN chmod -R u=rwX,go=rX ./ && chmod +x ./deploy/entrypoint.sh

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python3 /app/deploy/health_check.py
EXPOSE 8000
ENTRYPOINT [ "/app/deploy/entrypoint.sh" ]