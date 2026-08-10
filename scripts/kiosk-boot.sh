#!/usr/bin/env bash
# LIGHT-BELT kiosk launcher — waits for host_services, then opens Chromium.
set -euo pipefail

SERVICE_URL="http://localhost:8443/api/v1/status"

echo "Waiting for host_services at ${SERVICE_URL}..."
curl \
  --retry 10 \
  --retry-delay 2 \
  --retry-connrefused \
  --silent \
  --fail \
  --output /dev/null \
  "${SERVICE_URL}"
echo "host_services is up."

# Hide the mouse cursor after 1 second of inactivity
unclutter -idle 1 &

exec chromium-browser \
  --kiosk \
  --no-first-run \
  --disable-translate \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-features=TranslateUI \
  "http://localhost:8443"
