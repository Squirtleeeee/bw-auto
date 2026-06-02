"""bw-auto Web UI — FastAPI"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from bw_auto.auth.qrcode import (
    CODE_EXPIRED,
    CODE_SCANNED,
    CODE_SUCCESS,
    CODE_UNSCANNED,
    generate_qrcode,
    poll_qrcode_once,
    qr_url_to_base64,
    check_login,
)
from bw_auto.auth.session import COOKIE_FILE, is_session_valid, load_cookies, save_cookies
from bw_auto.api.show_api import get_buyer_list
from bw_auto.config import get_settings
from bw_auto.core.item import fetch_item, validate_item_for_grab
from bw_auto.core.models import BuyerInfo, GrabPlan, OrderResult
from bw_auto.http_client import make_client
from bw_auto.bot.engine import GrabEngine, State
from bw_auto.services.selection import (
    buyer_from_api_row,
    buyers_to_api_list,
    item_to_api_dict,
    parse_sale_time,
)
from bw_auto.web.state import GrabJob, app_state

import sys as _sys
if getattr(_sys, "frozen", False):
    STATIC_DIR = Path(_sys._MEIPASS) / "src" / "bw_auto" / "web" / "static"
else:
    STATIC_DIR = Path(__file__).parent / "static"
app = FastAPI(title="bw-auto", version="0.2.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class GrabStartRequest(BaseModel):
    project_id: str
    screen_id: str
    sku_id: str
    buy_num: int = 1
    pay_money_fen: int = 0
    buyer_id: str = ""
    buyer_name: str
    buyer_tel: str
    buyer_id_card: str = ""
    buyer_id_card_type: int = 0
    sale_time: str | None = None
    schedule_start: str | None = None
    pre_fire_ms: float = 200.0
    grab_interval_ms: float = 300.0
    max_attempts: int = 15
    prewarm_connections: int = 3


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    text = s.replace("T", " ").strip()
    if len(text) == 16:
        text = text + ":00"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise HTTPException(400, f"时间格式无效: {s}")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/login/logout")
async def login_logout():
    import os
    try:
        os.remove(COOKIE_FILE)
    except OSError:
        pass
    return {"ok": True}


@app.get("/api/login/status")
async def login_status():
    cookies = load_cookies()
    if not is_session_valid(cookies):
        return {"logged_in": False}
    async with make_client(cookies) as client:
        ok = await check_login(client)
        uid = cookies.get("DedeUserID", "")
        return {"logged_in": ok, "uid": uid}


@app.post("/api/login/qrcode/start")
async def login_qrcode_start():
    if app_state.login.client:
        await app_state.login.client.aclose()
    app_state.login.client = make_client(cookies={})
    qr = await generate_qrcode(app_state.login.client)
    app_state.login.qrcode = qr
    app_state.login.login_message = "请使用 Bilibili App 扫码"
    return {
        "qrcode_key": qr.qrcode_key,
        "url": qr.url,
        "image_base64": qr_url_to_base64(qr.url),
    }


@app.get("/api/login/qrcode/poll")
async def login_qrcode_poll():
    sess = app_state.login
    if not sess.client or not sess.qrcode:
        raise HTTPException(400, "请先获取二维码")
    code, msg, data = await poll_qrcode_once(sess.client, sess.qrcode.qrcode_key)
    status = "waiting"
    if code == CODE_UNSCANNED:
        sess.login_message = "等待扫码..."
    elif code == CODE_SCANNED:
        sess.login_message = "已扫码，请在手机上确认"
        status = "scanned"
    elif code == CODE_EXPIRED:
        sess.login_message = "二维码已过期"
        status = "expired"
    elif code == CODE_SUCCESS:
        save_cookies(sess.client)
        sess.login_message = "登录成功"
        status = "success"
    else:
        sess.login_message = msg or "未知状态"
    logged_in = False
    uid = ""
    if status == "success":
        logged_in = await check_login(sess.client)
        uid = sess.client.cookies.get("DedeUserID", "")
    return {
        "code": code,
        "status": status,
        "message": sess.login_message,
        "logged_in": logged_in,
        "uid": uid,
    }


@app.get("/api/project/{project_id}")
async def get_project(project_id: str):
    cookies = load_cookies()
    if not is_session_valid(cookies):
        raise HTTPException(401, "请先登录")
    try:
        async with make_client(cookies) as client:
            item = await fetch_item(client, project_id)
            buyers = await get_buyer_list(client)
            return {
                "project": item_to_api_dict(item),
                "buyers": buyers_to_api_list(buyers),
            }
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e
    except httpx.HTTPError as e:
        raise HTTPException(502, f"网络请求失败: {e}") from e
    except Exception as e:
        raise HTTPException(500, f"解析商品失败: {e}") from e


@app.post("/api/grab/start")
async def grab_start(req: GrabStartRequest):
    cookies = load_cookies()
    if not is_session_valid(cookies):
        raise HTTPException(401, "请先登录")
    if not req.buyer_name or not req.buyer_tel:
        raise HTTPException(400, "请填写购买人姓名与手机号")

    async with make_client(cookies) as client:
        item = await fetch_item(client, req.project_id)
        err = validate_item_for_grab(item, req.screen_id, req.sku_id, req.buy_num)
        if err:
            raise HTTPException(400, err)

        # 获取完整购买人信息，优先用 buyer_id 精准匹配
        buyer_name = req.buyer_name
        buyer_tel = req.buyer_tel
        buyer_id_card = req.buyer_id_card
        buyer_id_card_type = req.buyer_id_card_type
        buyer_db_id = req.buyer_id
        try:
            buyers = await get_buyer_list(client)
            for b in buyers:
                if req.buyer_id and str(b.get("id", "")) == str(req.buyer_id):
                    buyer_name = b.get("name", buyer_name)
                    buyer_tel = b.get("tel", buyer_tel)
                    buyer_id_card = b.get("personal_id", buyer_id_card)
                    buyer_id_card_type = int(b.get("id_type", buyer_id_card_type) or 0)
                    buyer_db_id = str(b.get("id", ""))
                    break
                elif not req.buyer_id and b.get("name") == req.buyer_name and (
                    b.get("tel") == req.buyer_tel or b.get("phone") == req.buyer_tel
                ):
                    buyer_tel = b.get("tel", buyer_tel)
                    buyer_id_card = b.get("personal_id", buyer_id_card)
                    buyer_id_card_type = int(b.get("id_type", buyer_id_card_type) or 0)
                    buyer_db_id = str(b.get("id", ""))
                    break
        except Exception:
            pass

        screen_raw = next(
            (s for s in item.raw.get("screen_list") or [] if str(s.get("id")) == req.screen_id),
            {},
        )
        sale_time = _parse_dt(req.sale_time) or parse_sale_time(
            item, req.screen_id, screen_raw, ""
        )
        if not sale_time:
            raise HTTPException(400, "无法确定开售时间，请在页面填写「开售时间」")
        sku = item.get_sku(req.sku_id)
        pay_fen = req.pay_money_fen or (sku.price_fen * req.buy_num if sku else 0)

        plan = GrabPlan(
            project_id=req.project_id,
            screen_id=req.screen_id,
            sku_id=req.sku_id,
            buy_num=req.buy_num,
            pay_money_fen=pay_fen,
            buyer=BuyerInfo(
                name=buyer_name,
                tel=buyer_tel,
                id_card_no=buyer_id_card,
                id_card_type=buyer_id_card_type,
                buyer_id=buyer_db_id,
            ),
            sale_time=sale_time,
            schedule_start=_parse_dt(req.schedule_start),
            pre_fire_ms=req.pre_fire_ms,
            grab_interval_ms=req.grab_interval_ms,
            max_attempts=req.max_attempts,
            prewarm_connections=req.prewarm_connections,
        )

    job_id = app_state.next_job_id()

    async def _run(job: GrabJob) -> None:
        job.state = "running"

        def log(msg: str) -> None:
            job.logs.append(msg)

        try:
            async with make_client(load_cookies()) as client:
                engine = GrabEngine(client, log=log)
                job.engine = engine
                result = await engine.run(job.plan)
                job.result = result
                job.state = "success" if result and result.success else "failed"
        except Exception as e:
            job.logs.append(f"  [异常] {e}")
            job.result = OrderResult(success=False, message=str(e))
            job.state = "failed"

    job = GrabJob(id=job_id, plan=plan)
    app_state.grab_jobs[job_id] = job
    job.task = asyncio.create_task(_run(job))
    return {"job_id": job_id, "sale_time": sale_time.isoformat() if sale_time else None}


@app.get("/api/grab/{job_id}")
async def grab_status(job_id: str):
    job = app_state.grab_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    engine_state = job.engine.state.name if job.engine else "PENDING"
    return {
        "job_id": job_id,
        "state": job.state,
        "engine_state": engine_state,
        "logs": job.logs[-80:],
        "result": (
            {
                "success": job.result.success,
                "order_id": job.result.order_id,
                "message": job.result.message,
                "attempt": job.result.attempt,
            }
            if job.result
            else None
        ),
    }


@app.post("/api/grab/{job_id}/cancel")
async def grab_cancel(job_id: str):
    job = app_state.grab_jobs.get(job_id)
    if not job or not job.engine:
        raise HTTPException(404, "任务不存在")
    job.engine.cancel()
    job.state = "cancelled"
    return {"ok": True}


def _open_browser(url: str) -> None:
    """用应用模式打开浏览器窗口（无地址栏，像独立 App）"""
    import shutil
    import subprocess
    import sys

    # 尝试 Chrome/Edge 应用模式
    for browser in ("chrome", "edge", "chromium"):
        exe = shutil.which(browser)
        if not exe:
            continue
        try:
            subprocess.Popen(
                [exe, f"--app={url}", "--window-size=420,820"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except Exception:
            continue

    # 兜底：系统默认浏览器
    import webbrowser
    webbrowser.open(url)


def run_server() -> None:
    import asyncio
    import uvicorn

    s = get_settings()
    url = f"http://{s.web_host}:{s.web_port}"

    # 延迟 1.5s 后自动打开浏览器
    async def _delayed_open() -> None:
        await asyncio.sleep(1.5)
        _open_browser(url)

    # 在后台线程中调度
    import threading
    def _schedule() -> None:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_delayed_open())

    threading.Thread(target=_schedule, daemon=True).start()

    print(f"\n  bw-auto Web 已启动 -> {url}\n")
    uvicorn.run(
        "bw_auto.web.app:app",
        host=s.web_host,
        port=s.web_port,
        reload=False,
        log_config=None,
    )
