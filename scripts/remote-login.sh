#!/bin/bash
set -euo pipefail
DISPLAY_NUM="${DISPLAY#:}"
NOVNC_PORT="${NOVNC_PORT:-18083}"
VNC_PORT="${VNC_PORT:-5900}"
DATA_DIR="${DATA_DIR:-/data}"
WEBSITE_URL="${WEBSITE_URL:-https://www.820010.xyz/}"
CHROME_BIN="/ms-playwright/chromium-1234/chrome-linux/chrome"
PROFILE_DIR="${DATA_DIR}/website-browser-profile"

pkill -9 -f "chrome" 2>/dev/null || true
pkill -9 Xvfb 2>/dev/null || true
pkill -9 x11vnc 2>/dev/null || true
pkill -9 websockify 2>/dev/null || true
pkill -9 openbox 2>/dev/null || true
sleep 1

Xvfb :${DISPLAY_NUM} -screen 0 1440x900x24 -ac +extension RANDR &
sleep 2
x11vnc -display :${DISPLAY_NUM} -rfbport ${VNC_PORT} -nopw -forever -shared -bg -quiet 2>/dev/null
websockify --web /usr/share/novnc/ ${NOVNC_PORT} localhost:${VNC_PORT} &
echo "noVNC ready: http://0.0.0.0:${NOVNC_PORT}/vnc.html"
openbox &
sleep 1

export DISPLAY=:${DISPLAY_NUM}
mkdir -p "${PROFILE_DIR}"
echo "Launching native Chromium at ${WEBSITE_URL}"
"${CHROME_BIN}" \
    --user-data-dir="${PROFILE_DIR}" \
    --no-sandbox \
    --no-first-run \
    --no-default-browser-check \
    --disable-sync \
    --disable-features=Translate \
    --start-maximized \
    "${WEBSITE_URL}" &
wait
