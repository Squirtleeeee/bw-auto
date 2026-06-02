"""应用配置 — 支持 .env 与运行时覆盖。"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

COOKIE_FILE = Path(".cookies.json")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    buyer_name: str = Field(default="", alias="BUYER_NAME")
    buyer_tel: str = Field(default="", alias="BUYER_TEL")
    buyer_id_card: str = Field(default="", alias="BUYER_ID_CARD")

    target_project_id: str = Field(default="", alias="TARGET_PROJECT_ID")
    target_screen_id: str = Field(default="", alias="TARGET_SCREEN_ID")
    target_sku_id: str = Field(default="", alias="TARGET_SKU_ID")
    target_buy_num: int = Field(default=1, alias="TARGET_BUY_NUM")
    target_sale_time: str = Field(default="", alias="TARGET_SALE_TIME")

    pre_fire_ms: float = Field(default=200.0, alias="PRE_FIRE_MS")
    grab_interval_ms: float = Field(default=300.0, alias="GRAB_INTERVAL_MS")
    grab_max_attempts: int = Field(default=15, alias="GRAB_MAX_ATTEMPTS")
    num_prewarm_connections: int = Field(default=3, alias="NUM_PREWARM_CONNECTIONS")
    schedule_start_time: str = Field(default="", alias="SCHEDULE_START_TIME")

    web_host: str = Field(default="127.0.0.1", alias="WEB_HOST")
    web_port: int = Field(default=8765, alias="WEB_PORT")


def get_settings() -> Settings:
    return Settings()
