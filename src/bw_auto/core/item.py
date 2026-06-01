"""商品信息获取：从会员购 API 拉取并解析为数据模型。"""

from __future__ import annotations

from datetime import datetime

import httpx

from bw_auto.api.show_api import get_project_detail
from bw_auto.core.models import Item, Screen, Sku


def _parse_datetime(ts: int | float | str | None) -> datetime | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(float(ts))


async def fetch_item(client: httpx.AsyncClient, project_id: str) -> Item:
    """获取商品详情

    兼容两种数据格式:
      - 新版: screen.ticket_list 里含票档
      - 旧版: 顶层 sku_list 含票档
    """
    raw = await get_project_detail(client, project_id)

    screens = []
    all_skus = []

    for s in raw.get("screen_list") or []:
        screen_id = str(s.get("id", ""))
        screen = Screen(
            screen_id=screen_id,
            name=s.get("name", ""),
            sale_start=_parse_datetime(s.get("sale_start")),
            sale_end=_parse_datetime(s.get("sale_end")),
        )
        screens.append(screen)

        # 从 screen 的 ticket_list 提取票档 (新版)
        for tk in s.get("ticket_list") or []:
            price_raw = int(tk.get("price", 0))
            all_skus.append(Sku(
                sku_id=str(tk.get("id", "")),
                name=tk.get("desc") or tk.get("name") or f"票档{screen_id}",
                price=price_raw / 100.0,
                stock=int(tk.get("sale_count", 0) or 0),
                limit_per_user=int(tk.get("limit_per_user", 1) or 1),
            ))

    # 如果没有 ticket_list，从顶层 sku_list 提取 (旧版)
    if not all_skus:
        for sk in raw.get("sku_list") or []:
            price_raw = int(sk.get("price", 0))
            all_skus.append(Sku(
                sku_id=str(sk.get("id", "")),
                name=sk.get("name", ""),
                price=price_raw / 100.0,
                stock=int(sk.get("sale_count", 0) or 0),
                limit_per_user=int(sk.get("limit_per_user", 1) or 1),
            ))

    return Item(
        project_id=str(raw.get("id", project_id)),
        name=raw.get("name", "未知商品"),
        screens=screens,
        skus=all_skus,
        raw=raw,
    )


def print_item(item: Item) -> None:
    """终端友好输出商品信息"""
    print(f"\n  商品: {item.name} (ID: {item.project_id})")
    print(f"  {'─' * 40}")
    if item.screens:
        print(f"  场次:")
        # 从 raw 数据中获取每个场次的票档
        raw = item.raw
        for sc in raw.get("screen_list") or []:
            start_ts = sc.get("sale_start") or sc.get("start_time")
            start = datetime.fromtimestamp(float(start_ts)).strftime("%Y-%m-%d %H:%M:%S") if start_ts else "未知"
            print(f"    [{sc['id']}] {sc['name']}  开售: {start}")
            tickets = sc.get("ticket_list") or []
            for tk in tickets:
                price_yuan = int(tk.get("price", 0)) / 100
                name = tk.get("desc") or tk.get("name") or "默认"
                stock = tk.get("sale_count", "?")
                print(f"         {name}  ￥{price_yuan:.0f}  库存:{stock}")
    if item.skus and not any(s.get("ticket_list") for s in (item.raw.get("screen_list") or [])):
        # 旧版: 顶层 sku_list
        print(f"  票档:")
        for sk in item.skus:
            print(f"    [{sk.sku_id}] {sk.name}  ￥{sk.price:.0f}  库存:{sk.stock}  限购:{sk.limit_per_user}")
