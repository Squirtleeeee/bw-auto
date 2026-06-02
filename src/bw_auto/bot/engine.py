"""抢票引擎 — 定时、预热、到点下单、间隔重试"""

from __future__ import annotations

import asyncio
from datetime import datetime
from enum import Enum, auto
from typing import Awaitable, Callable

import httpx

from bw_auto.core.item import fetch_item, validate_item_for_grab
from bw_auto.core.models import GrabPlan, OrderPayload, OrderResult
from bw_auto.core.order import (
    build_payload,
    fetch_order_token,
    is_retryable,
    payload_to_dict,
    submit_order,
)
from bw_auto.core.scheduler import PreciseTimer
from bw_auto.http_client import prewarm_client
from bw_auto.utils.time_sync import sync_time

LogFn = Callable[[str], None]


class State(Enum):
    IDLE = auto()
    SCHEDULED = auto()
    PREPARING = auto()
    WAITING = auto()
    ORDERING = auto()
    SUCCESS = auto()
    FAILED = auto()
    CANCELLED = auto()


class GrabEngine:
    def __init__(
        self,
        client: httpx.AsyncClient,
        log: LogFn | None = None,
    ):
        self.client = client
        self.state = State.IDLE
        self._cancelled = False
        self._log = log or (lambda msg: print(msg, flush=True))
        self._timer: PreciseTimer | None = None
        self.last_result: OrderResult | None = None

    def cancel(self) -> None:
        self._cancelled = True
        if self._timer:
            self._timer.cancel()
        self.state = State.CANCELLED

    async def _wait_until(self, target: datetime, label: str) -> bool:
        if self._cancelled:
            return False
        now = datetime.now()
        secs = (target - now).total_seconds()
        if secs <= 0:
            return True
        self._log(f"  [{label}] 等待至 {target.strftime('%Y-%m-%d %H:%M:%S')}（约 {secs:.0f}s）")
        timer = PreciseTimer()
        self._timer = timer

        def tick(remaining: float) -> None:
            if remaining > 60:
                return
            self._log(f"  [{label}] 剩余 {remaining:.0f}s")

        await timer.wait_until(target, on_tick=tick)
        return not self._cancelled

    async def run(self, plan: GrabPlan) -> OrderResult | None:
        if self._cancelled:
            self.state = State.CANCELLED
            return None

        item = await fetch_item(self.client, plan.project_id)
        err = validate_item_for_grab(item, plan.screen_id, plan.sku_id, plan.buy_num)
        if err:
            self.state = State.FAILED
            self.last_result = OrderResult(success=False, message=err)
            return self.last_result

        sku = item.get_sku(plan.sku_id)
        pay_fen = plan.pay_money_fen or (sku.price_fen * plan.buy_num if sku else 0)

        if plan.schedule_start:
            self.state = State.SCHEDULED
            ok = await self._wait_until(plan.schedule_start, "脚本启动")
            if not ok:
                return None

        self.state = State.PREPARING
        offset = await sync_time(self.client)
        self._log(f"  [时间同步] 服务器偏移 {offset:+.1f}ms")
        await prewarm_client(self.client, plan.project_id, plan.prewarm_connections)

        token = await fetch_order_token(
            self.client,
            plan.project_id,
            plan.screen_id,
            plan.sku_id,
            plan.buy_num,
        )
        if token:
            self._log("  [预确认] 已获取下单 token")

        payload = build_payload(
            plan.project_id,
            plan.screen_id,
            plan.sku_id,
            plan.buy_num,
            pay_fen,
            plan.buyer,
            token=token,
        )
        device_id = self.client.cookies.get("deviceFingerprint", "") or self.client.cookies.get("buvid3", "")
        body = payload_to_dict(payload, device_id)

        if plan.sale_time:
            self.state = State.WAITING
            timer = PreciseTimer(time_offset_ms=offset, pre_fire_ms=plan.pre_fire_ms)
            self._timer = timer
            self._log(f"  [开售时间] {plan.sale_time.strftime('%Y-%m-%d %H:%M:%S')}")
            await timer.wait_until(
                plan.sale_time,
                on_tick=lambda s: self._log(f"  [倒计时] {s:.0f}s") if s <= 30 else None,
            )
            if self._cancelled:
                self.state = State.CANCELLED
                return None

        self.state = State.ORDERING
        interval_s = max(plan.grab_interval_ms, 50) / 1000

        for attempt in range(1, plan.max_attempts + 1):
            if self._cancelled:
                self.state = State.CANCELLED
                return None

            self._log(f"  [下单] 第 {attempt}/{plan.max_attempts} 次请求...")
            t0 = datetime.now()
            result = await submit_order(self.client, body, attempt=attempt)
            elapsed = (datetime.now() - t0).total_seconds() * 1000
            self.last_result = result

            if result.success:
                self.state = State.SUCCESS
                self._log(f"  [成功] order_id={result.order_id} ({elapsed:.0f}ms)")
                return result

            self._log(f"  [失败] {result.message} ({elapsed:.0f}ms)")
            if attempt >= plan.max_attempts or not is_retryable(result):
                self.state = State.FAILED
                return result

            await asyncio.sleep(interval_s)

        self.state = State.FAILED
        return self.last_result
