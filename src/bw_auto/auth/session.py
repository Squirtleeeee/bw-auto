"""
Session 管理 — Cookie 持久化、过期检测、自动恢复。
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx

COOKIE_FILE = Path(".cookies.json")
SESSION_KEYS = ("SESSDATA", "bili_jct", "DedeUserID", "sid")


def save_cookies(client: httpx.AsyncClient, path: Path = COOKIE_FILE) -> None:
    """把 client 里的 cookie 持久化到 JSON"""
    cookies = dict(client.cookies.items())
    import json
    path.write_text(json.dumps(cookies, indent=2, ensure_ascii=False), encoding="utf-8")


def load_cookies(path: Path = COOKIE_FILE) -> dict[str, str]:
    """从 JSON 文件加载 cookie"""
    if not path.exists():
        return {}
    import json
    return json.loads(path.read_text(encoding="utf-8"))


def is_session_valid(cookies: dict[str, str]) -> bool:
    """检查关键 cookie 是否存在且未过期"""
    return all(cookies.get(k) for k in SESSION_KEYS)
