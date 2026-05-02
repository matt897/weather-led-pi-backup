#!/usr/bin/env python3

import time
import math
import random
import signal
import sys
import json
from pathlib import Path
from datetime import datetime

import requests
from rpi_ws281x import PixelStrip, Color


# -----------------------------
# CONFIG FILE
# -----------------------------

CONFIG_PATH = Path("/home/matt/weather_led_config.json")


def load_config():
    defaults = {
        "led_count": 60,
        "led_pin": 18,
        "led_brightness": 80,
        "latitude": 40.856202,
        "longitude": -73.793085,
        "weather_refresh_seconds": 900,
        "animation_frame_delay": 0.05,
        "quiet_hours_enabled": True,
        "quiet_start_hour": 22,
        "quiet_end_hour": 7,
        "quiet_check_seconds": 60,
        "test_mode_enabled": False,
        "test_condition": "sunny",
        "test_is_night": False,
        "test_precipitation_probability": 0
    }

    try:
        if CONFIG_PATH.exists():
            with CONFIG_PATH.open("r") as f:
                loaded = json.load(f)
            defaults.update(loaded)
        else:
            print(f"Config file not found at {CONFIG_PATH}. Using defaults.", flush=True)

    except Exception as e:
        print(f"Could not load config, using defaults: {e}", flush=True)

    return defaults


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


# -----------------------------
# LED SETUP
# -----------------------------

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
    for i in range(LED_COUNT):
        strip.setPixelColor(i, color)
    strip.show()


def clear():
    set_all(rgb(0, 0, 0))


def is_quiet_hours():
    """
    Returns True when current local time is inside quiet hours.

    Handles:
    - Overnight windows like 22 to 7
    - Same-day windows like 13 to 16
    """
    runtime_config = load_config()

    quiet_enabled = bool(runtime_config.get("quiet_hours_enabled", QUIET_HOURS_ENABLED))
    quiet_start = int(runtime_config.get("quiet_start_hour", QUIET_START_HOUR))
    quiet_end = int(runtime_config.get("quiet_end_hour", QUIET_END_HOUR))

    if not quiet_enabled:
        return False

    current_hour = datetime.now().hour

    if quiet_start == quiet_end:
        return False

    if quiet_start < quiet_end:
        return quiet_start <= current_hour < quiet_end

    return current_hour >= quiet_start or current_hour < quiet_end


# -----------------------------
# WEATHER FETCHING
# -----------------------------

def fetch_next_hour_weather():
    """
    Gets hourly forecast data plus today's sunrise/sunset from Open-Meteo.
    Uses timezone=auto, so returned times are local to the lat/lon.
    """

    runtime_config = load_config()
    latitude = float(runtime_config.get("latitude", LATITUDE))
    longitude = float(runtime_config.get("longitude", LONGITUDE))

    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "weather_code,precipitation_probability,precipitation,temperature_2m",
        "daily": "sunrise,sunset",
        "forecast_days": 2,
        "timezone": "auto"
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()
    hourly = data["hourly"]
    daily = data["daily"]

    times = hourly["time"]
    weather_codes = hourly["weather_code"]
    precip_probs = hourly["precipitation_probability"]
    precip_amounts = hourly["precipitation"]
    temps = hourly["temperature_2m"]

    now = datetime.now()

    sunrise = datetime.fromisoformat(daily["sunrise"][0])
    sunset = datetime.fromisoformat(daily["sunset"][0])

    is_night = now < sunrise or now >= sunset

    for i, t in enumerate(times):
        forecast_time = datetime.fromisoformat(t)

        if forecast_time >= now.replace(minute=0, second=0, microsecond=0):
            return {
                "time": t,
                "weather_code": weather_codes[i],
                "precipitation_probability": precip_probs[i],
                "precipitation": precip_amounts[i],
                "temperature": temps[i],
                "sunrise": sunrise.isoformat(),
                "sunset": sunset.isoformat(),
                "is_night": is_night
            }

    return {
        "time": times[-1],
        "weather_code": weather_codes[-1],
        "precipitation_probability": precip_probs[-1],
        "precipitation": precip_amounts[-1],
        "temperature": temps[-1],
        "sunrise": sunrise.isoformat(),
        "sunset": sunset.isoformat(),
        "is_night": is_night
    }


def classify_weather(weather_code, precip_probability=0, precipitation=0):
    """
    Groups Open-Meteo weather codes into visual animation categories.
    """

    if weather_code in [95, 96, 99]:
        return "storm"

    if weather_code in [71, 73, 75, 77, 85, 86]:
        return "snow"

    if weather_code in [56, 57, 66, 67]:
        return "ice"

    if weather_code in [61, 63, 65, 80, 81, 82]:
        return "rain"

    if weather_code in [51, 53, 55]:
        return "drizzle"

    if weather_code in [45, 48]:
        return "fog"

    if weather_code == 3:
        return "cloudy"

    if weather_code in [1, 2]:
        return "partly_cloudy"

    if weather_code == 0:
        return "sunny"

    if precip_probability >= 60 or precipitation > 0:
        return "rain"

    return "unknown"


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

    while True:
        runtime_config = load_config()

        quiet_enabled = bool(runtime_config.get("quiet_hours_enabled", QUIET_HOURS_ENABLED))
        quiet_start = int(runtime_config.get("quiet_start_hour", QUIET_START_HOUR))
        quiet_end = int(runtime_config.get("quiet_end_hour", QUIET_END_HOUR))

        test_mode_enabled = bool(runtime_config.get("test_mode_enabled", False))

        # Test mode overrides quiet hours so you can preview LEDs at any time.
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

        # Quiet hours only apply when not in test mode.
        if quiet_enabled:
            current_hour = datetime.now().hour

            if quiet_start == quiet_end:
                quiet_now = False
            elif quiet_start < quiet_end:
                quiet_now = quiet_start <= current_hour < quiet_end
            else:
                quiet_now = current_hour >= quiet_start or current_hour < quiet_end

            if quiet_now:
                clear()
                print(
                    f"Quiet hours active. LEDs off. "
                    f"Quiet window: {quiet_start}:00 to {quiet_end}:00. "
                    f"Exiting until next scheduled start.",
                    flush=True
                )
                sys.exit(0)

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

        run_animation_for_condition(
            current_weather["condition"],
            current_weather.get("precipitation_probability", 0),
            current_weather.get("is_night", False)
        )


if __name__ == "__main__":
    main()
