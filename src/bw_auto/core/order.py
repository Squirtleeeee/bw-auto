"""订单构造、预下单、下单与错误解析"""

from __future__ import annotations

import json as _json
import time
from typing import Any

import httpx

from bw_auto.api.show_api import create_order_v2, prepare_order
from bw_auto.core.models import BuyerInfo, OrderPayload, OrderResult

RETRYABLE_KEYWORDS = (
    "繁忙", "拥挤", "稍后", "timeout", "超时", "频繁",
    "系统", "网络", "库存", "售罄", "service", "83000",
    "慢一点", "请慢",
)


def build_payload(
    project_id: str,
    screen_id: str,
    sku_id: str,
    buy_num: int = 1,
    pay_money_fen: int = 0,
    buyer: BuyerInfo | None = None,
    token: str = "",
) -> OrderPayload:
    if buyer is None:
        buyer = BuyerInfo()
    return OrderPayload(
        project_id=project_id,
        screen_id=screen_id,
        sku_id=sku_id,
        buy_num=buy_num,
        pay_money=pay_money_fen,
        buyer_info=buyer,
        token=token,
    )


def payload_to_dict(p: OrderPayload, device_id: str = "") -> dict[str, Any]:
    """转为 createV2 的请求体 — buyer_info/deliver_info 为 JSON 字符串"""
    buyer_list = [{
        "name": p.buyer_info.name,
        "personal_id": p.buyer_info.id_card_no,
        "tel": p.buyer_info.tel,
        "id_type": p.buyer_info.id_card_type,
        "id": int(p.buyer_info.buyer_id) if p.buyer_info.buyer_id else 0,
    }]
    return {
        "project_id": int(p.project_id),
        "screen_id": int(p.screen_id),
        "sku_id": int(p.sku_id),
        "count": p.buy_num,
        "pay_money": int(p.pay_money),
        "order_type": 1,
        "timestamp": int(time.time() * 1000),
        "deviceId": device_id,
        "buyer": p.buyer_info.name,
        "tel": p.buyer_info.tel,
        "buyer_info": buyer_list,
        "deliver_info": {"name": p.buyer_info.name, "tel": p.buyer_info.tel, "addr_id": 0, "addr": ""},
        "token": p.token,
    }


def humanize_order_error(errno: int, msg: str) -> str:
    text = (msg or "").lower()
    if "实名" in msg or "购买人" in msg:
        return "需要实名购买人：请先在 Bilibili App/网页添加"
    if "售罄" in msg or "库存" in msg:
        return "票已售罄或库存不足"
    if "限购" in msg:
        return "超过限购数量"
    if "未完成" in msg:
        return "存在未完成订单，请在 App 中取消后重试"
    if errno in (-100, 100001) or "繁忙" in msg or "拥挤" in msg:
        return "系统繁忙，将自动重试"
    return f"[errno={errno}] {msg}" if msg else f"下单失败 errno={errno}"


def is_retryable(result: OrderResult) -> bool:
    if result.success:
        return False
    msg = result.message.lower()
    return any(k in msg for k in RETRYABLE_KEYWORDS)


async def fetch_order_token(
    client: httpx.AsyncClient,
    project_id: str,
    screen_id: str,
    sku_id: str,
    count: int,
) -> str:
    """调用 prepare 获取下单 token"""
    try:
        data = await prepare_order(client, project_id, screen_id, sku_id, count)
        if data.get("errno") == 0:
            inner = data.get("data") or {}
            return str(inner.get("token") or "")
    except Exception:
        pass
    return ""


async def submit_order(
    client: httpx.AsyncClient,
    payload: OrderPayload | dict,
    *,
    attempt: int = 1,
) -> OrderResult:
    """发送 createV2 下单请求"""
    device_id = client.cookies.get("deviceFingerprint", "")
    body = payload_to_dict(payload, device_id) if isinstance(payload, OrderPayload) else payload

    try:
        data = await create_order_v2(client, body)
    except httpx.HTTPStatusError as e:
        return OrderResult(success=False, message=f"HTTP {e.response.status_code}", attempt=attempt)
    except Exception as e:
        return OrderResult(success=False, message=str(e), attempt=attempt)

    errno = data.get("errno", -1)
    msg = data.get("msg", "")
    if errno == 0:
        order_id = data.get("data", {}).get("orderId") or data.get("data", {}).get("order_id", "")
        return OrderResult(success=True, order_id=str(order_id), message=msg or "下单成功", attempt=attempt)

    raw_info = _json.dumps(data, ensure_ascii=False)[:300]
    return OrderResult(
        success=False,
        message=humanize_order_error(errno, msg) if msg else f"[errno={errno}]",
        raw=data,
        attempt=attempt,
    )
