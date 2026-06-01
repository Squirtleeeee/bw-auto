"""
会员购 API — show.bilibili.com
"""

from __future__ import annotations

from typing import Any

import httpx

SHOW_BASE = "https://show.bilibili.com"


async def get_project_detail(
    client: httpx.AsyncClient,
    project_id: str,
    source: str = "pc",
) -> dict[str, Any]:
    """获取商品详情

    GET /api/ticket/project/get?id={project_id}&source={source}

    返回的 data 包含:
      - id, name: 商品 ID / 名称
      - sale_flag: 1=预售, 2=在售, 3=已售罄
      - sale_time: 开售时间
      - screen_list: [{id, name, sale_start, sale_end}]
      - sku_list: [{id, name, price, sale_count, limit_per_user}]
    """
    resp = await client.get(
        f"{SHOW_BASE}/api/ticket/project/get",
        params={"id": project_id, "source": source},
        headers={"Referer": f"https://show.bilibili.com/platform/detail.html?id={project_id}"},
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("errno") != 0:
        raise RuntimeError(f"获取商品详情失败: {data.get('msg', data)}")
    return data["data"]


async def get_buyer_list(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """获取已保存的购买人列表

    GET /api/ticket/buyer/list

    返回: [{id, name, tel, id_card_no, id_card_type, is_default, ...}]
    """
    resp = await client.get(
        f"{SHOW_BASE}/api/ticket/buyer/list",
        headers={"Referer": "https://show.bilibili.com/"},
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("errno") != 0:
        raise RuntimeError(f"获取购买人列表失败: {data.get('msg', data)}")
    return data.get("data", {}).get("list", data.get("data", []))


async def create_order_v2(
    client: httpx.AsyncClient,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """创建订单 (下单) — 使用 createV2 端点

    POST /api/ticket/order/createV2?project_id={project_id}

    从 confirmOrder JS 逆向出的完整 payload:
      project_id, screen_id, sku_id, count, pay_money,
      order_type, timestamp, promo_id, promo_group_id,
      buyer_info, deliver_info, seats, coupon_code,
      voucher, token, use_year_card, deviceId, clickPosition,
      newRisk: true, requestSource: "pc-new"

    buyer_info 格式 (从 saved buyer profile):
      {name, tel, id_card_type: 0, id_card_no}

    返回: {errno: 0, data: {order_id: "..."}}
    """
    import time

    project_id = payload.get("project_id", "")
    csrf = client.cookies.get("bili_jct", "")

    body = {
        "project_id": project_id,
        "screen_id": payload.get("screen_id", ""),
        "sku_id": payload.get("sku_id", ""),
        "count": payload.get("count", 1),
        "pay_money": payload.get("pay_money", 0),
        "order_type": payload.get("order_type", 1),
        "timestamp": payload.get("timestamp", int(time.time())),
        "promo_id": payload.get("promo_id", ""),
        "promo_group_id": payload.get("promo_group_id", ""),
        "buyer_info": payload.get("buyer_info", {}),
        "deliver_info": payload.get("deliver_info", {"deliver_type": 0}),
        "seats": payload.get("seats", []),
        "coupon_code": payload.get("coupon_code", ""),
        "voucher": payload.get("voucher", ""),
        "token": payload.get("token", ""),
        "use_year_card": payload.get("use_year_card", ""),
        "deviceId": payload.get("deviceId", ""),
        "clickPosition": payload.get("clickPosition", ""),
        "newRisk": True,
        "requestSource": "pc-new",
    }

    # csrf token 放在 body 里
    if csrf:
        body["csrf_token"] = csrf
    if payload.get("csrf_token"):
        body["csrf_token"] = payload["csrf_token"]

    # captureVerifyCode 相关
    if payload.get("capture_code"):
        body["captureVerifyCode"] = payload["capture_code"]

    resp = await client.post(
        f"{SHOW_BASE}/api/ticket/order/createV2?project_id={project_id}",
        json=body,
        headers={
            "Referer": f"https://show.bilibili.com/platform/detail.html?id={project_id}",
            "Origin": "https://show.bilibili.com",
        },
    )
    resp.raise_for_status()
    return resp.json()
