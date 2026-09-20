#!/usr/bin/env python3

import time
import math
import random
import signal
import sys
import os
import fcntl
from pathlib import Path

import socket

from rpi_ws281x import PixelStrip, Color

from weather_data import (
    load_config,
    fetch_next_hour_weather,
    classify_weather,
    is_quiet_hours,
    quiet_hours_active,
)


# -----------------------------
# SYSTEMD WATCHDOG
# -----------------------------

def systemd_watchdog_ping():
    """Ping the systemd watchdog. No-op when not running under systemd."""
    notify_socket = os.environ.get("NOTIFY_SOCKET")
    if not notify_socket:
        return
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(notify_socket)
            sock.send(b"WATCHDOG=1")
    except Exception:
        pass


# -----------------------------
# CONFIG FILE
# -----------------------------

INSTANCE_LOCK_PATH = Path("/tmp/weather_led_strip.lock")
INSTANCE_LOCK_FILE = None


CONFIG = load_config()


# -----------------------------
# SETTINGS FROM CONFIG
# -----------------------------

LED_COUNT = int(CONFIG["led_count"])
LED_PIN = int(CONFIG["led_pin"])
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = int(CONFIG["led_brightness"])
LED_INVERT = False
LED_CHANNEL = 0

LATITUDE = float(CONFIG["latitude"])
LONGITUDE = float(CONFIG["longitude"])

WEATHER_REFRESH_SECONDS = int(CONFIG["weather_refresh_seconds"])
ANIMATION_FRAME_DELAY = float(CONFIG["animation_frame_delay"])

QUIET_HOURS_ENABLED = bool(CONFIG["quiet_hours_enabled"])
QUIET_START_HOUR = int(CONFIG["quiet_start_hour"])
QUIET_END_HOUR = int(CONFIG["quiet_end_hour"])
QUIET_CHECK_SECONDS = int(CONFIG["quiet_check_seconds"])


strip = None


# -----------------------------
# PROCESS / LED SETUP
# -----------------------------

