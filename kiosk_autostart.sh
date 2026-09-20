#!/bin/sh
# Deploy to ~/.config/labwc/autostart (chmod +x) on the kiosk user (matt).
# labwc runs this automatically once its Wayland session is up.

until curl -sf http://localhost:5000/display -o /dev/null; do
  sleep 1
done

chromium --kiosk --incognito --noerrdialogs --disable-infobars --no-first-run \
  --disable-session-crashed-bubble --ozone-platform=wayland \
  http://localhost:5000/display &
