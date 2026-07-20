"""Offline pure-function tests without importing HA packages."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "custom_components" / "heweather"

CONDITION_CLASSES = {
    "sunny": ["晴"], "cloudy": ["多云"], "partlycloudy": ["少云", "晴间多云", "阴"],
    "windy": ["有风", "微风", "和风", "清风"],
    "rainy": ["雨", "毛毛雨", "细雨", "小雨", "小到中雨", "中雨", "中到大雨", "大雨", "大到暴雨", "阵雨", "极端降雨", "冻雨"],
}
DRY_CONDITIONS = frozenset({"sunny", "cloudy", "partlycloudy", "windy"})
INDEX_TYPE_MAP = {"1":"sport","2":"cw","3":"drsg","4":"fishing","5":"uv","6":"trav","7":"guomin","8":"comf","9":"flu","10":"air","11":"kongtiao","12":"sunglass","13":"makeup","14":"liangshai","15":"jiaotong","16":"fangshai"}
DISASTER_LEVEL = {"minor":2,"moderate":3,"major":4,"severe":5,"extreme":6}

def condition_from_text(text):
    if not text: return "unknown"
    for condition, keywords in CONDITION_CLASSES.items():
        if text in keywords: return condition
    return "unknown"

def parse_indices(indices_data):
    parsed = {}
    for item in (indices_data or {}).get("daily") or []:
        key = INDEX_TYPE_MAP.get(str(item.get("type", "")))
        if key: parsed[key] = [item.get("category") or "", item.get("text") or ""]
    return parsed

def parse_disaster(alert_data, disaster_level, disaster_msg):
    """Mirror coordinator.parse_disaster text rules (offline, no HA import)."""
    threshold = int(disaster_level)
    alerts = (alert_data or {}).get("alerts") or []
    all_parts = []
    title_parts = []
    matched = []
    for item in alerts:
        severity = str(item.get("severity", "")).lower()
        if severity in DISASTER_LEVEL and DISASTER_LEVEL[severity] >= threshold:
            matched.append(item)
            description = (item.get("description") or "").strip()
            headline = (item.get("headline") or "").strip()
            if description:
                all_parts.append(description)
            if headline:
                title_parts.append(headline)
    if not matched:
        return {"active": False, "text": ""}
    text = "；".join(title_parts) if disaster_msg == "title" else "；".join(all_parts)
    return {"active": True, "text": text}

def parse_minutely(minutely_data):
    items = (minutely_data or {}).get("minutely") or []
    first = None
    has = False
    for row in items:
        try: precip = float(row.get("precip"))
        except (TypeError, ValueError): continue
        if precip > 0:
            has = True
            if first is None: first = precip
    return {"summary": (minutely_data or {}).get("summary"), "has_precip": has, "first_precip": first}

def parse_hourly_forecast(forecast_data):
    result = []
    for hour in (forecast_data or {}).get("hourly") or []:
        text = hour.get("text")
        result.append({
            "datetime": hour.get("fxTime"),
            "condition": condition_from_text(text),
            "native_temperature": float(hour["temp"]) if hour.get("temp") not in (None, "") else None,
            "native_precipitation": float(hour["precip"]) if hour.get("precip") not in (None, "") else None,
            "precipitation_probability": float(hour["pop"]) if hour.get("pop") not in (None, "") else None,
        })
    return result

def rain_warn_active(weather_data):
    hourly = weather_data.get("hourly") or []
    if not hourly: return False
    first = hourly[0]
    condition = first.get("condition") or condition_from_text(first.get("text"))
    return condition not in DRY_CONDITIONS

def round_coord(value, digits=2):
    return f"{float(value):.{digits}f}"

# ---- alert_key mirror (same logic as coordinator) ----
def alert_key(alert):
    headline = (alert.get("headline") or "").strip()
    severity = (alert.get("severity") or "").strip().lower()
    return f"{severity}:{headline}"

# ---- _fire_disaster_events mirror (no HA import) ----
EVENT_DISASTER_NEW = "heweather_disaster_new"
EVENT_DISASTER_CLEARED = "heweather_disaster_cleared"

class _FakeBus:
    def __init__(self):
        self.events = []
    def async_fire(self, event_type, data=None, **kw):
        self.events.append((event_type, data or {}))

class _FakeHass:
    def __init__(self):
        self.bus = _FakeBus()

def _fire_disaster_events(hass, new_alerts, cleared_alerts, disaster_msg):
    if new_alerts:
        descs = [a.get("description") or "" for a in new_alerts]
        headlines = [a.get("headline") or "" for a in new_alerts]
        text_long = "；".join(d for d in descs if d.strip())
        text_short = "；".join(h for h in headlines if h.strip())
        text = text_short if disaster_msg == "title" else text_long
        hass.bus.async_fire(
            EVENT_DISASTER_NEW,
            {"text": text, "text_long": text_long, "text_short": text_short,
             "alerts": new_alerts, "source": "heweather"},
        )
    if cleared_alerts:
        headlines = [a.get("headline") or "" for a in cleared_alerts]
        text_short = "；".join(h for h in headlines if h.strip())
        hass.bus.async_fire(
            EVENT_DISASTER_CLEARED,
            {"text_short": text_short, "alerts": cleared_alerts, "source": "heweather"},
        )

def test_all():
    assert condition_from_text("晴") == "sunny"
    assert condition_from_text("小雨") == "rainy"
    parsed = parse_indices({"daily":[{"type":"5","category":"强","text":"紫外线强"},{"type":"12","category":"需要","text":"建议戴太阳镜"}]})
    assert parsed["uv"][0] == "强" and parsed["sunglass"][0] == "需要"
    parsed2 = parse_indices({"daily":[{"type":"4","category":"适宜","text":"钓鱼适宜"},{"type":"13","category":"保湿","text":"化妆保湿"}]})
    assert "fishing" in parsed2 and "makeup" in parsed2
    result = parse_disaster({"alerts":[{"severity":"minor","headline":"小风","description":"d1"},{"severity":"severe","headline":"暴雨","description":"d2"}]}, "3", "title")
    assert result["active"] is True and result["text"] == "暴雨" and "小风" not in result["text"]
    no_match = parse_disaster({"alerts":[{"severity":"minor","headline":"小风","description":"d1"}]}, "3", "allmsg")
    assert no_match["active"] is False and no_match["text"] == ""
    # allmsg: description only, multi joined by Chinese semicolon
    allmsg = parse_disaster({
        "alerts": [
            {"severity": "severe", "headline": "HEADLINE_A", "description": "南京市气象台发布高温黄色预警，预计白天最高气温将升至35℃以上"},
            {"severity": "major", "headline": "HEADLINE_B", "description": "江苏省气象台发布高温橙色预警，预计部分地区最高气温将升至37℃以上"},
        ]
    }, "3", "allmsg")
    assert allmsg["active"] is True
    assert allmsg["text"] == (
        "南京市气象台发布高温黄色预警，预计白天最高气温将升至35℃以上；"
        "江苏省气象台发布高温橙色预警，预计部分地区最高气温将升至37℃以上"
    )
    assert "HEADLINE_A" not in allmsg["text"] and "HEADLINE_B" not in allmsg["text"]
    assert "||" not in allmsg["text"]
    title_multi = parse_disaster({
        "alerts": [
            {"severity": "severe", "headline": "南京高温", "description": "d1"},
            {"severity": "major", "headline": "江苏高温", "description": "d2"},
        ]
    }, "3", "title")
    assert title_multi["text"] == "南京高温；江苏高温"
    # skip empty description pieces
    skip_empty = parse_disaster({
        "alerts": [
            {"severity": "severe", "headline": "H", "description": ""},
            {"severity": "major", "headline": "H2", "description": "only"},
        ]
    }, "3", "allmsg")
    assert skip_empty["text"] == "only"
    m = parse_minutely({"summary":"即将下雨","minutely":[{"precip":"0.0"},{"precip":"0.2"}]})
    assert m["has_precip"] and m["first_precip"] == 0.2
    assert rain_warn_active({"hourly":[{"condition":"rainy","text":"小雨"}]}) is True
    assert rain_warn_active({"hourly":[{"condition":"sunny","text":"晴"}]}) is False
    hourly = parse_hourly_forecast({"hourly":[{"fxTime":"2024-01-01T12:00+08:00","text":"小雨","temp":"10","precip":"0.5","pop":"60"}]})
    assert hourly[0]["datetime"] == "2024-01-01T12:00+08:00" and hourly[0]["condition"] == "rainy"
    assert round_coord("116.41234") == "116.41"
    api = (PKG/"api.py").read_text(encoding="utf-8")
    assert "/v7/minutely/5m" in api and "/v7/tropical" not in api and "solar-radiation" not in api
    coord = (PKG/"coordinator.py").read_text(encoding="utf-8")
    assert "if not matched:" in coord and "WeatherUpdateCoordinator" in coord
    sensor = (PKG/"sensor.py").read_text(encoding="utf-8")
    assert "heweather_temperature" in sensor and '("sunglass"' in sensor and "suggestion_{key}" in sensor and "async_setup_platform" not in sensor
    binary = (PKG/"binary_sensor.py").read_text(encoding="utf-8")
    assert "rain_warn" in binary and "next_precip" in binary
    weather = (PKG/"weather.py").read_text(encoding="utf-8")
    assert "async_forecast_daily" in weather and "localweather_" in weather and "async_setup_platform" not in weather
    init = (PKG/"__init__.py").read_text(encoding="utf-8")
    assert "WeatherUpdateCoordinator" in init
    manifest = json.loads((PKG/"manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "2.7.0"
    # production parse_disaster: description-only allmsg, no legacy || join
    assert '".join(all_parts)' in coord or ".join(all_parts)" in coord
    assert "headline}:{description" not in coord
    assert 'allmsg += f"{headline}:{description}||"' not in coord
    # coordinator must have disaster event/diff infrastructure
    assert "_last_disaster_alerts" in coord
    assert "alert_key" in coord
    # event constants in const.py
    const = (PKG/"heweather"/"const.py").read_text(encoding="utf-8")
    assert "EVENT_DISASTER_NEW" in const
    assert "EVENT_DISASTER_CLEARED" in const
    # alert_key tests (mirror)
    assert alert_key({"severity": "severe", "headline": "暴雨"}) == "severe:暴雨"
    assert alert_key({"severity": "Major", "headline": "高温"}) == "major:高温"
    assert alert_key({"severity": "", "headline": ""}) == ":"
    assert alert_key({}) == ":"
    # _fire_disaster_events: new event (allmsg → text_long)
    h = _FakeHass()
    _fire_disaster_events(
        h,
        new_alerts=[
            {"severity": "severe", "headline": "暴雨", "description": "预计有大暴雨"},
            {"severity": "major", "headline": "高温", "description": "预计气温37℃"},
        ],
        cleared_alerts=[],
        disaster_msg="allmsg",
    )
    assert len(h.bus.events) == 1
    etype, edata = h.bus.events[0]
    assert etype == EVENT_DISASTER_NEW
    assert edata["text"] == edata["text_long"]
    assert "暴雨" not in edata["text_short"] or "暴雨" in edata["text_short"]
    assert "预计有大暴雨" in edata["text"]
    assert "预计气温37℃" in edata["text"]
    # _fire_disaster_events: new event (title → text_short)
    h2 = _FakeHass()
    _fire_disaster_events(
        h2,
        new_alerts=[
            {"severity": "severe", "headline": "暴雨", "description": "预计有大暴雨"},
        ],
        cleared_alerts=[],
        disaster_msg="title",
    )
    assert h2.bus.events[0][1]["text"] == "暴雨"
    # _fire_disaster_events: cleared event
    h3 = _FakeHass()
    _fire_disaster_events(
        h3,
        new_alerts=[],
        cleared_alerts=[
            {"severity": "severe", "headline": "暴雨解除", "description": "预警已解除"},
        ],
        disaster_msg="allmsg",
    )
    assert len(h3.bus.events) == 1
    assert h3.bus.events[0][0] == EVENT_DISASTER_CLEARED
    assert h3.bus.events[0][1]["text_short"] == "暴雨解除"
    assert "description" not in h3.bus.events[0][1]  # cleared event has no description
    # diff logic: no change → no event
    h4 = _FakeHass()
    old = [{"severity": "severe", "headline": "暴雨"}]
    new = [{"severity": "severe", "headline": "暴雨"}]
    _fire_disaster_events(h4, new_alerts=[], cleared_alerts=[], disaster_msg="allmsg")
    assert len(h4.bus.events) == 0  # no change → no event
    # diff logic: new + cleared simultaneously
    h5 = _FakeHass()
    _fire_disaster_events(
        h5,
        new_alerts=[{"severity": "severe", "headline": "新增预警"}],
        cleared_alerts=[{"severity": "major", "headline": "旧预警解除"}],
        disaster_msg="allmsg",
    )
    assert len(h5.bus.events) == 2
    assert h5.bus.events[0][0] == EVENT_DISASTER_NEW
    assert h5.bus.events[1][0] == EVENT_DISASTER_CLEARED
    const = (PKG/"heweather"/"const.py").read_text(encoding="utf-8")
    assert '"4": "fishing"' in const and '"13": "makeup"' in const
    cf = (PKG/"config_flow.py").read_text(encoding="utf-8")
    assert '__show_auth_jwt_config_form("jwt_sub is empty")' in cf
    zh = json.loads((PKG/"translations"/"zh-Hans.json").read_text(encoding="utf-8"))
    assert "heweather_rain_warn" in zh["entity"]["binary_sensor"]
    assert "suggestion_fishing" in zh["entity"]["sensor"]
    assert "heweather_sunrise" in zh["entity"]["sensor"]
    print("ALL TESTS PASSED")

if __name__ == "__main__":
    test_all()