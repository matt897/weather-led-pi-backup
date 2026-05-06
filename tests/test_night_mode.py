import sys
import json
import types
import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock

fake_rpi = types.ModuleType("rpi_ws281x")


class FakePixelStrip:
    def __init__(self, *args, **kwargs):
        self._brightness = args[5] if len(args) > 5 else 255

    def begin(self):
        pass

    def setPixelColor(self, *args, **kwargs):
        pass

    def show(self):
        pass

    def getBrightness(self):
        return self._brightness

    def setBrightness(self, value):
        self._brightness = value


def fake_color(r, g, b):
    return (r, g, b)


fake_rpi.PixelStrip = FakePixelStrip
fake_rpi.Color = fake_color
sys.modules["rpi_ws281x"] = fake_rpi
sys.modules["requests"] = types.ModuleType("requests")

import weather_led_strip as led


def _make_api_response(local_now_iso, sunrise_iso, sunset_iso, timezone="America/New_York"):
    """Build a minimal Open-Meteo response dict for the given timezone and sun times."""
    return {
        "timezone": timezone,
        "hourly": {
            "time": [local_now_iso],
            "weather_code": [0],
            "precipitation_probability": [0],
            "precipitation": [0.0],
            "temperature_2m": [15.0],
        },
        "daily": {
            "sunrise": [sunrise_iso, sunrise_iso],
            "sunset": [sunset_iso, sunset_iso],
        },
    }


class NightModeTimezoneTests(unittest.TestCase):
    def _fetch_with_utc_clock(self, utc_now, api_response):
        """Simulate fetch_next_hour_weather with the system clock set to utc_now (UTC)."""
        fake_resp = MagicMock()
        fake_resp.json.return_value = api_response

        with patch("weather_led_strip.requests") as mock_requests, \
             patch("weather_led_strip.datetime") as mock_dt, \
             patch("weather_led_strip.load_config", return_value={"latitude": 40.856, "longitude": -73.793}):

            mock_requests.get.return_value = fake_resp

            # datetime.now(tz=...) should return the UTC instant so that
            # .replace(tzinfo=None) gives the correct local time via ZoneInfo.
            # We use the real datetime for fromisoformat but stub now().
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            mock_dt.now.side_effect = lambda tz=None: (
                utc_now.replace(tzinfo=__import__("zoneinfo").ZoneInfo("UTC")).astimezone(tz).replace(tzinfo=None)
                if tz else utc_now
            )

            return led.fetch_next_hour_weather()

    def test_night_at_2am_edt_with_utc_pi(self):
        """
        2 AM EDT = 6 AM UTC. The old code compared UTC 06:00 against EDT
        sunrise 05:50 and concluded it was daytime. Fixed code uses local time.
        """
        utc_now = datetime(2026, 5, 6, 6, 0)  # 2 AM EDT expressed in UTC
        api = _make_api_response(
            local_now_iso="2026-05-06T02:00",
            sunrise_iso="2026-05-06T05:50",
            sunset_iso="2026-05-06T19:54",
        )
        result = self._fetch_with_utc_clock(utc_now, api)
        self.assertTrue(result["is_night"], "Should be night at 2 AM local time")

    def test_night_at_3am_edt_with_utc_pi(self):
        utc_now = datetime(2026, 5, 6, 7, 0)  # 3 AM EDT in UTC
        api = _make_api_response(
            local_now_iso="2026-05-06T03:00",
            sunrise_iso="2026-05-06T05:50",
            sunset_iso="2026-05-06T19:54",
        )
        result = self._fetch_with_utc_clock(utc_now, api)
        self.assertTrue(result["is_night"], "Should be night at 3 AM local time")

    def test_day_mode_at_noon_edt_with_utc_pi(self):
        utc_now = datetime(2026, 5, 6, 16, 0)  # Noon EDT in UTC
        api = _make_api_response(
            local_now_iso="2026-05-06T12:00",
            sunrise_iso="2026-05-06T05:50",
            sunset_iso="2026-05-06T19:54",
        )
        result = self._fetch_with_utc_clock(utc_now, api)
        self.assertFalse(result["is_night"], "Should be day at noon local time")

    def test_night_after_sunset_edt_with_utc_pi(self):
        utc_now = datetime(2026, 5, 6, 23, 55)  # 7:55 PM EDT in UTC
        api = _make_api_response(
            local_now_iso="2026-05-06T19:55",
            sunrise_iso="2026-05-06T05:50",
            sunset_iso="2026-05-06T19:54",
        )
        result = self._fetch_with_utc_clock(utc_now, api)
        self.assertTrue(result["is_night"], "Should be night after sunset")


if __name__ == "__main__":
    unittest.main()
