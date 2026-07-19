"""和风天气异步 API 客户端。"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlencode

from aiohttp import ClientError, ClientSession

from .heweather.const import DOMAIN
from .heweather.heweather_cert import HeWeatherCert

_LOGGER = logging.getLogger(__name__)


class QWeatherApiError(Exception):
    """API 调用失败。"""


class QWeatherApiClient:
    """共享 HTTP 客户端：API Key 或 JWT。"""

    def __init__(
        self,
        session: ClientSession,
        host: str,
        *,
        key: str | None = None,
        heweather_cert: HeWeatherCert | None = None,
        jwt_sub: str | None = None,
        jwt_kid: str | None = None,
    ) -> None:
        self._session = session
        self._host = host.rstrip("/")
        self._key = key
        self._cert = heweather_cert
        self._jwt_sub = jwt_sub
        self._jwt_kid = jwt_kid
        self._is_jwt = not bool(key)

    def _base(self, path: str) -> str:
        if not path.startswith("/"):
            path = f"/{path}"
        return f"https://{self._host}{path}"

    @staticmethod
    def round_coord(value: str | float, digits: int = 2) -> str:
        return f"{float(value):.{digits}f}"

    async def _auth_headers(self) -> dict[str, str]:
        if not self._is_jwt:
            return {}
        if not self._cert or not self._jwt_sub or not self._jwt_kid:
            raise QWeatherApiError("JWT credentials incomplete")
        now = int(time.time())
        token = await self._cert.get_jwt_token_heweather_async(
            self._jwt_sub, self._jwt_kid, now - 30, now + 180
        )
        return {"Authorization": f"Bearer {token}"}

    def _with_key(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = dict(params or {})
        if not self._is_jwt and self._key:
            query["key"] = self._key
        return query

    async def _get_json(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        url = self._base(path)
        query = self._with_key(params)
        headers = await self._auth_headers()
        try:
            async with self._session.get(url, params=query, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise QWeatherApiError(
                        f"HTTP {resp.status} for {path}: {text[:200]}"
                    )
                data = await resp.json(content_type=None)
        except ClientError as err:
            raise QWeatherApiError(f"Request failed {path}: {err}") from err

        if not isinstance(data, dict):
            raise QWeatherApiError(f"Invalid JSON for {path}")

        # v7 系列用 code；新 air/alert 无 code 字段
        code = data.get("code")
        if code is not None and str(code) != "200":
            raise QWeatherApiError(f"API code {code} for {path}")
        return data

    async def weather_now(self, longitude: str, latitude: str) -> dict[str, Any]:
        location = f"{longitude},{latitude}"
        return await self._get_json("/v7/weather/now", {"location": location})

    async def weather_7d(self, longitude: str, latitude: str) -> dict[str, Any]:
        location = f"{longitude},{latitude}"
        return await self._get_json("/v7/weather/7d", {"location": location})

    async def weather_24h(self, longitude: str, latitude: str) -> dict[str, Any]:
        location = f"{longitude},{latitude}"
        return await self._get_json("/v7/weather/24h", {"location": location})

    async def air_current(self, longitude: str, latitude: str) -> dict[str, Any]:
        # 路径参数：纬度在前
        path = f"/airquality/v1/current/{latitude}/{longitude}"
        return await self._get_json(path)

    async def air_daily(self, longitude: str, latitude: str) -> dict[str, Any]:
        path = f"/airquality/v1/daily/{latitude}/{longitude}"
        return await self._get_json(path)

    async def weather_alert(self, longitude: str, latitude: str) -> dict[str, Any]:
        path = f"/weatheralert/v1/current/{latitude}/{longitude}"
        return await self._get_json(path)

    async def indices_1d(
        self, longitude: str, latitude: str, index_type: str = "0"
    ) -> dict[str, Any]:
        location = f"{longitude},{latitude}"
        return await self._get_json(
            "/v7/indices/1d",
            {"location": location, "type": index_type},
        )

    async def minutely_5m(self, longitude: str, latitude: str) -> dict[str, Any]:
        # 分钟降水要求坐标最多两位小数
        lon = self.round_coord(longitude, 2)
        lat = self.round_coord(latitude, 2)
        location = f"{lon},{lat}"
        return await self._get_json("/v7/minutely/5m", {"location": location})

    async def astronomy_sun(
        self, longitude: str, latitude: str, date: str
    ) -> dict[str, Any]:
        location = f"{longitude},{latitude}"
        return await self._get_json(
            "/v7/astronomy/sun",
            {"location": location, "date": date},
        )

    async def astronomy_moon(
        self, longitude: str, latitude: str, date: str
    ) -> dict[str, Any]:
        location = f"{longitude},{latitude}"
        return await self._get_json(
            "/v7/astronomy/moon",
            {"location": location, "date": date},
        )


def build_location_key(longitude: str, latitude: str) -> str:
    """设备 identifier 与 unique_id 后缀。"""
    return f"{longitude},{latitude}"


def unique_id_for(object_id: str, longitude: str, latitude: str) -> str:
    return f"{object_id}_{longitude}_{latitude}"


def strip_location_suffix(unique_id: str, longitude: str, latitude: str) -> str | None:
    """从 unique_id 去掉 _{lon}_{lat} 得到 object_id 前缀。"""
    suffix = f"_{longitude}_{latitude}"
    if unique_id.endswith(suffix):
        return unique_id[: -len(suffix)]
    return None
