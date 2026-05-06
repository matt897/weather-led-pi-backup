import sys
import types
import unittest
from datetime import datetime


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


class QuietHoursTests(unittest.TestCase):
    def test_disabled_quiet_hours(self):
        self.assertFalse(led.quiet_hours_active(False, 22, 7, 23))

    def test_equal_start_and_end_disables_quiet_hours(self):
        self.assertFalse(led.quiet_hours_active(True, 22, 22, 22))

    def test_overnight_window_before_midnight(self):
        self.assertTrue(led.quiet_hours_active(True, 22, 7, 23))

    def test_overnight_window_after_midnight(self):
        self.assertTrue(led.quiet_hours_active(True, 22, 7, 3))

    def test_same_day_window(self):
        self.assertTrue(led.quiet_hours_active(True, 13, 16, 14))

    def test_outside_quiet_window(self):
        self.assertFalse(led.quiet_hours_active(True, 22, 7, 12))

    def test_runtime_config_is_re_evaluated(self):
        quiet_config = {
            "quiet_hours_enabled": True,
            "quiet_start_hour": 22,
            "quiet_end_hour": 7,
        }
        disabled_config = {
            "quiet_hours_enabled": False,
            "quiet_start_hour": 22,
            "quiet_end_hour": 7,
        }
        now = datetime(2026, 1, 1, 23, 30)

        self.assertTrue(led.is_quiet_hours(quiet_config, now=now))
        self.assertFalse(led.is_quiet_hours(disabled_config, now=now))


if __name__ == "__main__":
    unittest.main()
