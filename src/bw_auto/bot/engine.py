"""
抢票引擎 — 状态机编排整个流程。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum, auto

import httpx

from bw_auto.core.item import fetch_item, print_item
from bw_auto.core.models import BuyerInfo, Item, OrderPayload
from bw_auto.core.order import build_payload, payload_to_dict, submit_order
from bw_auto.core.scheduler import PreciseTimer
from bw_auto.utils.time_sync import sync_time


class State(Enum):
    IDLE = auto()
    LOGGED_IN = auto()
    ITEM_LOADED = auto()
    WAITING = auto()
    ORDERING = auto()
    SUCCESS = auto()
    FAILED = auto()
    CANCELLED = auto()


class GrabEngine:
    """抢票引擎"""

    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.state = State.IDLE
        self.item: Item | None = None
        self._cancelled = False

    async def load_item(self, project_id: str) -> Item:
        self.item = await fetch_item(self.client, project_id)
        self.state = State.ITEM_LOADED
        print_item(self.item)
        return self.item

    async def grab(
        self,
        item: Item,
        screen_id: str = "",
        sku_id: str = "",
        buy_num: int = 1,
        buyer: BuyerInfo | None = None,
        sale_time: datetime | None = None,
        pre_fire_ms: float = 150.0,
    ):
        """执行抢票"""
        screen_id = screen_id or item.first_screen_id
        sku_id = sku_id or item.first_sku_id

        if sale_time is None:
            screen = next((s for s in item.screens if s.screen_id == screen_id), None)
            if screen and screen.sale_start:
                sale_time = screen.sale_start
            else:
                raise ValueError("无法确定开售时间，请手动指定 sale_time 参数")

        # 从 models 中查找 SKU 价格 (元) → 转为分
        sku = next((s for s in item.skus if s.sku_id == sku_id), None)
        pay_money = (sku.price * 100) if sku else 0.0

        payload = build_payload(
            project_id=item.project_id,
            screen_id=screen_id,
            sku_id=sku_id,
            buy_num=buy_num,
            pay_money=pay_money,
            buyer=buyer,
        )
        body = payload_to_dict(payload)

        # 时间同步
        offset = await sync_time(self.client)
        print(f"  [时间同步] 服务器偏移: {offset:+.1f}ms")

        timer = PreciseTimer(time_offset_ms=offset, pre_fire_ms=pre_fire_ms)

        now = datetime.now()
        wait_secs = (sale_time - now).total_seconds()
        print(f"  [开售时间] {sale_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  [等待时长] {wait_secs:.1f} 秒")

        if wait_secs < 0:
            print(f"  [警告] 开售时间已过，直接尝试下单...")
        elif wait_secs > 5:
            print(f"  进入等待...")

        self.state = State.WAITING

        if self._cancelled:
            self.state = State.CANCELLED
            return None

        if wait_secs >= 0:
            await timer.wait_until(sale_time)
        self.state = State.ORDERING

        print(f"\n  [下单] 发送请求...")
        t0 = datetime.now()
        result = await submit_order(self.client, body)
        elapsed = (datetime.now() - t0).total_seconds() * 1000

        if result.success:
            self.state = State.SUCCESS
            print(f"  [成功] order_id={result.order_id} (耗时 {elapsed:.0f}ms)")
        else:
            self.state = State.FAILED
            print(f"  [失败] {result.message} (耗时 {elapsed:.0f}ms)")

        return result

    def cancel(self):
        self._cancelled = True
        self.state = State.CANCELLED
