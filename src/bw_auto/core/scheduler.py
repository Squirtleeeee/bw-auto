"""
精确定时器：等待到目标时间，误差 < 10ms。
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime


class PreciseTimer:
    """精确定时器

    策略:
      - 长等待 (> 1s): asyncio.sleep 省 CPU
      - 末段 (< 0.5s): busy-wait 自旋，毫秒级精度
    """

    def __init__(self, time_offset_ms: float = 0.0, pre_fire_ms: float = 150.0):
        # time_offset_ms: 服务器时间 - 本地时间 (正 = 服务器快)
        # pre_fire_ms: 提前多久发请求 (抵消网络延迟)
        self.time_offset_ms = time_offset_ms
        self.pre_fire_ms = pre_fire_ms

    def _server_time_now_ms(self) -> float:
        """当前服务器时间 (毫秒时间戳)"""
        return (time.time() * 1000) + self.time_offset_ms

    async def wait_until(self, target: datetime) -> None:
        """精确等待到 target 时间 (服务器时间)"""
        target_ms = target.timestamp() * 1000

        while True:
            now_ms = self._server_time_now_ms()
            remaining_ms = target_ms - now_ms - self.pre_fire_ms

            if remaining_ms <= 0:
                break

            if remaining_ms > 500:
                # 长等待 — 睡到倒数 500ms
                sleep_s = (remaining_ms - 400) / 1000
                await asyncio.sleep(sleep_s)
            else:
                # 末段 busy-wait (精度 ~1ms)
                while (time.time() * 1000) + self.time_offset_ms < target_ms - self.pre_fire_ms:
                    pass
                break
