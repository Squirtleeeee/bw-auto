"""
Bilibili API HTTP 客户端。

封装 httpx，统一处理：请求头伪装、Cookie 管理、重试、签名。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

COOKIE_FILE = Path(".cookies.json")


class BiliAPIClient:
    """Bilibili API 客户端 — 异步，自动管理 Cookie 和请求头"""

    def __init__(
        self,
        cookies: dict[str, str] | None = None,
        ua: str = DEFAULT_UA,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        self._cookies = cookies or {}
        self._ua = ua
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout
        self._max_retries = max_retries

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            cookies=self._cookies,
            headers=self._base_headers(),
            timeout=self._timeout,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Client not initialised — use 'async with'")
        return self._client

    def _base_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Origin": "https://show.bilibili.com",
            "Referer": "https://show.bilibili.com/",
        }

    # ------------------------------------------------------------------
    # Cookie 持久化
    # ------------------------------------------------------------------

    def save_cookies(self, path: Path = COOKIE_FILE) -> None:
        """把当前 Cookie 写入 JSON 文件"""
        cookies = dict(self.client.cookies.items())
        path.write_text(json.dumps(cookies, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def load_cookies(path: Path = COOKIE_FILE) -> dict[str, str]:
        """从 JSON 文件读取 Cookie"""
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def update_cookies(self, cookies: dict[str, str]) -> None:
        """合并新 Cookie 到当前会话"""
        self.client.cookies.update(cookies)

    @property
    def cookies(self) -> dict[str, str]:
        return dict(self.client.cookies.items())

    # ------------------------------------------------------------------
    # HTTP 请求
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """发送请求 — 带重试"""
        last_exc: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                resp = await self.client.request(
                    method=method,
                    url=url,
                    params=params,
                    data=data,
                    json=json_data,
                    headers=headers,
                )
                return resp
            except httpx.TimeoutException as e:
                last_exc = e
                wait = 2**attempt * 0.5
                time.sleep(wait)
            except httpx.NetworkError as e:
                last_exc = e
                wait = 2**attempt * 0.5
                time.sleep(wait)

        raise last_exc  # type: ignore[misc]

    async def get(self, url: str, *, params: dict[str, Any] | None = None, **kw) -> httpx.Response:
        return await self._request("GET", url, params=params, **kw)

    async def post(
        self,
        url: str,
        *,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        **kw,
    ) -> httpx.Response:
        return await self._request("POST", url, data=data, json_data=json, **kw)

    async def get_json(self, url: str, *, params: dict[str, Any] | None = None, **kw) -> dict[str, Any]:
        """GET 并直接返回解析后的 JSON"""
        resp = await self.get(url, params=params, **kw)
        resp.raise_for_status()
        return resp.json()

    async def post_json(
        self,
        url: str,
        *,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        **kw,
    ) -> dict[str, Any]:
        """POST 并直接返回解析后的 JSON"""
        resp = await self.post(url, data=data, json=json, **kw)
        resp.raise_for_status()
        return resp.json()
