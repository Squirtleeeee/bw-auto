"""场次 / 票档 / 购买人解析 — CLI 与 Web 共用"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bw_auto.core.item import sale_flag_label
from bw_auto.core.models import BuyerInfo, Item


def parse_sale_time(
    item: Item,
    screen_id: str,
    screen_raw: dict[str, Any],
    sale_time_str: str = "",
) -> datetime | None:
    if sale_time_str:
        return datetime.strptime(sale_time_str, "%Y-%m-%d %H:%M:%S")
    sale_start = screen_raw.get("sale_start")
    if sale_start:
        return datetime.fromtimestamp(float(sale_start))
    screen = next((s for s in item.screens if s.screen_id == screen_id), None)
    if screen and screen.sale_start:
        return screen.sale_start
    raw_sale = item.raw.get("sale_time") or item.raw.get("start_time")
    if raw_sale:
        return datetime.fromtimestamp(float(raw_sale))
    return None


def buyer_from_api_row(row: dict[str, Any]) -> BuyerInfo:
    return BuyerInfo(
        name=row.get("name", ""),
        tel=row.get("tel", row.get("phone", "")),
        id_card_type=int(row.get("id_card_type", 0) or 0),
        id_card_no=row.get("id_card_no", ""),
        buyer_id=str(row.get("id", "")),
    )


def _is_ticket_available(tk: dict[str, Any]) -> bool:
    """检查票档当前是否可购买"""
    now = datetime.now()
    sale_start = tk.get("sale_start")
    sale_end = tk.get("sale_end")
    if not sale_start and not sale_end:
        return True  # 无时间限制
    if sale_start:
        try:
            if isinstance(sale_start, str):
                sale_start = datetime.strptime(sale_start, "%Y-%m-%d %H:%M:%S")
            elif isinstance(sale_start, (int, float)):
                sale_start = datetime.fromtimestamp(float(sale_start))
            if now < sale_start:
                return False
        except (ValueError, TypeError, OSError):
            pass
    if sale_end:
        try:
            if isinstance(sale_end, str):
                sale_end = datetime.strptime(sale_end, "%Y-%m-%d %H:%M:%S")
            elif isinstance(sale_end, (int, float)):
                sale_end = datetime.fromtimestamp(float(sale_end))
            if now > sale_end:
                return False
        except (ValueError, TypeError, OSError):
            pass
    return True


def item_to_api_dict(item: Item) -> dict[str, Any]:
    screens_out = []
    for sc in item.raw.get("screen_list") or []:
        sid = str(sc.get("id", ""))
        tickets = []
        for tk in sc.get("ticket_list") or []:
            available = _is_ticket_available(tk)
            tickets.append(
                {
                    "id": str(tk.get("id", "")),
                    "name": tk.get("desc") or tk.get("name", ""),
                    "price_yuan": int(tk.get("price", 0) or 0) / 100,
                    "price_fen": int(tk.get("price", 0) or 0),
                    "available": available,
                    "sale_start": tk.get("sale_start"),
                    "sale_end": tk.get("sale_end"),
                }
            )
        if not tickets:
            for sk in item.skus_for_screen(sid):
                tickets.append(
                    {
                        "id": sk.sku_id,
                        "name": sk.name,
                        "price_yuan": sk.price_fen / 100,
                        "price_fen": sk.price_fen,
                        "available": True,
                        "sale_start": None,
                        "sale_end": None,
                    }
                )
        start = sc.get("sale_start")
        screens_out.append(
            {
                "id": sid,
                "name": sc.get("name", ""),
                "sale_start": (
                    datetime.fromtimestamp(float(start)).isoformat() if start else None
                ),
                "tickets": tickets,
            }
        )
    if not screens_out and item.skus:
        screens_out.append(
            {
                "id": "",
                "name": "默认场次",
                "sale_start": None,
                "tickets": [
                    {
                        "id": s.sku_id,
                        "name": s.name,
                        "price_yuan": s.price_fen / 100,
                        "price_fen": s.price_fen,
                        "stock": s.stock,
                        "limit": s.limit_per_user,
                    }
                    for s in item.skus
                ],
            }
        )
    return {
        "project_id": item.project_id,
        "name": item.name,
        "sale_flag": item.sale_flag,
        "sale_flag_label": sale_flag_label(item),
        "screens": screens_out,
    }


def buyers_to_api_list(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for b in rows:
        id_no = b.get("id_card_no", "")
        masked = id_no[:3] + "****" + id_no[-4:] if len(id_no) > 6 else id_no
        out.append(
            {
                "id": str(b.get("id", "")),
                "name": b.get("name", ""),
                "tel": b.get("tel", b.get("phone", "")),
                "id_card_masked": masked,
                "is_default": bool(b.get("is_default")),
            }
        )
    return out
