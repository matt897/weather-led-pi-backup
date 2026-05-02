#!/bin/bash

LOG="/home/matt/weather_led_boot.log"

echo "-----------------------------" >> "$LOG"
echo "Launcher started at $(date)" >> "$LOG"

sleep 90

echo "After boot delay at $(date)" >> "$LOG"

# Kill any stale copy.
pkill -f "/home/matt/weather_led_strip.py" || true
sleep 2

cd /home/matt || exit 1

echo "Launching LED script with nohup at $(date)" >> "$LOG"

nohup /home/matt/weatherled-venv/bin/python /home/matt/weather_led_strip.py >> "$LOG" 2>&1 &
echo "Spawned PID $!" >> "$LOG"

exit 0
