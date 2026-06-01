"""
订单创建：构造请求体、发送下单请求、处理响应。

基于 show.bilibili.com confirmOrder JS 逆向的 createV2 端点。
"""

from __future__ import annotations

import time

import httpx

from bw_auto.api.show_api import create_order_v2
from bw_auto.core.models import BuyerInfo, OrderPayload, OrderResult


def build_payload(
    project_id: str,
    screen_id: str,
    sku_id: str,
    buy_num: int = 1,
    pay_money: float = 0.0,
    buyer: BuyerInfo | None = None,
    order_type: int = 1,
) -> OrderPayload:
    """构造下单请求体"""
    if buyer is None:
        buyer = BuyerInfo()
    return OrderPayload(
        project_id=project_id,
        screen_id=screen_id,
        sku_id=sku_id,
        buy_num=buy_num,
        pay_money=pay_money,
        buyer_info=buyer,
    )


def payload_to_dict(p: OrderPayload) -> dict:
    """把 OrderPayload 转为 createV2 的 POST body"""
    return {
        "project_id": p.project_id,
        "screen_id": p.screen_id,
        "sku_id": p.sku_id,
        "count": p.buy_num,
        "pay_money": p.pay_money,
        "order_type": 1,
        "timestamp": int(time.time()),
        "promo_id": "",
        "promo_group_id": "",
        "buyer_info": {
            "name": p.buyer_info.name,
            "tel": p.buyer_info.tel,
            "id_card_type": p.buyer_info.id_card_type,
            "id_card_no": p.buyer_info.id_card_no,
        },
        "deliver_info": p.deliver_info,
        "seats": [],
        "coupon_code": "",
        "voucher": "",
        "token": p.token,
        "use_year_card": "",
        "deviceId": "",
        "clickPosition": "",
    }


async def submit_order(
    client: httpx.AsyncClient,
    payload: OrderPayload | dict,
) -> OrderResult:
    """发送 createV2 下单请求并解析结果"""
    body = payload_to_dict(payload) if isinstance(payload, OrderPayload) else payload

    try:
        data = await create_order_v2(client, body)
    except httpx.HTTPStatusError as e:
        return OrderResult(
            success=False,
            message=f"HTTP {e.response.status_code}",
            raw={"status_code": e.response.status_code},
        )
    except Exception as e:
        return OrderResult(success=False, message=str(e))

    errno = data.get("errno", -1)
    msg = data.get("msg", "")

    if errno == 0:
        order_id = data.get("data", {}).get("order_id", "")
        return OrderResult(success=True, order_id=str(order_id), message=msg, raw=data)

    return OrderResult(success=False, message=f"[errno={errno}] {msg}", raw=data)


# ---------------------------------------------------------------------------
# 常见错误码
# ---------------------------------------------------------------------------

ERRNO_SOLD_OUT = -1
ERRNO_LIMITED = -2
ERRNO_NEED_REALNAME = -3
ERRNO_CROWDED = -100
