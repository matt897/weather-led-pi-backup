#!/usr/bin/env python3

import time
import subprocess
from flask import Flask, request, redirect, render_template_string, jsonify

from weather_data import (
    load_config,
    save_config,
    fetch_next_hour_weather,
    classify_weather,
)

app = Flask(__name__)


WEATHER_CARDS = [
    {
        "condition": "sunny",
        "title": "Clear",
        "icon": "☀️",
        "description": "Golden sunlight by day, moonlight and stars at night.",
        "day_swatches": ["#ffcc33", "#ff9500", "#fff3a3"],
        "night_swatches": ["#000012", "#294682", "#dbeafe"]
    },
    {
        "condition": "partly_cloudy",
        "title": "Partly Cloudy",
        "icon": "⛅",
        "description": "Sun and drifting clouds, or silver clouds after sunset.",
        "day_swatches": ["#ffb000", "#ffffff", "#b8b8b8"],
        "night_swatches": ["#000018", "#6b7280", "#c7d2fe"]
    },
    {
        "condition": "cloudy",
        "title": "Cloudy",
        "icon": "☁️",
        "description": "Moving gray clouds over a muted sky.",
        "day_swatches": ["#141923", "#d1d5db", "#ffffff"],
        "night_swatches": ["#04040c", "#252837", "#5b647a"]
    },
    {
        "condition": "rain",
        "title": "Rain",
        "icon": "🌧️",
        "description": "Falling blue drops. Heavy rain uses brighter, faster motion.",
        "day_swatches": ["#000012", "#195aff", "#7dd3fc"],
        "night_swatches": ["#000008", "#0046b4", "#00a7cc"]
    },
    {
        "condition": "drizzle",
        "title": "Drizzle",
        "icon": "🌦️",
        "description": "Soft, sparse blue-green droplets.",
        "day_swatches": ["#000814", "#14b8a6", "#67e8f9"],
        "night_swatches": ["#00040a", "#075985", "#5eead4"]
    },
    {
        "condition": "snow",
        "title": "Snow",
        "icon": "❄️",
        "description": "White and icy-blue flakes with occasional sparkle.",
        "day_swatches": ["#020812", "#b4dcff", "#ffffff"],
        "night_swatches": ["#00030e", "#a5d8ff", "#f8fbff"]
    },
    {
        "condition": "storm",
        "title": "Storm",
        "icon": "⚡",
        "description": "Dark purple atmosphere with lightning flashes.",
        "day_swatches": ["#080019", "#3c0078", "#ffffbe"],
        "night_swatches": ["#03000c", "#24005f", "#ffffe6"]
    },
    {
        "condition": "ice",
        "title": "Ice",
        "icon": "🧊",
        "description": "Sharp cyan and white glitter for freezing rain or ice.",
        "day_swatches": ["#002337", "#a0ffff", "#ffffff"],
        "night_swatches": ["#000c16", "#78e6ff", "#e0ffff"]
    },
    {
        "condition": "fog",
        "title": "Fog",
        "icon": "🌫️",
        "description": "Low-contrast gray haze, dimmer and bluer at night.",
        "day_swatches": ["#1f2937", "#6b7280", "#d1d5db"],
        "night_swatches": ["#05080f", "#2f3b4d", "#7b8794"]
    }
]


WEATHER_CARDS_BY_CONDITION = {item["condition"]: item for item in WEATHER_CARDS}