def acquire_instance_lock():
    global INSTANCE_LOCK_FILE

    INSTANCE_LOCK_FILE = INSTANCE_LOCK_PATH.open("a+")
    try:
        fcntl.flock(INSTANCE_LOCK_FILE, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(
            f"Another weather LED strip process already holds {INSTANCE_LOCK_PATH}. Exiting.",
            flush=True
        )
        sys.exit(0)

    INSTANCE_LOCK_FILE.seek(0)
    INSTANCE_LOCK_FILE.truncate()
    INSTANCE_LOCK_FILE.write(str(os.getpid()))
    INSTANCE_LOCK_FILE.flush()


def init_led_strip():
    global strip

    if strip is not None:
        return

    strip = PixelStrip(
        LED_COUNT,
        LED_PIN,
        LED_FREQ_HZ,
        LED_DMA,
        LED_INVERT,
        LED_BRIGHTNESS,
        LED_CHANNEL
    )

    strip.begin()


# -----------------------------
# BASIC LED HELPERS
# -----------------------------

def rgb(r, g, b):
    return Color(int(r), int(g), int(b))


def set_all(color):
    if strip is None:
        return

    for i in range(LED_COUNT):
        strip.setPixelColor(i, color)
    strip.show()


def clear():
    set_all(rgb(0, 0, 0))


# -----------------------------
# DAY/NIGHT WEATHER ANIMATIONS
# -----------------------------

def animate_sunny_day(duration=30):
    start = time.time()

    while time.time() - start < duration:
        t = time.time()

        for i in range(LED_COUNT):
            wave = (math.sin(t * 2.5 + i * 0.35) + 1) / 2
            brightness = 0.45 + wave * 0.55
            strip.setPixelColor(
                i,
                rgb(255 * brightness, 170 * brightness, 15 * brightness)
            )

        strip.show()
        time.sleep(ANIMATION_FRAME_DELAY)


def animate_clear_night(duration=30):
    start = time.time()

    while time.time() - start < duration:
        t = time.time()

        for i in range(LED_COUNT):
            wave = (math.sin(t * 1.2 + i * 0.12) + 1) / 2
            blue = 18 + wave * 20
            strip.setPixelColor(i, rgb(0, 0, blue))

        moon_center = int((t * 2.2) % LED_COUNT)

        for offset in range(-5, 6):
            idx = (moon_center + offset) % LED_COUNT
            fade = 1 - abs(offset) / 6
            strip.setPixelColor(idx, rgb(40 * fade, 70 * fade, 130 * fade))

        if random.random() < 0.08:
             idx = random.randint(0, LED_COUNT - 1)
             strip.setPixelColor(idx, rgb(160, 190, 240))

        strip.show()
        time.sleep(0.08)


def animate_partly_cloudy_day(duration=30):
    start = time.time()

    while time.time() - start < duration:
        t = time.time()

        for i in range(LED_COUNT):
            strip.setPixelColor(i, rgb(255, 150, 0))

        cloud_center_1 = int((t * 8) % LED_COUNT)
        cloud_center_2 = int((t * 8 + LED_COUNT / 2) % LED_COUNT)

        for center in [cloud_center_1, cloud_center_2]:
            for offset in range(-5, 6):
                idx = (center + offset) % LED_COUNT
                fade = 1 - abs(offset) / 6
                level = 80 + 170 * fade
                strip.setPixelColor(idx, rgb(level, level, level))

        strip.show()
        time.sleep(0.06)


def animate_partly_cloudy_night(duration=30):
    start = time.time()

    while time.time() - start < duration:
        t = time.time()

        for i in range(LED_COUNT):
            strip.setPixelColor(i, rgb(0, 0, 18))

        cloud_center_1 = int((t * 4) % LED_COUNT)
        cloud_center_2 = int((t * 4 + LED_COUNT / 2) % LED_COUNT)

        for center in [cloud_center_1, cloud_center_2]:
            for offset in range(-6, 7):
                idx = (center + offset) % LED_COUNT
                fade = 1 - abs(offset) / 7
                level = 35 + 90 * fade
                strip.setPixelColor(idx, rgb(level, level, level + 15))

        if random.random() < 0.15:
            idx = random.randint(0, LED_COUNT - 1)
            strip.setPixelColor(idx, rgb(160, 190, 255))

        strip.show()
        time.sleep(0.08)


def animate_cloudy_day(duration=30):
    start = time.time()

    while time.time() - start < duration:
        t = time.time()

        for i in range(LED_COUNT):
            strip.setPixelColor(i, rgb(20, 25, 35))

        cloud_center_1 = int((t * 5) % LED_COUNT)
        cloud_center_2 = int((t * 5 + LED_COUNT / 3) % LED_COUNT)
        cloud_center_3 = int((t * 5 + 2 * LED_COUNT / 3) % LED_COUNT)

        for center in [cloud_center_1, cloud_center_2, cloud_center_3]:
            for offset in range(-7, 8):
                idx = (center + offset) % LED_COUNT
                fade = 1 - abs(offset) / 8
                level = 90 + 165 * fade
                strip.setPixelColor(idx, rgb(level, level, level))

        strip.show()
        time.sleep(0.06)


def animate_cloudy_night(duration=30):
    start = time.time()

    while time.time() - start < duration:
        t = time.time()

        for i in range(LED_COUNT):
            strip.setPixelColor(i, rgb(4, 4, 12))

        centers = [
            int((t * 2.5) % LED_COUNT),
            int((t * 2.5 + LED_COUNT / 3) % LED_COUNT),
            int((t * 2.5 + 2 * LED_COUNT / 3) % LED_COUNT)
        ]

        for center in centers:
            for offset in range(-8, 9):
                idx = (center + offset) % LED_COUNT
                fade = 1 - abs(offset) / 9
                strip.setPixelColor(idx, rgb(35 * fade, 38 * fade, 55 * fade))

        strip.show()
        time.sleep(0.10)


def animate_rain_day(duration=30, heavy=False):
    start = time.time()
    drops = []

    while time.time() - start < duration:
        for i in range(LED_COUNT):
            strip.setPixelColor(i, rgb(0, 0, 18))

        if random.random() < (0.55 if heavy else 0.28):
            drops.append({
                "pos": 0,
                "speed": random.uniform(0.7, 1.8 if heavy else 1.2),
                "length": random.randint(2, 5 if heavy else 4)
            })

        new_drops = []

        for drop in drops:
            pos = int(drop["pos"])
            length = drop["length"]

            for tail in range(length):
                idx = pos - tail
                if 0 <= idx < LED_COUNT:
                    fade = 1.0 - (tail / length)
                    strip.setPixelColor(idx, rgb(25 * fade, 90 * fade, 255 * fade))

            drop["pos"] += drop["speed"]

            if drop["pos"] < LED_COUNT + length:
                new_drops.append(drop)

        drops = new_drops

        strip.show()
        time.sleep(0.05)


def animate_rain_night(duration=30, heavy=False):
    start = time.time()
    drops = []

    while time.time() - start < duration:
        for i in range(LED_COUNT):
            strip.setPixelColor(i, rgb(0, 0, 8))

        if random.random() < (0.5 if heavy else 0.25):
            drops.append({
                "pos": 0,
                "speed": random.uniform(0.6, 1.5 if heavy else 1.0),
                "length": random.randint(2, 5 if heavy else 4)
            })

        new_drops = []

        for drop in drops:
            pos = int(drop["pos"])
            length = drop["length"]

            for tail in range(length):
                idx = pos - tail
                if 0 <= idx < LED_COUNT:
                    fade = 1.0 - (tail / length)
                    strip.setPixelColor(idx, rgb(0, 70 * fade, 180 * fade))

            drop["pos"] += drop["speed"]

            if drop["pos"] < LED_COUNT + length:
                new_drops.append(drop)

        drops = new_drops

        strip.show()
        time.sleep(0.06)


def animate_drizzle_day(duration=30):
    start = time.time()
    drops = []

    while time.time() - start < duration:
        for i in range(LED_COUNT):
            strip.setPixelColor(i, rgb(0, 8, 20))

        if random.random() < 0.15:
            drops.append({
                "pos": 0,
                "speed": random.uniform(0.35, 0.75),
                "length": random.randint(1, 3)
            })

        new_drops = []

        for drop in drops:
            pos = int(drop["pos"])

            for tail in range(drop["length"]):
                idx = pos - tail
                if 0 <= idx < LED_COUNT:
                    fade = 1.0 - (tail / max(drop["length"], 1))
                    strip.setPixelColor(idx, rgb(20 * fade, 120 * fade, 180 * fade))

            drop["pos"] += drop["speed"]

            if drop["pos"] < LED_COUNT + 3:
                new_drops.append(drop)

        drops = new_drops
        strip.show()
        time.sleep(0.07)


def animate_drizzle_night(duration=30):
    start = time.time()
    drops = []

    while time.time() - start < duration:
        for i in range(LED_COUNT):
            strip.setPixelColor(i, rgb(0, 4, 10))

        if random.random() < 0.12:
            drops.append({
                "pos": 0,
                "speed": random.uniform(0.25, 0.6),
                "length": random.randint(1, 3)
            })

        new_drops = []

        for drop in drops:
            pos = int(drop["pos"])

            for tail in range(drop["length"]):
                idx = pos - tail
                if 0 <= idx < LED_COUNT:
                    fade = 1.0 - (tail / max(drop["length"], 1))
                    strip.setPixelColor(idx, rgb(0, 70 * fade, 120 * fade))

            drop["pos"] += drop["speed"]

            if drop["pos"] < LED_COUNT + 3:
                new_drops.append(drop)

        drops = new_drops
        strip.show()
        time.sleep(0.09)


def animate_snow_day(duration=30):
    start = time.time()
    flakes = []

    while time.time() - start < duration:
        for i in range(LED_COUNT):
            strip.setPixelColor(i, rgb(2, 8, 18))

        if random.random() < 0.35:
            flakes.append({
                "pos": 0,
                "speed": random.uniform(0.15, 0.55),
                "brightness": random.uniform(0.5, 1.0)
            })

        new_flakes = []

        for flake in flakes:
            pos = int(flake["pos"])
            brightness = flake["brightness"]

            if 0 <= pos < LED_COUNT:
                strip.setPixelColor(pos, rgb(180 * brightness, 220 * brightness, 255 * brightness))

            if random.random() < 0.08:
                sparkle = random.randint(0, LED_COUNT - 1)
                strip.setPixelColor(sparkle, rgb(80, 120, 160))

            flake["pos"] += flake["speed"]

            if flake["pos"] < LED_COUNT:
                new_flakes.append(flake)

        flakes = new_flakes
        strip.show()
        time.sleep(0.08)


def animate_snow_night(duration=30):
    start = time.time()
    flakes = []

    while time.time() - start < duration:
        for i in range(LED_COUNT):
            strip.setPixelColor(i, rgb(0, 3, 14))

        if random.random() < 0.30:
            flakes.append({
                "pos": 0,
                "speed": random.uniform(0.12, 0.45),
                "brightness": random.uniform(0.55, 1.0)
            })

        new_flakes = []

        for flake in flakes:
            pos = int(flake["pos"])
            brightness = flake["brightness"]

            if 0 <= pos < LED_COUNT:
                strip.setPixelColor(pos, rgb(160 * brightness, 210 * brightness, 255 * brightness))

            if random.random() < 0.12:
                sparkle = random.randint(0, LED_COUNT - 1)
                strip.setPixelColor(sparkle, rgb(220, 240, 255))

            flake["pos"] += flake["speed"]

            if flake["pos"] < LED_COUNT:
                new_flakes.append(flake)

        flakes = new_flakes
        strip.show()
        time.sleep(0.10)


def animate_storm_day(duration=30):
    start = time.time()

    while time.time() - start < duration:
        for i in range(LED_COUNT):
            strip.setPixelColor(i, rgb(8, 0, 25))

        pulse_pos = int((time.time() * 12) % LED_COUNT)

        for offset in range(-4, 5):
            idx = pulse_pos + offset
            if 0 <= idx < LED_COUNT:
                brightness = 1 - abs(offset) / 5
                strip.setPixelColor(idx, rgb(60 * brightness, 0, 120 * brightness))

        strip.show()
        time.sleep(0.04)

        if random.random() < 0.08:
            for _ in range(random.randint(1, 3)):
                for i in range(LED_COUNT):
                    strip.setPixelColor(i, rgb(255, 255, 190))
                strip.show()
                time.sleep(random.uniform(0.03, 0.08))

                for i in range(LED_COUNT):
                    strip.setPixelColor(i, rgb(8, 0, 25))
                strip.show()
                time.sleep(random.uniform(0.04, 0.12))


def animate_storm_night(duration=30):
    start = time.time()

    while time.time() - start < duration:
        for i in range(LED_COUNT):
            strip.setPixelColor(i, rgb(3, 0, 12))

        pulse_pos = int((time.time() * 8) % LED_COUNT)

        for offset in range(-5, 6):
            idx = pulse_pos + offset
            if 0 <= idx < LED_COUNT:
                brightness = 1 - abs(offset) / 6
                strip.setPixelColor(idx, rgb(30 * brightness, 0, 80 * brightness))

        strip.show()
        time.sleep(0.05)

        if random.random() < 0.08:
            for _ in range(random.randint(1, 3)):
                for i in range(LED_COUNT):
                    strip.setPixelColor(i, rgb(255, 255, 230))
                strip.show()
                time.sleep(random.uniform(0.03, 0.08))

                for i in range(LED_COUNT):
                    strip.setPixelColor(i, rgb(3, 0, 12))
                strip.show()
                time.sleep(random.uniform(0.04, 0.15))


def animate_ice_day(duration=30):
    start = time.time()

    while time.time() - start < duration:
        for i in range(LED_COUNT):
            strip.setPixelColor(i, rgb(0, 35, 55))

        for _ in range(random.randint(3, 10)):
            idx = random.randint(0, LED_COUNT - 1)
            strip.setPixelColor(idx, rgb(160, 255, 255))

        strip.show()
        time.sleep(0.12)


def animate_ice_night(duration=30):
    start = time.time()

    while time.time() - start < duration:
        for i in range(LED_COUNT):
            strip.setPixelColor(i, rgb(0, 12, 22))

        for _ in range(random.randint(2, 8)):
            idx = random.randint(0, LED_COUNT - 1)
            strip.setPixelColor(idx, rgb(120, 230, 255))

        strip.show()
        time.sleep(0.15)


def animate_fog_day(duration=30):
    start = time.time()

    while time.time() - start < duration:
        t = time.time()

        for i in range(LED_COUNT):
            wave = (math.sin(t * 0.7 + i * 0.09) + 1) / 2
            level = 25 + wave * 45
            strip.setPixelColor(i, rgb(level, level, level + 5))

        strip.show()
        time.sleep(0.12)


def animate_fog_night(duration=30):
    start = time.time()

    while time.time() - start < duration:
        t = time.time()

        for i in range(LED_COUNT):
            wave = (math.sin(t * 0.45 + i * 0.06) + 1) / 2
            level = 8 + wave * 28
            strip.setPixelColor(i, rgb(level, level, level + 8))

        strip.show()
        time.sleep(0.15)


def animate_unknown(duration=30, is_night=False):
    start = time.time()

    while time.time() - start < duration:
        color = rgb(20, 10, 50) if is_night else rgb(40, 20, 80)

        for i in range(LED_COUNT):
            strip.setPixelColor(i, color)

        strip.show()
        time.sleep(0.5)


# -----------------------------
# MAIN LOOP
# -----------------------------

def run_animation_for_condition(condition, precip_probability=0, is_night=False):
    mode = "night" if is_night else "day"
    print(f"Running animation: {condition} / {mode}", flush=True)

    heavy = precip_probability >= 70

    if condition == "sunny":
        if is_night:
            animate_clear_night(duration=30)
        else:
            animate_sunny_day(duration=30)

    elif condition == "partly_cloudy":
        if is_night:
            animate_partly_cloudy_night(duration=30)
        else:
            animate_partly_cloudy_day(duration=30)

    elif condition == "cloudy":
        if is_night:
            animate_cloudy_night(duration=30)
        else:
            animate_cloudy_day(duration=30)

    elif condition == "rain":
        if is_night:
            animate_rain_night(duration=30, heavy=heavy)
        else:
            animate_rain_day(duration=30, heavy=heavy)

    elif condition == "drizzle":
        if is_night:
            animate_drizzle_night(duration=30)
        else:
            animate_drizzle_day(duration=30)

    elif condition == "snow":
        if is_night:
            animate_snow_night(duration=30)
        else:
            animate_snow_day(duration=30)

    elif condition == "storm":
        if is_night:
            animate_storm_night(duration=30)
        else:
            animate_storm_day(duration=30)

    elif condition == "ice":
        if is_night:
            animate_ice_night(duration=30)
        else:
            animate_ice_day(duration=30)

    elif condition == "fog":
        if is_night:
            animate_fog_night(duration=30)
        else:
            animate_fog_day(duration=30)

    else:
        animate_unknown(duration=30, is_night=is_night)


def shutdown_handler(sig, frame):
    clear()
    sys.exit(0)


signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)


