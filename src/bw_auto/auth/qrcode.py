"""
Bilibili 二维码登录。

流程：
1. GET /x/passport-login/web/qrcode/generate → 获取 qrcode_key + 二维码 URL
2. 终端渲染二维码（qrcode 库直接输出 ASCII）
3. 轮询 /x/passport-login/web/qrcode/poll → 等待用户扫码确认
4. 成功 → 返回 Cookie；过期 → 重新生成
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"

# 轮询间隔 (秒)
POLL_INTERVAL = 1.5

# 状态码
CODE_UNSCANNED = 86101   # 未扫码
CODE_SCANNED = 86090     # 已扫码，未确认
CODE_EXPIRED = 86038     # 二维码过期
CODE_SUCCESS = 0         # 登录成功


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class QRCodeInfo:
    url: str
    qrcode_key: str


@dataclass
class LoginResult:
    """登录成功后提取的关键 Cookie"""
    sessdata: str = ""
    bili_jct: str = ""
    dedeuserid: str = ""
    sid: str = ""
    cookies: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# API 调用
# ---------------------------------------------------------------------------

async def _generate_qrcode(client: httpx.AsyncClient) -> QRCodeInfo:
    resp = await client.get(GENERATE_URL)
    resp.raise_for_status()
    data = resp.json()
    if data["code"] != 0:
        raise RuntimeError(f"生成二维码失败: {data.get('message', data)}")
    return QRCodeInfo(
        url=data["data"]["url"],
        qrcode_key=data["data"]["qrcode_key"],
    )


async def _poll_status(client: httpx.AsyncClient, qrcode_key: str) -> tuple[dict[str, Any], httpx.Response]:
    resp = await client.get(POLL_URL, params={"qrcode_key": qrcode_key})
    resp.raise_for_status()
    return resp.json(), resp


def _write_cookies_from_response(client: httpx.AsyncClient, resp: httpx.Response) -> None:
    """从 poll 成功响应中提取并写入 cookie 的兜底处理。

    httpx 会自动处理 Set-Cookie 响应头存入 client.cookies，
    这里额外处理 JSON body 中可能夹带的 token 信息。
    """
    # 从响应 Set-Cookie 中复制 (httpx 会自动写入，这里确保 domain 正确)
    for name, value in resp.cookies.items():
        if not client.cookies.get(name):
            client.cookies.set(name, value, domain=".bilibili.com")

    # 检查 JSON body 中的 token 信息作为兜底
    try:
        body = resp.json()
        data = body.get("data", {})
        if isinstance(data, dict):
            token = data.get("token", "")
            refresh = data.get("refresh_token", "")
            if token and not client.cookies.get("SESSDATA"):
                client.cookies.set("SESSDATA", token, domain=".bilibili.com")
            if refresh and not client.cookies.get("refresh_token"):
                client.cookies.set("refresh_token", refresh, domain=".bilibili.com")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def render_qr_terminal(url: str) -> None:
    """在终端输出二维码 ASCII 图"""
    import qrcode
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii()


async def qrcode_login(client: httpx.AsyncClient) -> LoginResult:
    """完整的二维码登录流程，阻塞直到登录成功或用户中断"""
    attempt = 0
    while True:
        attempt += 1
        qr = await _generate_qrcode(client)
        print(f"\n{'='*50}")
        print(f"  [第 {attempt} 次] 请用 Bilibili App 扫码：")
        print(f"{'='*50}\n")
        render_qr_terminal(qr.url)
        print(f"\n(若二维码未显示，手动打开: {qr.url})\n")

        # 轮询等待扫码
        cookies = None
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            result, resp = await _poll_status(client, qr.qrcode_key)

            code = result["code"]
            msg = result.get("message", "")

            if code == CODE_UNSCANNED:
                print("  ⏳ 等待扫码...", flush=True)
            elif code == CODE_SCANNED:
                print("  📱 已扫码！请在手机上确认登录...", flush=True)
            elif code == CODE_EXPIRED:
                print("  ⌛ 二维码已过期，重新生成...", flush=True)
                break  # 跳出内层循环，重新生成
            elif code == CODE_SUCCESS:
                print("  ✅ 登录成功！", flush=True)
                _write_cookies_from_response(client, resp)
                cookies = result["data"]
                break  # 成功，跳出内层
            else:
                print(f"  ❓ 未知状态: code={code}, msg={msg}", flush=True)

        if cookies:
            return _parse_login_result(client, cookies)


def _parse_login_result(client: httpx.AsyncClient, cookie_data: dict) -> LoginResult:
    """从 scan 响应或 cookie 中提取关键字段"""
    all_cookies = dict(client.cookies.items())
    # poll 成功时 Set-Cookie 已经自动写入 client
    result = LoginResult(
        sessdata=all_cookies.get("SESSDATA", ""),
        bili_jct=all_cookies.get("bili_jct", ""),
        dedeuserid=all_cookies.get("DedeUserID", ""),
        sid=all_cookies.get("sid", ""),
        cookies=all_cookies,
    )
    # 如果 cookie 响应中还包含额外信息
    if isinstance(cookie_data, dict):
        if not result.sessdata:
            result.sessdata = cookie_data.get("sessdata", "")
        if not result.bili_jct:
            result.bili_jct = cookie_data.get("bili_jct", "")
    return result


async def check_login(client: httpx.AsyncClient) -> bool:
    """检查当前 Cookie 是否已登录"""
    resp = await client.get("https://api.bilibili.com/x/web-interface/nav")
    data = resp.json()
    return data.get("code") == 0 and data.get("data", {}).get("isLogin", False)