DISPLAY_HTML = """
<!doctype html>
<html>
<head>
    <title>Weather Display</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <style>
        * {
            box-sizing: border-box;
        }

        html, body {
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100%;
            overflow: hidden;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }

        #bg {
            position: fixed;
            inset: 0;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            color: white;
            text-shadow: 0 4px 24px rgba(0,0,0,0.35);
            background: linear-gradient(160deg, #171126, #31204e 60%, #000);
        }

        #icon {
            font-size: 22vh;
            line-height: 1;
        }

        #condition-title {
            font-size: 6vh;
            font-weight: 800;
            letter-spacing: -0.02em;
            margin-top: 1vh;
        }

        #temperature {
            font-size: 16vh;
            font-weight: 900;
            letter-spacing: -0.04em;
            margin-top: 1vh;
        }

        #detail-row {
            display: flex;
            gap: 4vh;
            margin-top: 3vh;
            font-size: 2.6vh;
            opacity: 0.85;
        }

        #clock-wrap {
            position: fixed;
            bottom: 4vh;
            right: 5vh;
            text-align: right;
        }

        #clock {
            font-size: 4vh;
            font-weight: 800;
        }

        #date {
            font-size: 2vh;
            opacity: 0.8;
        }

        #status {
            position: fixed;
            top: 3vh;
            left: 5vh;
            font-size: 1.8vh;
            opacity: 0.55;
        }
    </style>
</head>

<body>
    <div id="bg">
        <div id="icon">⏳</div>
        <div id="condition-title">Loading weather&hellip;</div>
        <div id="temperature"></div>
        <div id="detail-row"></div>
    </div>

    <div id="status"></div>

    <div id="clock-wrap">
        <div id="clock"></div>
        <div id="date"></div>
    </div>

    <script>
        function updateClock() {
            var now = new Date();
            document.getElementById("clock").textContent = now.toLocaleTimeString([], {hour: "numeric", minute: "2-digit"});
            document.getElementById("date").textContent = now.toLocaleDateString([], {weekday: "long", month: "long", day: "numeric"});
        }

        function renderWeather(w) {
            var bg = document.getElementById("bg");
            var swatches = w.is_night ? w.night_swatches : w.day_swatches;

            bg.style.background = "linear-gradient(160deg, " + swatches[0] + ", " + swatches[1] + " 55%, " + swatches[2] + ")";

            document.getElementById("icon").textContent = w.icon;
            document.getElementById("condition-title").textContent = w.title + (w.is_night ? " · Night" : " · Day");
            document.getElementById("temperature").textContent = Math.round(w.temperature) + "°F";

            var details = [];
            if (w.precipitation_probability > 0) {
                details.push(w.precipitation_probability + "% chance of precip");
            }
            if (w.sunrise && w.sunset) {
                var sunrise = new Date(w.sunrise).toLocaleTimeString([], {hour: "numeric", minute: "2-digit"});
                var sunset = new Date(w.sunset).toLocaleTimeString([], {hour: "numeric", minute: "2-digit"});
                details.push("Sunrise " + sunrise + " · Sunset " + sunset);
            }
            document.getElementById("detail-row").textContent = details.join("   ");

            document.getElementById("status").textContent = w.error ? ("Weather unavailable: " + w.error) : "";
        }

        function refreshWeather() {
            fetch("/api/weather")
                .then(function (res) { return res.json(); })
                .then(renderWeather)
                .catch(function (err) {
                    document.getElementById("status").textContent = "Weather unavailable: " + err;
                });
        }

        updateClock();
        setInterval(updateClock, 1000);

        refreshWeather();
        setInterval(refreshWeather, 30000);
    </script>
</body>
</html>
"""


