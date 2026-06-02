"""Web 服务运行时状态（单进程内存）。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

from bw_auto.auth.qrcode import QRCodeInfo
from bw_auto.bot.engine import GrabEngine, State
from bw_auto.core.models import GrabPlan, OrderResult


@dataclass
class LoginSession:
    client: httpx.AsyncClient | None = None
    qrcode: QRCodeInfo | None = None
    login_message: str = ""


@dataclass
class GrabJob:
    id: str
    plan: GrabPlan
    state: str = "pending"
    logs: list[str] = field(default_factory=list)
    result: OrderResult | None = None
    task: asyncio.Task | None = None
    engine: GrabEngine | None = None


class AppState:
    def __init__(self) -> None:
        self.login = LoginSession()
        self.grab_jobs: dict[str, GrabJob] = {}
        self._job_seq = 0

    def next_job_id(self) -> str:
        self._job_seq += 1
        return f"job-{self._job_seq}"


app_state = AppState()
