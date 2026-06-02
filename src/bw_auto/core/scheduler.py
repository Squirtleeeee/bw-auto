"""精确定时器"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Callable


class PreciseTimer:
    def __init__(self, time_offset_ms: float = 0.0, pre_fire_ms: float = 200.0):
        self.time_offset_ms = time_offset_ms
        self.pre_fire_ms = pre_fire_ms
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def _server_time_now_ms(self) -> float:
        return (time.time() * 1000) + self.time_offset_ms

    async def wait_until(
        self,
        target: datetime,
        *,
        on_tick: Callable[[float], None] | None = None,
        tick_interval: float = 1.0,
    ) -> None:
        target_ms = target.timestamp() * 1000
        last_tick = 0.0

        while not self._cancelled:
            now_ms = self._server_time_now_ms()
            remaining_ms = target_ms - now_ms - self.pre_fire_ms
            if remaining_ms <= 0:
                break

            if on_tick and (time.time() - last_tick) >= tick_interval:
                on_tick(remaining_ms / 1000)
                last_tick = time.time()

            if remaining_ms > 500:
                sleep_s = min((remaining_ms - 400) / 1000, 1.0)
                await asyncio.sleep(sleep_s)
            else:
                while not self._cancelled:
                    if self._server_time_now_ms() >= target_ms - self.pre_fire_ms:
                        break
                break
