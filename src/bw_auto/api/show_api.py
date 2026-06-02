"""会员购 API — show.bilibili.com"""

from __future__ import annotations

import time
from typing import Any

import httpx

SHOW_BASE = "https://show.bilibili.com"


def _detail_headers(project_id: str) -> dict[str, str]:
    return {"Referer": f"https://show.bilibili.com/platform/detail.html?id={project_id}"}


async def get_project_detail(
    client: httpx.AsyncClient,
    project_id: str,
    source: str = "pc",
) -> dict[str, Any]:
    resp = await client.get(
        f"{SHOW_BASE}/api/ticket/project/get",
        params={"id": project_id, "source": source},
        headers=_detail_headers(project_id),
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("errno") != 0:
        raise RuntimeError(f"获取商品详情失败: {data.get('msg', data)}")
    return data["data"]


async def get_buyer_list(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    resp = await client.get(
        f"{SHOW_BASE}/api/ticket/buyer/list",
        params={"nomask": "1"},
        headers={"Referer": "https://show.bilibili.com/"},
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("errno") != 0:
        raise RuntimeError(f"获取购买人列表失败: {data.get('msg', data)}")
    payload = data.get("data")
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get("list") or []
    return []


async def prepare_order(
    client: httpx.AsyncClient,
    project_id: str,
    screen_id: str,
    sku_id: str,
    count: int = 1,
) -> dict[str, Any]:
    """预下单 — 获取 createV2 所需的 token"""
    body = {
        "project_id": int(project_id),
        "screen_id": int(screen_id),
        "sku_id": int(sku_id),
        "count": count,
        "order_type": 1,
        "token": "",
        "newRisk": True,
    }
    resp = await client.post(
        f"{SHOW_BASE}/api/ticket/order/prepare",
        params={"project_id": project_id},
        json=body,
        headers=_detail_headers(project_id),
    )
    resp.raise_for_status()
    data = resp.json()
    if "errno" not in data and "code" in data:
        data["errno"] = data["code"]
        data["msg"] = data.get("message", "")
    return data


async def get_confirm_info(
    client: httpx.AsyncClient,
    token: str,
    project_id: str,
    voucher: str = "",
) -> dict[str, Any]:
    """获取订单确认信息（含完整手机号）。

    GET /api/ticket/order/confirmInfo

    返回 data 包含:
      - contact_info: {username, tel}  — 完整手机号
      - buyerList: {list: [...]}
      - pay_money, screen_id, sku_id 等
    """
    resp = await client.get(
        f"{SHOW_BASE}/api/ticket/order/confirmInfo",
        params={
            "token": token,
            "voucher": voucher,
            "project_id": project_id,
            "requestSource": "pc-new",
        },
        headers=_detail_headers(project_id),
    )
    resp.raise_for_status()
    data = resp.json()
    if "errno" not in data and "code" in data:
        data["errno"] = data["code"]
        data["msg"] = data.get("message", "")
    return data


async def create_order_v2(
    client: httpx.AsyncClient,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """创建订单 — 格式经浏览器验证"""
    import json as _json

    pid = int(payload.get("project_id", 0))
    device_id = payload.get("deviceId", "") or client.cookies.get("deviceFingerprint", "")
    buyer_name = payload.get("buyer", "")
    buyer_tel = payload.get("tel", "")

    # buyer_info: JSON-encoded string (key difference from earlier attempts)
    buyer_info = payload.get("buyer_info") or []
    if isinstance(buyer_info, list):
        buyer_info = _json.dumps(buyer_info, ensure_ascii=False)
    deliver_info = payload.get("deliver_info")
    if isinstance(deliver_info, dict):
        deliver_info = _json.dumps(deliver_info, ensure_ascii=False)
    elif not deliver_info:
        deliver_info = _json.dumps({"name": buyer_name, "tel": buyer_tel, "addr_id": 0, "addr": ""}, ensure_ascii=False)

    body = {
        "project_id": pid,
        "screen_id": int(payload.get("screen_id", 0)),
        "sku_id": int(payload.get("sku_id", 0)),
        "count": payload.get("count", 1),
        "pay_money": payload.get("pay_money", 0),
        "order_type": payload.get("order_type", 1),
        "timestamp": payload.get("timestamp", int(time.time() * 1000)),
        "deviceId": device_id,
        "buyer": buyer_name,
        "tel": buyer_tel,
        "buyer_info": buyer_info,
        "deliver_info": deliver_info,
        "token": payload.get("token", ""),
        "again": payload.get("again", 0),
        "coupon_code": payload.get("coupon_code", ""),
        "newRisk": True,
        "requestSource": "pc-new",
    }

    resp = await client.post(
        f"{SHOW_BASE}/api/ticket/order/createV2?project_id={pid}",
        json=body,
        headers={
            "Referer": _detail_headers(str(pid))["Referer"],
            "Origin": "https://show.bilibili.com",
        },
    )
    resp.raise_for_status()
    data = resp.json()
    if "errno" not in data and "code" in data:
        data["errno"] = data["code"]
        data["msg"] = data.get("message", "")
    return data
