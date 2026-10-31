"""天气工具:调用 Open-Meteo 实时天气接口(免 key,无需注册)

输出 JSON 键与行程规划节点约定一致: 日期/天气/温度/风力/出行建议
"""
import json

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.config import settings
from app.utils.dates import fmt_date, normalize_date

_API = "https://api.open-meteo.com/v1/forecast"

# WMO 天气代码 -> 中文描述
_WMO = {
    0: "晴", 1: "晴间多云", 2: "多云", 3: "阴",
    45: "雾", 48: "雾凇",
    51: "小毛毛雨", 53: "毛毛雨", 55: "大毛毛雨",
    56: "冻毛毛雨", 57: "强冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨",
    66: "冻雨", 67: "强冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "阵雨", 81: "中阵雨", 82: "强阵雨",
    85: "小阵雪", 86: "大阵雪",
    95: "雷阵雨", 96: "雷阵雨伴冰雹", 99: "强雷阵雨伴冰雹",
}

# 蒲福风级上限(米/秒),用于把风速换算成风力等级
_BEAUFORT = [0.3, 1.6, 3.4, 5.5, 8.0, 10.8, 13.9, 17.2, 20.8, 24.5, 28.5, 32.7]

# 需要提示改为室内安排的天气代码:毛毛雨至强阵雨、雷雨
_RAIN_CODES = set(range(51, 68)) | set(range(80, 83)) | {95, 96, 99}


class WeatherArgs(BaseModel):
    query_date: str = Field(description="查询日期,如 今天/明天 或 YYYY-MM-DD")


def _wind_level(speed_ms: float) -> int:
    """把风速(米/秒)换算为蒲福风级"""
    for level, limit in enumerate(_BEAUFORT):
        if speed_ms < limit:
            return level
    return 12


def _advice(code: int, temp_max: float, precip_prob: float) -> str:
    """根据天气代码与降水概率生成出行建议"""
    if code >= 95:
        return "索道可能临时停运,优先室内场馆"
    if code in _RAIN_CODES or precip_prob >= 60:
        return "有降雨,建议以室内项目为主,栈道湿滑注意安全"
    if temp_max >= 30:
        return "气温较高,注意防晒补水"
    return "适合全项目"


async def _get_weather(query_date: str) -> str:
    """查询度假区某日天气(温度、风力、出行建议),用于行程规划"""
    d = normalize_date(query_date)
    cfg = settings.weather
    params = {
        "latitude": cfg.latitude,
        "longitude": cfg.longitude,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,wind_speed_10m_max,precipitation_probability_max",
        "timezone": cfg.timezone,
        "start_date": d.isoformat(),
        "end_date": d.isoformat(),
        "wind_speed_unit": "ms",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(_API, params=params)
        resp.raise_for_status()
        daily = resp.json()["daily"]

    code = int(daily["weather_code"][0])
    temp_min = float(daily["temperature_2m_min"][0])
    temp_max = float(daily["temperature_2m_max"][0])
    wind = _wind_level(float(daily["wind_speed_10m_max"][0]))
    precip = float(daily["precipitation_probability_max"][0])
    weather = _WMO.get(code, f"未知天气({code})")

    return json.dumps({
        "日期": fmt_date(d),
        "天气": weather,
        "温度": f"{temp_min:.0f}~{temp_max:.0f}℃",
        "风力": f"{wind} 级",
        "出行建议": _advice(code, temp_max, precip),
    }, ensure_ascii=False)


def build_weather_tools() -> list[StructuredTool]:
    return [
        StructuredTool.from_function(coroutine=_get_weather, args_schema=WeatherArgs,
                                      name="get_weather",
                                      description="查询度假区某天的天气与出行建议。做行程规划时必须首先调用以决定室内外安排")
    ]
