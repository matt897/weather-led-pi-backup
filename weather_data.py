#!/usr/bin/env python3
"""Shared, hardware-free weather/config logic used by the LED strip script,
the Flask admin/kiosk web app, and the kiosk screen-blanking script."""

import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import requests


CONFIG_PATH = Path("/home/matt/weather_led_config.json")


DEFAULT_CONFIG = {
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
    "test_precipitation_probability": 0,
    "kiosk_quiet_hours_enabled": True,
    "kiosk_blank_check_seconds": 30
}


def load_config():
    defaults = DEFAULT_CONFIG.copy()

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


def save_config(config):
    with CONFIG_PATH.open("w") as f:
        json.dump(config, f, indent=2)


# -----------------------------
# WEATHER FETCHING
# -----------------------------

def fetch_next_hour_weather():
    """
    Gets hourly forecast data plus today's sunrise/sunset from Open-Meteo.
    Uses timezone=auto, so returned times are local to the lat/lon.
    """

    runtime_config = load_config()
    latitude = float(runtime_config["latitude"])
    longitude = float(runtime_config["longitude"])

    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "weather_code,precipitation_probability,precipitation,temperature_2m",
        "daily": "sunrise,sunset",
        "forecast_days": 2,
        "timezone": "auto",
        "temperature_unit": "fahrenheit"
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

    local_tz = ZoneInfo(data.get("timezone", "UTC"))
    now = datetime.now(tz=local_tz).replace(tzinfo=None)

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
# QUIET HOURS
# -----------------------------

def quiet_hours_active(quiet_enabled, quiet_start, quiet_end, current_hour):
    if not quiet_enabled:
        return False

    if quiet_start == quiet_end:
        return False

    if quiet_start < quiet_end:
        return quiet_start <= current_hour < quiet_end

    return current_hour >= quiet_start or current_hour < quiet_end


def is_quiet_hours(runtime_config=None, now=None):
    """
    Returns True when current local time is inside quiet hours.

    Handles:
    - Overnight windows like 22 to 7
    - Same-day windows like 13 to 16
    """
    if runtime_config is None:
        runtime_config = load_config()

    quiet_enabled = bool(runtime_config.get("quiet_hours_enabled", DEFAULT_CONFIG["quiet_hours_enabled"]))
    quiet_start = int(runtime_config.get("quiet_start_hour", DEFAULT_CONFIG["quiet_start_hour"]))
    quiet_end = int(runtime_config.get("quiet_end_hour", DEFAULT_CONFIG["quiet_end_hour"]))

    if now is None:
        now = datetime.now()

    return quiet_hours_active(quiet_enabled, quiet_start, quiet_end, now.hour)
