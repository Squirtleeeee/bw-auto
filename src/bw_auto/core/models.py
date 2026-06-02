"""核心数据模型"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class BuyerInfo:
    """实名购买人信息"""
    name: str = ""
    tel: str = ""
    id_card_type: int = 0
    id_card_no: str = ""
    buyer_id: str = ""


@dataclass
class Screen:
    screen_id: str
    name: str
    sale_start: datetime | None = None
    sale_end: datetime | None = None


@dataclass
class Sku:
    sku_id: str
    screen_id: str
    name: str
    price_fen: int = 0
    stock: int = 0
    limit_per_user: int = 1


@dataclass
class Item:
    project_id: str
    name: str
    sale_flag: int = 0
    screens: list[Screen] = field(default_factory=list)
    skus: list[Sku] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def skus_for_screen(self, screen_id: str) -> list[Sku]:
        return [s for s in self.skus if s.screen_id == screen_id]

    def get_sku(self, sku_id: str) -> Sku | None:
        return next((s for s in self.skus if s.sku_id == sku_id), None)


@dataclass
class OrderPayload:
    project_id: str
    screen_id: str
    sku_id: str
    buy_num: int = 1
    pay_money: int = 0
    buyer_info: BuyerInfo = field(default_factory=BuyerInfo)
    deliver_info: dict = field(default_factory=lambda: {"deliver_type": 0})
    token: str = ""


@dataclass
class OrderResult:
    success: bool
    order_id: str = ""
    message: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    attempt: int = 0


@dataclass
class GrabPlan:
    """一次抢票任务的完整参数"""
    project_id: str
    screen_id: str
    sku_id: str
    buy_num: int = 1
    pay_money_fen: int = 0
    buyer: BuyerInfo = field(default_factory=BuyerInfo)
    sale_time: datetime | None = None
    schedule_start: datetime | None = None
    pre_fire_ms: float = 200.0
    grab_interval_ms: float = 300.0
    max_attempts: int = 15
    prewarm_connections: int = 3
