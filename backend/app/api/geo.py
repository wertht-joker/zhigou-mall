"""定位辅助接口：经纬度 → 省市区 + 街道地址

前端不再直连第三方地图服务（Nominatim 在部分网络不可达，且浏览器跨域受限），
统一由后端代理并归一化：
- Photon（OSM，无需 Key）：街道/门牌/地点名
- BigDataCloud（无需 Key）：省市区名称与行政区划编码

返回标准 6 位省/市/区行政区划编码，前端按级联组件的数据层级转换后回填。
两家服务互为兜底。
"""
import asyncio
import logging

import httpx
from fastapi import APIRouter, Query

from app.core.errors import ServiceUnavailableError
from app.core.response import success

router = APIRouter(tags=["定位"])
logger = logging.getLogger(__name__)

PHOTON_URL = "https://photon.komoot.io/reverse"
BDC_URL = "https://api-bdc.net/data/reverse-geocode-client"
USER_AGENT = "zhigou-mall-demo/1.0"
TIMEOUT_SECONDS = 6.0


async def _fetch(client: httpx.AsyncClient, url: str, params: dict) -> dict:
    resp = await client.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def _admin_codes(bdc: dict) -> list[str]:
    """从 BigDataCloud 的 chinaAdminCode 推导 6 位省/市/区编码

    BigDataCloud 的编码形如 "33"（省）、"33 01"（市）、"33 01 05"（区），
    与 element-china-area-data 的 330000 / 330100 / 330105 一一对应。
    直辖市没有市级编码，但区级编码可反推市辖区编码（如 110101 → 110100）。
    """
    admin = ((bdc.get("localityInfo") or {}).get("administrative") or [])
    raw = {
        str(item.get("chinaAdminCode") or "").replace(" ", "")
        for item in admin
    }
    raw = {code for code in raw if code.isdigit()}
    district = next((c for c in raw if len(c) == 6), None)
    if district:
        return [district[:2] + "0000", district[:4] + "00", district]
    city = next((c for c in raw if len(c) == 4), None)
    if city:
        return [city[:2] + "0000", city + "00"]
    province = next((c for c in raw if len(c) == 2), None)
    if province:
        return [province + "0000"]
    return []


def _bdc_region_parts(bdc: dict) -> list[str]:
    parts = [
        (bdc.get("principalSubdivision") or "").strip(),
        (bdc.get("city") or "").strip(),
        (bdc.get("locality") or "").strip(),
    ]
    # 去重并保持顺序（直辖市的省、市可能同名）
    result: list[str] = []
    for part in parts:
        if part and part not in result:
            result.append(part)
    return result


def _photon_props(photon: dict) -> dict:
    features = photon.get("features") or []
    if not features:
        return {}
    return features[0].get("properties") or {}


def _photon_region_parts(props: dict) -> list[str]:
    parts = [
        (props.get("state") or "").strip(),
        (props.get("city") or props.get("county") or "").strip(),
        (props.get("district") or props.get("city_district") or "").strip(),
    ]
    result: list[str] = []
    for part in parts:
        if part and part not in result:
            result.append(part)
    return result


def _photon_detail(props: dict) -> str:
    """拼街道门牌与地点名；没有街道时退回片区/街道办名称"""
    street = (props.get("street") or "").strip()
    house = (props.get("housenumber") or "").strip()
    name = (props.get("name") or "").strip()
    parts = [street]
    if house:
        parts.append(house if house.endswith("号") else house + "号")
    if name and name not in street:
        parts.append(name)
    detail = "".join(p for p in parts if p)
    if not detail:
        detail = (
            (props.get("district") or props.get("city_district")
             or props.get("locality") or "").strip()
        )
    return detail


@router.get("/geo/reverse")
async def reverse_geocode(
    lat: float = Query(..., ge=-90, le=90, description="纬度"),
    lon: float = Query(..., ge=-180, le=180, description="经度"),
):
    """经纬度逆地理编码（公开接口，供地址簿「定位」按钮使用）"""
    # 强制 IPv4：部分网络 IPv6 出口不可达，会导致第三方逆地理编码连接超时
    transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
    async with httpx.AsyncClient(
        timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT},
        transport=transport, follow_redirects=True,
    ) as client:
        photon_result, bdc_result = await asyncio.gather(
            _fetch(client, PHOTON_URL, {"lat": lat, "lon": lon}),
            _fetch(
                client, BDC_URL,
                {"latitude": lat, "longitude": lon, "localityLanguage": "zh"},
            ),
            return_exceptions=True,
        )

    photon = photon_result if isinstance(photon_result, dict) else {}
    bdc = bdc_result if isinstance(bdc_result, dict) else {}
    if not photon and not bdc:
        logger.warning("逆地理编码失败 lat=%s lon=%s", lat, lon)
        raise ServiceUnavailableError("定位服务暂不可用，请手动选择所在地区")

    props = _photon_props(photon)
    region_parts = _bdc_region_parts(bdc) or _photon_region_parts(props)
    return success({
        "region_parts": region_parts,
        "region_codes": _admin_codes(bdc),
        "detail": _photon_detail(props),
        "latitude": lat,
        "longitude": lon,
        "providers": {
            "photon": bool(photon),
            "bigdatacloud": bool(bdc),
        },
    })
