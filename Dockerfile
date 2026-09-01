# Monica 1.0 — production image (P0). Только stdlib — requirements нет.
FROM python:3.12-slim

# non-root пользователь
RUN useradd --create-home --shell /usr/sbin/nologin monica

WORKDIR /app

# копируем только код (data/, .env, config.json идут volume/env — см. .dockerignore)
COPY app/ /app/app/
COPY tools/ /app/tools/

# mutable-данные — в volume (MONICA_DATA_DIR), владелец monica
RUN mkdir -p /data && chown -R monica:monica /data /app
USER monica

ENV MONICA_DATA_DIR=/data \
    MONICA_HOST=0.0.0.0 \
    PORT=8900 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8900

# healthcheck по /health (минимальный ответ без конфигурации)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,sys;sys.exit(0 if b'ok' in urllib.request.urlopen('http://127.0.0.1:8900/health',timeout=4).read() else 1)"

CMD ["python", "app/server.py"]
