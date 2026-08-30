FROM mcr.microsoft.com/playwright/python:v1.62.0-noble

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data \
    CONFIG_PATH=/app/config.yaml

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN mkdir -p /data \
    && chown pwuser:pwuser /data

USER pwuser

ENTRYPOINT ["telegram-checkin"]
CMD ["daemon"]
