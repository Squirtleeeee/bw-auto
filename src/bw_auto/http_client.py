"""共享 HTTP 客户端工厂与连接预热。"""

from __future__ import annotations

import httpx

from bw_auto.auth.session import load_cookies

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def make_client(cookies: dict | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        cookies=cookies if cookies is not None else load_cookies(),
        headers={
            "User-Agent": DEFAULT_UA,
            "Origin": "https://show.bilibili.com",
            "Accept": "application/json, text/plain, */*",
        },
        follow_redirects=True,
        timeout=30.0,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )


async def prewarm_client(client: httpx.AsyncClient, project_id: str, n: int = 3) -> None:
    """预热到会员购域名的连接，减少首开售请求延迟。"""
    url = f"https://show.bilibili.com/api/ticket/project/get?id={project_id}&source=pc"
    referer = f"https://show.bilibili.com/platform/detail.html?id={project_id}"
    for _ in range(max(1, n)):
        try:
            await client.get(url, headers={"Referer": referer})
        except httpx.HTTPError:
            pass
