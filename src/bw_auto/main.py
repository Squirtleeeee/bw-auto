"""
bw-auto CLI — Bilibili 会员购抢票工具
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime

import click
from dotenv import load_dotenv
from rich.console import Console

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from bw_auto.api.show_api import get_buyer_list
from bw_auto.auth.qrcode import check_login, qrcode_login
from bw_auto.auth.session import is_session_valid, load_cookies, save_cookies
from bw_auto.bot.engine import GrabEngine
from bw_auto.config import get_settings
from bw_auto.core.item import fetch_item, print_item, validate_item_for_grab
from bw_auto.core.models import BuyerInfo, GrabPlan
from bw_auto.http_client import make_client
from bw_auto.services.selection import buyer_from_api_row, parse_sale_time

load_dotenv()
console = Console()


@click.group()
def cli():
    """bw-auto — Bilibili 会员购抢票工具"""


@cli.command()
def login():
    """扫码登录 Bilibili，保存 Cookie 到本地"""

    async def _login():
        async with make_client(cookies={}) as client:
            await qrcode_login(client)
            save_cookies(client)
            if await check_login(client):
                console.print("\n  [green]登录成功！[/green] Cookie 已保存到 .cookies.json")
            else:
                console.print("\n  [red]登录验证失败[/red]")

    asyncio.run(_login())


@cli.command()
def status():
    """检查登录状态"""

    async def _run():
        cookies = load_cookies()
        if not is_session_valid(cookies):
            console.print("[red]未找到有效 Cookie，请执行: bw-auto login[/red]")
            return
        async with make_client(cookies=cookies) as client:
            if await check_login(client):
                console.print(f"[green]已登录[/green] (UID: {cookies.get('DedeUserID', '?')})")
            else:
                console.print("[red]Cookie 已过期，请重新执行: bw-auto login[/red]")

    asyncio.run(_run())


@cli.command()
@click.option("--id", "project_id", required=True, help="商品 project_id")
def info(project_id: str):
    """查看商品详情"""

    async def _run():
        async with make_client() as client:
            item = await fetch_item(client, project_id)
            print_item(item)

    asyncio.run(_run())


@cli.command("web")
@click.option("--host", default=None, help="监听地址")
@click.option("--port", default=None, type=int, help="端口")
def web(host: str | None, port: int | None):
    """启动 Web 界面（浏览器操作）"""
    import uvicorn

    s = get_settings()
    uvicorn.run(
        "bw_auto.web.app:app",
        host=host or s.web_host,
        port=port or s.web_port,
        reload=False,
    )


@cli.command()
@click.option("--id", "project_id", default=None, help="商品 project_id")
@click.option("--num", default=None, type=int, help="购买数量")
@click.option("--time", "sale_time_str", default="", help="开售时间")
@click.option("--start", "schedule_start_str", default="", help="脚本启动时间")
@click.option("--pre-fire", default=None, type=float, help="提前发单毫秒")
@click.option("--interval", "grab_interval_ms", default=None, type=float, help="失败重试间隔毫秒")
@click.option("--attempts", "max_attempts", default=None, type=int, help="最大尝试次数")
@click.option("--yes", "-y", is_flag=True, help="跳过确认")
def grab(
    project_id: str | None,
    num: int | None,
    sale_time_str: str,
    schedule_start_str: str,
    pre_fire: float | None,
    grab_interval_ms: float | None,
    max_attempts: int | None,
    yes: bool,
):
    """交互式抢票 — 到点自动下单，失败按间隔重试"""

    async def _grab():
        settings = get_settings()
        project_id_v = project_id or settings.target_project_id
        if not project_id_v:
            console.print("[red]请指定 --id 或在 .env 设置 TARGET_PROJECT_ID[/red]")
            return

        cookies = load_cookies()
        if not is_session_valid(cookies):
            console.print("[red]未登录，请先: bw-auto login[/red]")
            return

        buy_num = num if num is not None else settings.target_buy_num
        pre_fire_v = pre_fire if pre_fire is not None else settings.pre_fire_ms
        interval_v = grab_interval_ms if grab_interval_ms is not None else settings.grab_interval_ms
        attempts_v = max_attempts if max_attempts is not None else settings.grab_max_attempts

        async with make_client(cookies=cookies) as client:
            console.print(f"\n[bold cyan]>>> 加载商品 {project_id_v} ...[/bold cyan]")
            item = await fetch_item(client, project_id_v)
            raw = item.raw
            console.print(f"\n  [bold]{item.name}[/bold]")

            screens = raw.get("screen_list") or []
            if not screens:
                console.print("[red]没有场次信息[/red]")
                return

            screen_id = settings.target_screen_id
            if not screen_id:
                if len(screens) == 1:
                    chosen_screen = screens[0]
                else:
                    for i, sc in enumerate(screens):
                        start = ""
                        if sc.get("sale_start"):
                            start = datetime.fromtimestamp(float(sc["sale_start"])).strftime(
                                "%m/%d %H:%M"
                            )
                        console.print(f"  [{i+1}] {sc['name']}  开售:{start}")
                    c = click.prompt("  选择场次", type=int, default=1)
                    chosen_screen = screens[c - 1]
                screen_id = str(chosen_screen["id"])
            else:
                chosen_screen = next(
                    (s for s in screens if str(s["id"]) == screen_id),
                    screens[0],
                )

            tickets = chosen_screen.get("ticket_list") or raw.get("sku_list") or []
            if not tickets:
                console.print("[red]没有票档[/red]")
                return

            sku_id = settings.target_sku_id
            if not sku_id:
                if len(tickets) == 1:
                    chosen_ticket = tickets[0]
                else:
                    from bw_auto.services.selection import _is_ticket_available
                    for i, tk in enumerate(tickets):
                        p = int(tk.get("price", 0)) / 100
                        n = tk.get("desc") or tk.get("name", "?")
                        s = "可购" if _is_ticket_available(tk) else "未开放"
                        console.print(f"  [{i+1}] {n}  ￥{p:.0f}  [{s}]")
                    c = click.prompt("  选择票档", type=int, default=1)
                    chosen_ticket = tickets[c - 1]
                sku_id = str(chosen_ticket["id"])
            else:
                chosen_ticket = next((t for t in tickets if str(t["id"]) == sku_id), tickets[0])

            err = validate_item_for_grab(item, screen_id, sku_id, buy_num)
            if err:
                console.print(f"[red]{err}[/red]")
                return

            buyers = await get_buyer_list(client)
            if not buyers:
                console.print(
                    "[red]没有购买人。请先在 Bilibili App 会员购中添加实名购买人[/red]"
                )
                return

            buyer: BuyerInfo
            if settings.buyer_name and settings.buyer_tel:
                buyer = BuyerInfo(
                    name=settings.buyer_name,
                    tel=settings.buyer_tel,
                    id_card_no=settings.buyer_id_card,
                )
            elif len(buyers) == 1:
                buyer = buyer_from_api_row(buyers[0])
            else:
                for i, b in enumerate(buyers):
                    console.print(f"  [{i+1}] {b.get('name')}  {b.get('tel', b.get('phone'))}")
                c = click.prompt("  选择购买人", type=int, default=1)
                buyer = buyer_from_api_row(buyers[c - 1])

            sku = item.get_sku(sku_id)
            pay_fen = (sku.price_fen * buy_num) if sku else int(chosen_ticket.get("price", 0)) * buy_num
            display = (chosen_ticket.get("desc") or chosen_ticket.get("name", "")) if isinstance(
                chosen_ticket, dict
            ) else (sku.name if sku else "")

            console.print(f"\n[bold cyan]--- 确认 ---[/bold cyan]")
            console.print(f"  商品: {item.name}")
            console.print(f"  场次: {chosen_screen['name']}")
            console.print(f"  票档: {display} x{buy_num}  ￥{pay_fen/100:.0f}")
            console.print(f"  购买人: {buyer.name} {buyer.tel}")

            if not yes and not click.confirm("  开始抢票?"):
                return

            sale_time = parse_sale_time(
                item,
                screen_id,
                chosen_screen,
                sale_time_str or settings.target_sale_time,
            )
            if not sale_time:
                console.print("[red]无法确定开售时间，请用 --time 指定[/red]")
                return

            schedule_start = None
            start_s = schedule_start_str or settings.schedule_start_time
            if start_s:
                schedule_start = datetime.strptime(start_s, "%Y-%m-%d %H:%M:%S")

            plan = GrabPlan(
                project_id=project_id_v,
                screen_id=screen_id,
                sku_id=sku_id,
                buy_num=buy_num,
                pay_money_fen=pay_fen,
                buyer=buyer,
                sale_time=sale_time,
                schedule_start=schedule_start,
                pre_fire_ms=pre_fire_v,
                grab_interval_ms=interval_v,
                max_attempts=attempts_v,
                prewarm_connections=settings.num_prewarm_connections,
            )

            engine = GrabEngine(client, log=lambda m: console.print(m))
            try:
                result = await engine.run(plan)
            except KeyboardInterrupt:
                engine.cancel()
                console.print("\n  已取消")
                return

            if result and result.success:
                console.print(f"\n[bold green]下单成功！订单号: {result.order_id}[/bold green]")
                console.print("  请在 Bilibili App 中完成支付")
            elif result:
                console.print(f"\n[bold red]失败: {result.message}[/bold red]")

    asyncio.run(_grab())


if __name__ == "__main__":
    cli()
