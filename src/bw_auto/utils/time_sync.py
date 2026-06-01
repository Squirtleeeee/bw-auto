"""
时间同步：计算本地时钟与 Bilibili 服务器的偏移量。

方法：请求 api.bilibili.com，读取响应头 Date 字段，与本地时间对比得出 offset。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx

SYNC_URL = "https://api.bilibili.com/x/web-interface/nav"


async def sync_time(client: httpx.AsyncClient) -> float:
    """返回 server_time - local_time 的偏移量 (毫秒)

    正值 = 服务器时钟比本地快 → 需要提前发请求
    """
    local_before = time.time()
    resp = await client.get(SYNC_URL)
    local_after = time.time()

    date = resp.headers.get("Date", "")
    if date:
        server_ts = datetime.strptime(date, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc).timestamp()
    else:
        server_ts = (local_before + local_after) / 2  # fallback: 假设对称延迟

    # 本地时间取请求前后的中点，抵消单向延迟
    local_ts = (local_before + local_after) / 2
    offset_ms = (server_ts - local_ts) * 1000
    return offset_ms
