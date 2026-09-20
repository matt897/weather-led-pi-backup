#!/usr/bin/env python3
"""Blanks/unblanks the HDMI-connected kiosk display for quiet hours.

Runs as a long-lived poller (like weather_led_strip.py's own quiet-hours
enforcement) rather than from cron, so a reboot mid-window or a missed tick
can't leave the screen stuck in the wrong state. Toggles the display via
wlopm, which talks to the Wayland compositor's output-power-management
protocol - this must run as the same user as the kiosk's Wayland session
(not root)."""

import subprocess
import time

from weather_data import load_config, quiet_hours_active


def main():
    last_state = None

    while True:
        config = load_config()

        quiet = quiet_hours_active(
            config["kiosk_quiet_hours_enabled"],
            config["quiet_start_hour"],
            config["quiet_end_hour"],
            time.localtime().tm_hour
        )

        if quiet != last_state:
            subprocess.run(["wlopm", "--off" if quiet else "--on", "*"], check=False)
            print(f"Kiosk display {'blanked' if quiet else 'unblanked'} for quiet hours.", flush=True)
            last_state = quiet

        time.sleep(max(1, int(config.get("kiosk_blank_check_seconds", 30))))


if __name__ == "__main__":
    main()
