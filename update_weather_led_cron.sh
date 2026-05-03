#!/bin/bash

CONFIG="/home/matt/weather_led_config.json"
BOOT_SCRIPT="/home/matt/boot_weather_led.sh"

if [ ! -f "$CONFIG" ]; then
  echo "Config file not found: $CONFIG"
  exit 1
fi

QUIET_ENABLED=$(/home/matt/weatherled-venv/bin/python - <<'PY'
import json
with open("/home/matt/weather_led_config.json") as f:
    c = json.load(f)
print(str(c.get("quiet_hours_enabled", True)).lower())
PY
)

QUIET_START=$(/home/matt/weatherled-venv/bin/python - <<'PY'
import json
with open("/home/matt/weather_led_config.json") as f:
    c = json.load(f)
print(int(c.get("quiet_start_hour", 22)))
PY
)

QUIET_END=$(/home/matt/weatherled-venv/bin/python - <<'PY'
import json
with open("/home/matt/weather_led_config.json") as f:
    c = json.load(f)
print(int(c.get("quiet_end_hour", 7)))
PY
)

if [ "$QUIET_START" -lt 0 ] || [ "$QUIET_START" -gt 23 ]; then
  echo "Invalid quiet_start_hour: $QUIET_START"
  exit 1
fi

if [ "$QUIET_END" -lt 0 ] || [ "$QUIET_END" -gt 23 ]; then
  echo "Invalid quiet_end_hour: $QUIET_END"
  exit 1
fi

TMP_CRON=$(mktemp)

{
  echo "# Weather LED auto-managed cron"
  echo "# Do not manually edit these lines; update quiet hours from the web UI."
  echo "@reboot $BOOT_SCRIPT"

  if [ "$QUIET_ENABLED" = "true" ]; then
    echo "0 $QUIET_END * * * $BOOT_SCRIPT"
    echo "0 $QUIET_START * * * pkill -f /home/matt/weather_led_strip.py"
  fi
} > "$TMP_CRON"

crontab "$TMP_CRON"
rm "$TMP_CRON"

echo "Updated root cron:"
crontab -l