def main():
    acquire_instance_lock()
    init_led_strip()

    print("Starting weather LED strip...", flush=True)
    print("Press Ctrl+C to stop.", flush=True)

    print(
        f"Loaded config: "
        f"LED_COUNT={LED_COUNT}, "
        f"LED_PIN={LED_PIN}, "
        f"BRIGHTNESS={LED_BRIGHTNESS}, "
        f"LAT={LATITUDE}, "
        f"LON={LONGITUDE}, "
        f"QUIET={QUIET_HOURS_ENABLED}, "
        f"QUIET_START={QUIET_START_HOUR}, "
        f"QUIET_END={QUIET_END_HOUR}",
        flush=True
    )

    current_weather = None
    last_weather_fetch = 0
    quiet_logged = False

    while True:
        runtime_config = load_config()

        quiet_start = int(runtime_config.get("quiet_start_hour", QUIET_START_HOUR))
        quiet_end = int(runtime_config.get("quiet_end_hour", QUIET_END_HOUR))
        quiet_check_seconds = max(
            1,
            int(runtime_config.get("quiet_check_seconds", QUIET_CHECK_SECONDS))
        )

        new_brightness = int(runtime_config.get("led_brightness", LED_BRIGHTNESS))
        if strip is not None and strip.getBrightness() != new_brightness:
            strip.setBrightness(new_brightness)
            strip.show()

        test_mode_enabled = bool(runtime_config.get("test_mode_enabled", False))

        if is_quiet_hours(runtime_config):
            clear()

            if not quiet_logged:
                print(
                    f"Quiet hours active. LEDs off. "
                    f"Quiet window: {quiet_start}:00 to {quiet_end}:00. "
                    f"Checking again in {quiet_check_seconds} seconds.",
                    flush=True
                )
                quiet_logged = True

            time.sleep(quiet_check_seconds)
            continue

        if quiet_logged:
            print("Quiet hours ended. Resuming weather LED animations.", flush=True)
            current_weather = None
            last_weather_fetch = 0
            quiet_logged = False

        if test_mode_enabled:
            test_condition = runtime_config.get("test_condition", "sunny")
            test_is_night = bool(runtime_config.get("test_is_night", False))
            test_precip_probability = int(runtime_config.get("test_precipitation_probability", 0))

            print(
                f"TEST MODE active: condition={test_condition}, "
                f"is_night={test_is_night}, "
                f"precip_prob={test_precip_probability}",
                flush=True
            )

            run_animation_for_condition(
                test_condition,
                test_precip_probability,
                test_is_night
            )

            continue

        weather_refresh_seconds = int(runtime_config.get("weather_refresh_seconds", WEATHER_REFRESH_SECONDS))
        now = time.time()

        if current_weather is None or now - last_weather_fetch > weather_refresh_seconds:
            try:
                current_weather = fetch_next_hour_weather()
                last_weather_fetch = now

                condition = classify_weather(
                    current_weather["weather_code"],
                    current_weather["precipitation_probability"],
                    current_weather["precipitation"]
                )

                current_weather["condition"] = condition

                mode = "night" if current_weather["is_night"] else "day"

                print(
                    f"Next hour: {current_weather['time']} | "
                    f"code={current_weather['weather_code']} | "
                    f"condition={condition} | "
                    f"mode={mode} | "
                    f"sunrise={current_weather['sunrise']} | "
                    f"sunset={current_weather['sunset']} | "
                    f"precip_prob={current_weather['precipitation_probability']}% | "
                    f"temp={current_weather['temperature']}",
                    flush=True
                )

            except Exception as e:
                print(f"Weather fetch failed: {e}", flush=True)
                current_weather = {
                    "condition": "unknown",
                    "precipitation_probability": 0,
                    "is_night": False
                }

        systemd_watchdog_ping()

        try:
            run_animation_for_condition(
                current_weather["condition"],
                current_weather.get("precipitation_probability", 0),
                current_weather.get("is_night", False)
            )
        except Exception as e:
            print(f"Animation error: {e}", flush=True)
            clear()
            time.sleep(5)


if __name__ == "__main__":
    main()
