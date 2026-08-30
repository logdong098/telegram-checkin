FROM mcr.microsoft.com/playwright/python:v1.62.0-noble

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data \
    CONFIG_PATH=/app/config.yaml \
    DISPLAY=:99 \
    NOVNC_PORT=18083 \
    VNC_PORT=5900

# Install Xvfb + x11vnc + noVNC for remote interactive browser login
RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb \
        x11vnc \
        novnc \
        websockify \
        openbox \
        fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir --ignore-installed .

RUN mkdir -p /data \
    && chown pwuser:pwuser /data

COPY scripts/remote-login.sh /usr/local/bin/remote-login
RUN chmod +x /usr/local/bin/remote-login

USER pwuser

ENTRYPOINT ["telegram-checkin"]
CMD ["daemon"]
