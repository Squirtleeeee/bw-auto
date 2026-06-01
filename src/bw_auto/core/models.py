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
    id_card_type: int = 0       # 0 = 身份证
    id_card_no: str = ""


@dataclass
class Screen:
    """场次信息"""
    screen_id: str
    name: str
    sale_start: datetime | None = None
    sale_end: datetime | None = None


@dataclass
class Sku:
    """票档 / SKU"""
    sku_id: str
    name: str
    price: float = 0.0          # 原始单价 (分)
    stock: int = 0              # 库存
    limit_per_user: int = 1     # 每人限购


@dataclass
class Item:
    """会员购商品"""
    project_id: str
    name: str
    screens: list[Screen] = field(default_factory=list)
    skus: list[Sku] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def first_screen_id(self) -> str:
        return self.screens[0].screen_id if self.screens else ""

    @property
    def first_sku_id(self) -> str:
        return self.skus[0].sku_id if self.skus else ""


@dataclass
class OrderPayload:
    """下单请求体"""
    project_id: str
    screen_id: str
    sku_id: str
    buy_num: int = 1
    pay_money: float = 0.0
    buyer_info: BuyerInfo = field(default_factory=BuyerInfo)
    deliver_info: dict = field(default_factory=lambda: {"deliver_type": 0})
    coupon_list: list = field(default_factory=list)
    token: str = ""


@dataclass
class OrderResult:
    """下单结果"""
    success: bool
    order_id: str = ""
    message: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
