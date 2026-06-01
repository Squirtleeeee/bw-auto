"""
bw-auto CLI — Bilibili 会员购抢票工具

用法:
  bw-auto login              扫码登录
  bw-auto info --id 80037    查看商品信息
  bw-auto grab --id 80037    交互式抢票
  bw-auto status             检查登录状态
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime

import click
import httpx
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from bw_auto.auth.qrcode import check_login, qrcode_login
from bw_auto.auth.session import is_session_valid, load_cookies, save_cookies
from bw_auto.bot.engine import GrabEngine
from bw_auto.core.models import BuyerInfo
from bw_auto.api.show_api import get_buyer_list

load_dotenv()
console = Console()

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def _make_client(cookies: dict | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        cookies=cookies or load_cookies(),
        headers={"User-Agent": UA, "Origin": "https://show.bilibili.com"},
        follow_redirects=True,
        timeout=30.0,
    )


# ======================================================================
# CLI
# ======================================================================

@click.group()
def cli():
    """bw-auto — Bilibili 会员购抢票工具"""


@cli.command()
def login():
    """扫码登录 Bilibili，保存 Cookie 到本地"""

    async def _login():
        async with _make_client(cookies={}) as client:
            result = await qrcode_login(client)
            save_cookies(client)
            if await check_login(client):
                console.print(f"\n  [green]登录成功！[/green]")
                console.print(f"  UID: {result.dedeuserid}")
                console.print(f"  Cookie 已保存到 .cookies.json")
            else:
                console.print("\n  [red]登录验证失败[/red]")

    asyncio.run(_login())


@cli.command()
@click.option("--id", "project_id", required=True, help="商品 project_id")
def info(project_id: str):
    """查看商品详情 (场次、票档、开售时间)"""

    async def _info():
        async with _make_client() as client:
            from bw_auto.core.item import fetch_item, print_item
            item = await fetch_item(client, project_id)
            print_item(item)

    asyncio.run(_info())


@cli.command()
@click.option("--id", "project_id", required=True, help="商品 project_id")
@click.option("--num", default=1, type=int, help="购买数量")
@click.option("--time", "sale_time_str", default="", help="开售时间 'YYYY-MM-DD HH:MM:SS'")
@click.option("--pre-fire", default=200.0, type=float, help="提前发送量 (毫秒)")
def grab(project_id: str, num: int, sale_time_str: str, pre_fire: float):
    """交互式抢票 — 选择场次/票档/购买人，到点自动下单"""

    async def _grab():
        cookies = load_cookies()
        if not is_session_valid(cookies):
            console.print("[red]未登录或 Cookie 过期，请先执行: bw-auto login[/red]")
            return

        async with _make_client(cookies=cookies) as client:
            # ================================================================
            # Step 1: 加载商品信息
            # ================================================================
            from bw_auto.core.item import fetch_item

            console.print(f"\n[bold cyan]>>> 加载商品 {project_id} ...[/bold cyan]")
            item = await fetch_item(client, project_id)
            raw = item.raw  # 保留原始 API 数据

            console.print(f"\n  [bold]{item.name}[/bold]")

            # ================================================================
            # Step 2: 选择场次
            # ================================================================
            screens = raw.get("screen_list") or []
            if not screens:
                console.print("[red]该商品没有场次信息[/red]")
                return

            if len(screens) == 1:
                chosen_screen = screens[0]
                console.print(f"  场次: {chosen_screen['name']}")
            else:
                console.print(f"\n[bold yellow]可选场次:[/bold yellow]")
                for i, sc in enumerate(screens):
                    start = ""
                    if sc.get("sale_start"):
                        start = datetime.fromtimestamp(float(sc["sale_start"])).strftime("%m/%d %H:%M")
                    end = ""
                    if sc.get("sale_end"):
                        end = datetime.fromtimestamp(float(sc["sale_end"])).strftime("%H:%M")
                    console.print(f"  [{i+1}] {sc['name']}  ({start} - {end})")

                choice = click.prompt("  选择场次编号", type=int, default=1)
                if choice < 1 or choice > len(screens):
                    console.print("[red]无效选择[/red]")
                    return
                chosen_screen = screens[choice - 1]

            screen_id = str(chosen_screen["id"])
            console.print(f"  [green]已选: {chosen_screen['name']}[/green]")

            # ================================================================
            # Step 3: 选择票档
            # ================================================================
            # 票档可能来自: screen.ticket_list (新版) 或 顶层 sku_list (旧版)
            tickets = chosen_screen.get("ticket_list") or raw.get("sku_list") or []
            if not tickets:
                console.print("[red]该商品没有票档信息[/red]")
                return

            if len(tickets) == 1:
                chosen_ticket = tickets[0]
                price_yuan = int(chosen_ticket.get("price", 0)) / 100
                display_name = chosen_ticket.get("desc") or chosen_ticket.get("name") or "默认票档"
                console.print(f"  票档: {display_name}  ￥{price_yuan:.0f}")
            else:
                console.print(f"\n[bold yellow]可选票档:[/bold yellow]")
                for i, tk in enumerate(tickets):
                    price_yuan = int(tk.get("price", 0)) / 100
                    stock = tk.get("sale_count", "?")
                    limit = tk.get("limit_per_user", "?")
                    display_name = tk.get("desc") or tk.get("name") or f"票档{i+1}"
                    console.print(f"  [{i+1}] {display_name}  ￥{price_yuan:.0f}  库存:{stock}  限购:{limit}")

                choice = click.prompt("  选择票档编号", type=int, default=1)
                if choice < 1 or choice > len(tickets):
                    console.print("[red]无效选择[/red]")
                    return
                chosen_ticket = tickets[choice - 1]

            sku_id = str(chosen_ticket["id"])
            price_fen = int(chosen_ticket.get("price", 0))  # 分
            price_yuan = price_fen / 100
            display_name = chosen_ticket.get("desc") or chosen_ticket.get("name") or "默认票档"
            console.print(f"  [green]已选: {display_name}  ￥{price_yuan:.0f}[/green]")

            # ================================================================
            # Step 4: 选择购买人
            # ================================================================
            console.print(f"\n[bold yellow]获取购买人列表...[/bold yellow]")
            buyers = await get_buyer_list(client)

            if not buyers:
                console.print("[red]没有已保存的购买人信息。请先在 Bilibili App/Web 中添加购买人[/red]")
                return

            if len(buyers) == 1:
                chosen_buyer = buyers[0]
                console.print(f"  购买人: {chosen_buyer.get('name', '?')}  {chosen_buyer.get('tel', '?')}")
            else:
                console.print(f"\n[bold yellow]选择购买人:[/bold yellow]")
                for i, b in enumerate(buyers):
                    name = b.get("name", "?")
                    tel = b.get("tel", b.get("phone", "?"))
                    id_no = b.get("id_card_no", "?")
                    masked_id = id_no[:3] + "****" + id_no[-4:] if len(id_no) > 6 else id_no
                    default = " [默认]" if b.get("is_default") else ""
                    console.print(f"  [{i+1}] {name}  {tel}  {masked_id}{default}")

                choice = click.prompt("  选择购买人编号", type=int, default=1)
                if choice < 1 or choice > len(buyers):
                    console.print("[red]无效选择[/red]")
                    return
                chosen_buyer = buyers[choice - 1]

            buyer = BuyerInfo(
                name=chosen_buyer.get("name", ""),
                tel=chosen_buyer.get("tel", chosen_buyer.get("phone", "")),
                id_card_type=chosen_buyer.get("id_card_type", 0),
                id_card_no=chosen_buyer.get("id_card_no", ""),
            )
            console.print(f"  [green]已选: {buyer.name}  {buyer.tel}[/green]")

            # ================================================================
            # Step 5: 确认信息
            # ================================================================
            console.print(f"\n[bold cyan]--- 订单确认 ---[/bold cyan]")
            console.print(f"  商品: {item.name}")
            console.print(f"  场次: {chosen_screen['name']}")
            console.print(f"  票档: {display_name}  x{num}  ￥{price_yuan * num:.0f}")
            console.print(f"  购买人: {buyer.name}  {buyer.tel}")

            if not click.confirm("\n  确认并开始等待抢票?"):
                console.print("  已取消")
                return

            # ================================================================
            # Step 6: 开售时间
            # ================================================================
            sale_time = None
            if sale_time_str:
                sale_time = datetime.strptime(sale_time_str, "%Y-%m-%d %H:%M:%S")
            else:
                # 尝试从场次获取
                sale_start = chosen_screen.get("sale_start")
                if sale_start:
                    sale_time = datetime.fromtimestamp(float(sale_start))
                else:
                    # 从商品级别获取
                    raw_sale = raw.get("sale_time") or raw.get("start_time")
                    if raw_sale:
                        sale_time = datetime.fromtimestamp(float(raw_sale))

            if not sale_time:
                console.print("[red]无法确定开售时间，请用 --time 指定[/red]")
                return

            # ================================================================
            # Step 7: 执行抢票
            # ================================================================
            engine = GrabEngine(client)

            try:
                result = await engine.grab(
                    item=item,
                    screen_id=screen_id,
                    sku_id=sku_id,
                    buy_num=num,
                    buyer=buyer,
                    sale_time=sale_time,
                    pre_fire_ms=pre_fire,
                )

                if result and result.success:
                    console.print(f"\n[bold green]========================================")
                    console.print(f"  下单成功！")
                    console.print(f"  订单号: {result.order_id}")
                    console.print(f"  请尽快在 Bilibili App 中完成支付")
                    console.print(f"  未支付订单将在 5-15 分钟后自动取消")
                    console.print(f"========================================[/bold green]")
                else:
                    msg = result.message if result else "未知错误"
                    console.print(f"\n[bold red]下单失败: {msg}[/bold red]")

            except KeyboardInterrupt:
                engine.cancel()
                console.print("\n  已取消抢票")

    asyncio.run(_grab())


@cli.command()
def status():
    """检查登录状态"""

    async def _status():
        cookies = load_cookies()
        if not is_session_valid(cookies):
            console.print("[red]未找到有效 Cookie，请执行: bw-auto login[/red]")
            return
        async with _make_client(cookies=cookies) as client:
            if await check_login(client):
                console.print(f"[green]已登录[/green] (UID: {cookies.get('DedeUserID', '?')})")
            else:
                console.print("[red]Cookie 已过期，请重新执行: bw-auto login[/red]")

    asyncio.run(_status())


if __name__ == "__main__":
    cli()