HTML = """
<!doctype html>
<html>
<head>
    <title>Weather LED Controller</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <style>
        :root {
            --bg: #f7f7f8;
            --surface: #ffffff;
            --surface-2: #f3f3f5;
            --surface-3: #e9e9ee;

            --border: #dedee6;
            --border-strong: #c7c7d2;

            --fg: #25252c;
            --fg-muted: #6d6d78;
            --fg-subtle: #8a8a96;

            --accent: #7c3aed;
            --accent-strong: #5b21b6;
            --accent-soft: #f1e8ff;
            --accent-ring: rgba(124, 58, 237, 0.18);

            --ok: #16a34a;
            --warn: #d97706;
            --danger: #dc2626;

            --radius: 12px;
            --radius-lg: 18px;
        }

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            padding: 32px 18px 60px;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background:
                radial-gradient(circle at top left, rgba(124, 58, 237, 0.12), transparent 34%),
                radial-gradient(circle at top right, rgba(14, 165, 233, 0.10), transparent 32%),
                var(--bg);
            color: var(--fg);
        }

        .page {
            max-width: 1120px;
            margin: 0 auto;
        }

        .hero {
            background: linear-gradient(135deg, #171126, #31204e);
            color: white;
            border-radius: 24px;
            padding: 26px;
            box-shadow: 0 20px 60px rgba(30, 20, 60, 0.20);
            margin-bottom: 22px;
        }

        .hero-top {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 18px;
            flex-wrap: wrap;
        }

        h1 {
            margin: 0;
            font-size: clamp(28px, 4vw, 42px);
            letter-spacing: -0.04em;
        }

        h2 {
            margin: 0 0 12px;
            font-size: 20px;
            letter-spacing: -0.02em;
        }

        h3 {
            margin: 0;
            font-size: 17px;
        }

        p {
            line-height: 1.5;
        }

        .hero p {
            color: rgba(255,255,255,0.72);
            margin-bottom: 0;
        }

        .pill-row {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 18px;
        }

        .pill {
            display: inline-flex;
            align-items: center;
            gap: 7px;
            border-radius: 999px;
            padding: 8px 11px;
            background: rgba(255,255,255,0.10);
            border: 1px solid rgba(255,255,255,0.16);
            color: rgba(255,255,255,0.88);
            font-size: 13px;
            font-weight: 700;
        }

        .dot {
            width: 8px;
            height: 8px;
            border-radius: 99px;
            display: inline-block;
            background: var(--ok);
            box-shadow: 0 0 0 4px rgba(22, 163, 74, 0.18);
        }

        .card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            padding: 22px;
            margin-bottom: 18px;
            box-shadow: 0 10px 30px rgba(20, 20, 35, 0.045);
        }

        .grid-2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 18px;
        }

        .row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 14px;
        }

        .status-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
            margin-top: 20px;
        }

        .stat {
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.13);
            border-radius: 15px;
            padding: 14px;
        }

        .stat-label {
            color: rgba(255,255,255,0.56);
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            font-weight: 800;
            margin-bottom: 4px;
        }

        .stat-value {
            font-size: 16px;
            font-weight: 900;
        }

        label {
            display: block;
            margin-top: 16px;
            font-weight: 800;
            font-size: 14px;
        }

        input,
        select {
            width: 100%;
            margin-top: 6px;
            padding: 11px 12px;
            border-radius: 11px;
            border: 1px solid var(--border);
            background: var(--surface-2);
            color: var(--fg);
            font-size: 15px;
            outline: none;
        }

        input:focus,
        select:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 4px var(--accent-ring);
            background: white;
        }

        input[type="range"] {
            accent-color: var(--accent);
        }

        button {
            border: 0;
            cursor: pointer;
            border-radius: 12px;
            font-weight: 900;
            font-size: 15px;
            padding: 12px 14px;
            transition: transform 120ms ease, box-shadow 120ms ease, background 120ms ease;
        }

        button:hover {
            transform: translateY(-1px);
        }

        .primary {
            background: var(--accent);
            color: white;
            box-shadow: 0 10px 22px rgba(124, 58, 237, 0.22);
        }

        .secondary {
            background: var(--surface-2);
            border: 1px solid var(--border);
            color: var(--fg);
        }

        .danger {
            background: #fee2e2;
            color: #991b1b;
            border: 1px solid #fecaca;
        }

        .full {
            width: 100%;
            margin-top: 18px;
        }

        .segmented {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            background: var(--surface-2);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 6px;
            margin-top: 14px;
        }

        .segmented form {
            margin: 0;
        }

        .segment-btn {
            width: 100%;
            background: transparent;
            color: var(--fg-muted);
        }

        .segment-btn.active {
            background: white;
            color: var(--accent-strong);
            box-shadow: 0 6px 18px rgba(20, 20, 35, 0.08);
            border: 1px solid var(--border);
        }

        .weather-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 14px;
            margin-top: 16px;
        }

        .weather-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 16px;
            min-height: 210px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }

        .weather-card.active {
            border-color: var(--accent);
            box-shadow: 0 0 0 4px var(--accent-ring);
        }

        .weather-title {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 12px;
        }

        .weather-icon {
            font-size: 26px;
            line-height: 1;
        }

        .desc {
            color: var(--fg-muted);
            font-size: 14px;
            margin: 10px 0 12px;
        }

        .swatches {
            display: flex;
            gap: 6px;
            margin-top: 8px;
        }

        .swatch {
            width: 24px;
            height: 24px;
            border-radius: 8px;
            border: 1px solid rgba(0,0,0,0.12);
        }

        .card-buttons {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-top: 12px;
        }

        .day-btn {
            background: #fff7d6;
            color: #7a4a00;
            border: 1px solid #f5d66b;
        }

        .night-btn {
            background: #111827;
            color: #dbeafe;
            border: 1px solid #334155;
        }

        .day-btn.active,
        .night-btn.active {
            outline: 4px solid var(--accent-ring);
            border-color: var(--accent);
        }

        .tiny {
            color: var(--fg-subtle);
            font-size: 13px;
            margin: 8px 0 0;
        }

        .note {
            color: var(--fg-muted);
            font-size: 14px;
            margin: 8px 0 0;
        }

        .warning {
            background: #fff7ed;
            border: 1px solid #fed7aa;
            color: #9a3412;
            border-radius: 14px;
            padding: 12px;
            margin-top: 12px;
            font-size: 14px;
        }

        details {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            padding: 18px 22px;
            margin-bottom: 18px;
        }

        summary {
            cursor: pointer;
            font-size: 20px;
            font-weight: 900;
            letter-spacing: -0.02em;
        }

        code {
            background: var(--surface-2);
            border: 1px solid var(--border);
            border-radius: 7px;
            padding: 2px 6px;
        }

        .save-row {
            display: flex;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap;
        }

        @media (max-width: 900px) {
            .weather-grid,
            .status-grid,
            .grid-2 {
                grid-template-columns: 1fr;
            }
        }

        @media (max-width: 620px) {
            .row,
            .card-buttons {
                grid-template-columns: 1fr;
            }

            body {
                padding: 18px 12px 48px;
            }

            .hero,
            .card,
            details {
                padding: 18px;
            }
        }
    </style>
</head>

<body>
<div class="page">

    <section class="hero">
        <div class="hero-top">
            <div>
                <h1>Weather LED Controller</h1>
                <p>Control live weather animations, preview day/night palettes, and manage quiet hours from one place.</p>
            </div>

            <div class="pill-row">
                <span class="pill"><span class="dot"></span> Config Online</span>
                <span class="pill">{{ "Test Mode" if config.test_mode_enabled else "Live Weather" }}</span>
                <span class="pill">{{ "Night Preview" if config.test_is_night else "Day Preview" }}</span>
            </div>
        </div>

        <div class="status-grid">
            <div class="stat">
                <div class="stat-label">Source</div>
                <div class="stat-value">{{ "Test Mode" if config.test_mode_enabled else "Live Weather" }}</div>
            </div>

            <div class="stat">
                <div class="stat-label">Current Preview</div>
                <div class="stat-value">
                    {% if config.test_mode_enabled %}
                        {{ config.test_condition }} · {{ "Night" if config.test_is_night else "Day" }}
                    {% else %}
                        Weather API
                    {% endif %}
                </div>
            </div>

            <div class="stat">
                <div class="stat-label">Brightness</div>
                <div class="stat-value">{{ config.led_brightness }}/255</div>
            </div>

            <div class="stat">
                <div class="stat-label">Quiet Hours</div>
                <div class="stat-value">
                    {% if config.quiet_hours_enabled %}
                        {{ config.quiet_start_hour }}:00–{{ config.quiet_end_hour }}:00
                    {% else %}
                        Off
                    {% endif %}
                </div>
            </div>
        </div>
    </section>

    {% if cron_sync_error %}
    <section class="warning">
        Settings were saved, but cron schedule sync failed. The LED process will still enforce quiet hours; check the web app logs for sudo or cron details.
    </section>
    {% endif %}

    <section class="card">
        <h2>Control Source</h2>
        <p class="note">
            Live Weather follows the forecast and quiet hours. Test Mode lets you preview animations outside quiet hours.
        </p>

        <div class="segmented">
            <form method="post">
                <input type="hidden" name="action" value="set_source">
                <input type="hidden" name="test_mode_enabled" value="false">
                <button class="segment-btn {% if not config.test_mode_enabled %}active{% endif %}" type="submit">
                    Live Weather
                </button>
            </form>

            <form method="post">
                <input type="hidden" name="action" value="set_source">
                <input type="hidden" name="test_mode_enabled" value="true">
                <button class="segment-btn {% if config.test_mode_enabled %}active{% endif %}" type="submit">
                    Test Mode
                </button>
            </form>
        </div>
    </section>

    <section class="card">
        <h2>Preview Weather Animations</h2>
        <p class="note">
            Pick a day or night version. The LED script should pick this up on the next animation loop.
        </p>

        <div class="weather-grid">
            {% for item in weather_cards %}
                {% set is_active = config.test_mode_enabled and config.test_condition == item.condition %}
                <div class="weather-card {% if is_active %}active{% endif %}">
                    <div>
                        <div class="weather-title">
                            <div>
                                <h3>{{ item.title }}</h3>
                                <p class="desc">{{ item.description }}</p>
                            </div>
                            <div class="weather-icon">{{ item.icon }}</div>
                        </div>

                        <div class="row">
                            <div>
                                <p class="tiny">Day palette</p>
                                <div class="swatches">
                                    {% for color in item.day_swatches %}
                                    <span class="swatch" style="background: {{ color }}"></span>
                                    {% endfor %}
                                </div>
                            </div>

                            <div>
                                <p class="tiny">Night palette</p>
                                <div class="swatches">
                                    {% for color in item.night_swatches %}
                                    <span class="swatch" style="background: {{ color }}"></span>
                                    {% endfor %}
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="card-buttons">
                        <form method="post">
                            <input type="hidden" name="action" value="quick_test">
                            <input type="hidden" name="test_condition" value="{{ item.condition }}">
                            <input type="hidden" name="test_is_night" value="false">
                            <button
                                class="day-btn {% if is_active and not config.test_is_night %}active{% endif %}"
                                type="submit"
                            >
                                Day
                            </button>
                        </form>

                        <form method="post">
                            <input type="hidden" name="action" value="quick_test">
                            <input type="hidden" name="test_condition" value="{{ item.condition }}">
                            <input type="hidden" name="test_is_night" value="true">
                            <button
                                class="night-btn {% if is_active and config.test_is_night %}active{% endif %}"
                                type="submit"
                            >
                                Night
                            </button>
                        </form>
                    </div>
                </div>
            {% endfor %}
        </div>

        <form method="post" style="margin-top: 18px;">
            <input type="hidden" name="action" value="disable_test_mode">
            <button class="danger full" type="submit">Return to Live Weather</button>
        </form>
    </section>

    <section class="card">
        <h2>Everyday Controls</h2>

        <form method="post">
            <input type="hidden" name="action" value="save_everyday">

            <label>Brightness</label>
            <input name="led_brightness" type="range" min="1" max="255" value="{{ config.led_brightness }}">
            <p class="note">Current brightness: <strong>{{ config.led_brightness }}</strong></p>

            <label>Quiet Hours</label>
            <select name="quiet_hours_enabled">
                <option value="true" {% if config.quiet_hours_enabled %}selected{% endif %}>Enabled</option>
                <option value="false" {% if not config.quiet_hours_enabled %}selected{% endif %}>Disabled</option>
            </select>

            <div class="row">
                <div>
                    <label>Quiet Start Hour</label>
                    <input name="quiet_start_hour" type="number" min="0" max="23" value="{{ config.quiet_start_hour }}">
                </div>

                <div>
                    <label>Quiet End Hour</label>
                    <input name="quiet_end_hour" type="number" min="0" max="23" value="{{ config.quiet_end_hour }}">
                </div>
            </div>

            <button class="primary full" type="submit">Save Everyday Controls</button>
        </form>
    </section>

    <section class="card">
        <h2>HDMI Display</h2>
        <p class="note">
            The kiosk screen shows live weather at <code>/display</code>. It uses the same Quiet Hours
            window above, but you can turn its screen-blanking on or off independently of the LEDs.
        </p>

        <form method="post">
            <input type="hidden" name="action" value="save_hdmi">

            <label>Blank Screen During Quiet Hours</label>
            <select name="kiosk_quiet_hours_enabled">
                <option value="true" {% if config.kiosk_quiet_hours_enabled %}selected{% endif %}>Enabled</option>
                <option value="false" {% if not config.kiosk_quiet_hours_enabled %}selected{% endif %}>Disabled</option>
            </select>

            <button class="primary full" type="submit">Save HDMI Display Settings</button>
        </form>

        <a href="/display" target="_blank"><button class="secondary full" type="button">Preview Display</button></a>
    </section>

    <details>
        <summary>Advanced Settings</summary>

        <form method="post" style="margin-top: 16px;">
            <input type="hidden" name="action" value="save_advanced">

            <div class="row">
                <div>
                    <label>LED Count</label>
                    <input name="led_count" type="number" value="{{ config.led_count }}">
                </div>

                <div>
                    <label>GPIO Pin / BCM Number</label>
                    <input name="led_pin" type="number" value="{{ config.led_pin }}">
                </div>
            </div>

            <div class="warning">
                Your data wire is physically on pin 12, but the software value should be <strong>GPIO18</strong>, so this field should usually be <code>18</code>.
            </div>

            <div class="row">
                <div>
                    <label>Latitude</label>
                    <input name="latitude" type="text" value="{{ config.latitude }}">
                </div>

                <div>
                    <label>Longitude</label>
                    <input name="longitude" type="text" value="{{ config.longitude }}">
                </div>
            </div>

            <div class="row">
                <div>
                    <label>Weather Check Interval</label>
                    <input name="weather_refresh_seconds" type="number" value="{{ config.weather_refresh_seconds }}">
                    <p class="tiny">Seconds. 900 = 15 minutes.</p>
                </div>

                <div>
                    <label>Animation Speed</label>
                    <input name="animation_frame_delay" type="text" value="{{ config.animation_frame_delay }}">
                    <p class="tiny">Lower is faster. Example: 0.05.</p>
                </div>
            </div>

            <label>Quiet Check Seconds</label>
            <input name="quiet_check_seconds" type="number" value="{{ config.quiet_check_seconds }}">

            <button class="primary full" type="submit">Save Advanced Settings</button>
        </form>
    </details>

    <section class="card">
        <h2>Testing Notes</h2>
        <p class="note">
            Test Mode is saved to <code>/home/matt/weather_led_config.json</code>. The LED script must be running and must include test-mode support.
            If nothing changes, check the LED script logs and confirm it prints <code>TEST MODE active</code>.
        </p>
    </section>

</div>
</body>
</html>
"""


