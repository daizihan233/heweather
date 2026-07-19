"""和风天气集成常量。"""

from homeassistant.const import Platform

DOMAIN: str = "heweather"
DEFAULT_NAME: str = "和风天气"

# config platform
CONF_AUTH_METHOD = "auth_method"
CONF_OPTIONS = "options"
CONF_LONGITUDE = "longitude"
CONF_LATITUDE = "latitude"
CONF_HOST = "host"
CONF_KEY = "key"
CONF_STORAGE_PATH = "storage_path"
CONF_JWT_SUB = "auth_jwt_sub"
CONF_JWT_KID = "auth_jwt_kid"

DEFAULT_HOST = "devapi.qweather.com"

CONF_DISASTERLEVEL = "disasterlevel"
CONF_DISASTERMSG = "disastermsg"

# 历史拼写 temprature 仅作 unique_id 迁移别名
LEGACY_OPTION_ALIASES = {
    "temprature": "temperature",
}

# 平台
PLATFORMS = [
    Platform.WEATHER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]

# 更新间隔（秒）
WEATHER_UPDATE_INTERVAL = 600
INDICES_UPDATE_INTERVAL = 7200
MINUTELY_UPDATE_INTERVAL = 600

# 配置流
DEFAULT_AUTH_METHOD: str = "key"
AUTH_METHOD: dict = {
    "key": "API KEY",
    "jwt": "JSON Web Token (Alpha)",
}

DEFAULT_DISASTER_MSG: str = "allmsg"
DISASTER_MSG: dict = {
    "title": "仅标题",
    "allmsg": "所有信息",
}

# 阈值 1–6：与 DISASTER_LEVEL 映射比较。文案对齐官方 severity：
# https://dev.qweather.com/docs/resource/warning-info/#severity
DEFAULT_DISASTER_LEVEL_CONF: str = "3"
DISASTER_LEVEL_CONF: dict = {
    "1": "兼容档(standard/blue)",
    "2": "minor：威胁极小或无已知威胁",
    "3": "moderate：可能构成威胁",
    "4": "兼容档(major/orange)",
    "5": "severe：重大威胁",
    "6": "extreme：严重威胁",
}

CONDITION_CLASSES = {
    "sunny": ["晴"],
    "cloudy": ["多云"],
    "partlycloudy": ["少云", "晴间多云", "阴"],
    "windy": ["有风", "微风", "和风", "清风"],
    "windy-variant": ["强风", "劲风", "疾风", "大风", "烈风"],
    "hurricane": ["飓风", "龙卷风", "热带风暴", "狂暴风", "风暴"],
    "rainy": [
        "雨",
        "毛毛雨",
        "细雨",
        "小雨",
        "小到中雨",
        "中雨",
        "中到大雨",
        "大雨",
        "大到暴雨",
        "阵雨",
        "极端降雨",
        "冻雨",
    ],
    "pouring": [
        "暴雨",
        "暴雨到大暴雨",
        "大暴雨",
        "大暴雨到特大暴雨",
        "特大暴雨",
        "强阵雨",
    ],
    "lightning-rainy": ["雷阵雨", "强雷阵雨"],
    "fog": [
        "雾",
        "薄雾",
        "霾",
        "浓雾",
        "强浓雾",
        "中度霾",
        "重度霾",
        "严重霾",
        "大雾",
        "特强浓雾",
    ],
    "hail": ["雷阵雨伴有冰雹"],
    "snowy": [
        "小雪",
        "小到中雪",
        "中雪",
        "中到大雪",
        "大雪",
        "大到暴雪",
        "暴雪",
        "阵雪",
    ],
    "snowy-rainy": ["雨夹雪", "雨雪天气", "阵雨夹雪"],
    "exceptional": ["扬沙", "浮尘", "沙尘暴", "强沙尘暴", "未知"],
}

# 与 README 模板一致：这些 condition 视为「无雨雪」
DRY_CONDITIONS = frozenset({"sunny", "cloudy", "partlycloudy", "windy"})

# severity → 内部阈值。官方 severity 见 warning-info#severity：
# unknown / minor / moderate / severe / extreme
# standard、major 与颜色别名仅作兼容，便于历史数据与 color 字段回落
DISASTER_LEVEL = {
    "cancel": 0,
    "none": 0,
    "unknown": 0,
    "standard": 1,  # 非官方 severity 枚举，兼容保留
    "minor": 2,
    "moderate": 3,
    "major": 4,  # 非官方 severity 枚举，兼容保留
    "severe": 5,
    "extreme": 6,
    "white": 0,
    "blue": 1,
    "green": 2,
    "yellow": 3,
    "orange": 4,
    "red": 5,
    "black": 6,
}

# 生活指数 type → 内部 key
INDEX_TYPE_MAP = {
    "1": "sport",
    "2": "cw",
    "3": "drsg",
    "4": "fishing",
    "5": "uv",
    "6": "trav",
    "7": "guomin",
    "8": "comf",
    "9": "flu",
    "10": "air",
    "11": "kongtiao",
    "12": "sunglass",
    "13": "makeup",
    "14": "liangshai",
    "15": "jiaotong",
    "16": "fangshai",
}

ATTR_UPDATE_TIME = "更新时间"
ATTR_SUGGESTION = "建议"
ATTR_STATES = "states"
ATTRIBUTION = "来自和风天气的天气数据"

CERT_NAME_PREFIX = "heweather_ed25519_"

# runtime data keys
RUNTIME_API = "api"
RUNTIME_WEATHER_COORD = "weather_coordinator"
RUNTIME_INDICES_COORD = "indices_coordinator"
RUNTIME_MINUTELY_COORD = "minutely_coordinator"
