"""商品信息获取与校验"""

from __future__ import annotations

from datetime import datetime

import httpx

from bw_auto.api.show_api import get_project_detail
from bw_auto.core.models import Item, Screen, Sku

SALE_FLAG_LABELS = {1: "预售", 2: "在售", 3: "已售罄"}
SALE_FLAG_TEXT_TO_CODE = {"预售": 1, "在售": 2, "已售罄": 3, "售罄": 3}


def _is_presale(item: Item) -> bool:
    if item.sale_flag == 1:
        return True
    raw = str(item.raw.get("sale_flag", "") or "")
    return "预售" in raw


def _safe_int(value: object, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def _parse_sale_flag(value: object) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    if text in SALE_FLAG_TEXT_TO_CODE:
        return SALE_FLAG_TEXT_TO_CODE[text]
    if "售罄" in text:
        return 3
    if "在售" in text:
        return 2
    if "预售" in text:
        return 1
    return 0


def _parse_datetime(ts: int | float | str | None) -> datetime | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(float(ts))


async def fetch_item(client: httpx.AsyncClient, project_id: str) -> Item:
    raw = await get_project_detail(client, project_id)
    screens: list[Screen] = []
    all_skus: list[Sku] = []

    for s in raw.get("screen_list") or []:
        screen_id = str(s.get("id", ""))
        screens.append(
            Screen(
                screen_id=screen_id,
                name=s.get("name", ""),
                sale_start=_parse_datetime(s.get("sale_start")),
                sale_end=_parse_datetime(s.get("sale_end")),
            )
        )
        for tk in s.get("ticket_list") or []:
            all_skus.append(
                Sku(
                    sku_id=str(tk.get("id", "")),
                    screen_id=screen_id,
                    name=tk.get("desc") or tk.get("name") or "票档",
                    price_fen=_safe_int(tk.get("price", 0)),
                    stock=_safe_int(tk.get("sale_count", 0)),
                    limit_per_user=max(1, _safe_int(tk.get("limit_per_user", 1), 1)),
                )
            )

    if not all_skus:
        default_screen = screens[0].screen_id if screens else ""
        for sk in raw.get("sku_list") or []:
            all_skus.append(
                Sku(
                    sku_id=str(sk.get("id", "")),
                    screen_id=default_screen,
                    name=sk.get("name", "票档"),
                    price_fen=_safe_int(sk.get("price", 0)),
                    stock=_safe_int(sk.get("sale_count", 0)),
                    limit_per_user=max(1, _safe_int(sk.get("limit_per_user", 1), 1)),
                )
            )

    return Item(
        project_id=str(raw.get("id", project_id)),
        name=raw.get("name", "未知商品"),
        sale_flag=_parse_sale_flag(raw.get("sale_flag")),
        screens=screens,
        skus=all_skus,
        raw=raw,
    )


def validate_item_for_grab(item: Item, screen_id: str, sku_id: str, buy_num: int) -> str | None:
    """返回错误信息；None 表示可继续。"""
    raw_flag = item.raw.get("sale_flag")
    if item.sale_flag == 3 or str(raw_flag) in ("已售罄", "售罄"):
        return "商品已售罄，无法抢票"
    sku = item.get_sku(sku_id)
    if not sku:
        return "票档不存在"
    if sku.screen_id and sku.screen_id != screen_id:
        return "票档与所选场次不匹配"
    if sku.stock <= 0 and not _is_presale(item):
        return "该票档库存为 0（非预售商品）"
    if buy_num > sku.limit_per_user:
        return f"超过限购数量（每人最多 {sku.limit_per_user} 张）"
    if buy_num < 1:
        return "购买数量至少为 1"
    return None


def sale_flag_label(item: Item) -> str:
    if item.sale_flag in SALE_FLAG_LABELS:
        return SALE_FLAG_LABELS[item.sale_flag]
    raw = item.raw.get("sale_flag")
    return str(raw) if raw else "未知"


def print_item(item: Item) -> None:
    from bw_auto.services.selection import _is_ticket_available
    flag = sale_flag_label(item)
    print(f"\n  商品: {item.name} (ID: {item.project_id})  状态: {flag}")
    print(f"  {'─' * 40}")
    for sc in item.raw.get("screen_list") or []:
        start_ts = sc.get("sale_start")
        start = (
            datetime.fromtimestamp(float(start_ts)).strftime("%Y-%m-%d %H:%M:%S")
            if start_ts
            else "未知"
        )
        print(f"    场次 [{sc['id']}] {sc['name']}  开售: {start}")
        tickets = sc.get("ticket_list") or item.skus_for_screen(str(sc["id"]))
        for tk in tickets:
            if isinstance(tk, Sku):
                print(f"         {tk.name}  ￥{tk.price_fen / 100:.0f}")
            else:
                price_yuan = int(tk.get("price", 0)) / 100
                name = tk.get("desc") or tk.get("name", "默认")
                status = "可购" if _is_ticket_available(tk) else "未开放"
                print(f"         {name}  ￥{price_yuan:.0f}  [{status}]")