def sync_cron_schedule():
    try:
        result = subprocess.run(
            ["sudo", "/home/matt/update_weather_led_cron.sh"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            print(
                f"Cron sync failed with exit code {result.returncode}. "
                f"stdout={result.stdout!r} stderr={result.stderr!r}",
                flush=True
            )
            return False
        print("Cron sync success:", result.stdout, flush=True)
        return True
    except Exception as e:
        print(f"Cron sync exception: {e}", flush=True)
        return False


def as_bool(value):
    return value == "true"


_weather_cache = {"data": None, "fetched_at": 0}


def get_current_weather():
    """Fetches and classifies the next-hour weather, cached for weather_refresh_seconds."""
    config = load_config()
    refresh_seconds = int(config.get("weather_refresh_seconds", 900))
    now = time.time()

    if _weather_cache["data"] is not None and now - _weather_cache["fetched_at"] < refresh_seconds:
        return _weather_cache["data"]

    try:
        weather = fetch_next_hour_weather()
        condition = classify_weather(
            weather["weather_code"],
            weather["precipitation_probability"],
            weather["precipitation"]
        )
        card = WEATHER_CARDS_BY_CONDITION.get(condition, WEATHER_CARDS_BY_CONDITION["cloudy"])

        data = {
            "condition": condition,
            "title": card["title"],
            "icon": card["icon"],
            "day_swatches": card["day_swatches"],
            "night_swatches": card["night_swatches"],
            "temperature": weather["temperature"],
            "precipitation_probability": weather["precipitation_probability"],
            "sunrise": weather["sunrise"],
            "sunset": weather["sunset"],
            "is_night": weather["is_night"],
            "error": None
        }
        _weather_cache["data"] = data
        _weather_cache["fetched_at"] = now
        return data

    except Exception as e:
        if _weather_cache["data"] is not None:
            stale = dict(_weather_cache["data"])
            stale["error"] = str(e)
            return stale

        card = WEATHER_CARDS_BY_CONDITION["cloudy"]
        return {
            "condition": "unknown",
            "title": card["title"],
            "icon": card["icon"],
            "day_swatches": card["day_swatches"],
            "night_swatches": card["night_swatches"],
            "temperature": 0,
            "precipitation_probability": 0,
            "sunrise": None,
            "sunset": None,
            "is_night": False,
            "error": str(e)
        }


@app.route("/", methods=["GET", "POST"])
def index():
    config = load_config()
    cron_sync_error = request.args.get("cron_sync") == "failed"

    if request.method == "POST":
        action = request.form.get("action", "")

        if action == "set_source":
            config["test_mode_enabled"] = as_bool(request.form["test_mode_enabled"])

        elif action == "quick_test":
            condition = request.form["test_condition"]

            config["test_mode_enabled"] = True
            config["test_condition"] = condition
            config["test_is_night"] = as_bool(request.form["test_is_night"])

            # Make precipitation-based previews obvious.
            if condition in ["rain", "storm"]:
                config["test_precipitation_probability"] = 80
            elif condition == "drizzle":
                config["test_precipitation_probability"] = 35
            else:
                config["test_precipitation_probability"] = 0

        elif action == "disable_test_mode":
            config["test_mode_enabled"] = False

        elif action == "save_everyday":
            config["led_brightness"] = int(request.form["led_brightness"])
            config["quiet_hours_enabled"] = as_bool(request.form["quiet_hours_enabled"])
            config["quiet_start_hour"] = int(request.form["quiet_start_hour"])
            config["quiet_end_hour"] = int(request.form["quiet_end_hour"])
            save_config(config)
            if not sync_cron_schedule():
                return redirect("/?cron_sync=failed")
            return redirect("/")

        elif action == "save_hdmi":
            config["kiosk_quiet_hours_enabled"] = as_bool(request.form["kiosk_quiet_hours_enabled"])

        elif action == "save_advanced":
            config["led_count"] = int(request.form["led_count"])
            config["led_pin"] = int(request.form["led_pin"])
            config["latitude"] = float(request.form["latitude"])
            config["longitude"] = float(request.form["longitude"])
            config["weather_refresh_seconds"] = int(request.form["weather_refresh_seconds"])
            config["animation_frame_delay"] = float(request.form["animation_frame_delay"])
            config["quiet_check_seconds"] = int(request.form["quiet_check_seconds"])

        save_config(config)
        return redirect("/")

    return render_template_string(
        HTML,
        config=config,
        cron_sync_error=cron_sync_error,
        weather_cards=WEATHER_CARDS
    )


@app.route("/display")
def display():
    return render_template_string(DISPLAY_HTML)


@app.route("/api/weather")
def api_weather():
    return jsonify(get_current_weather())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
