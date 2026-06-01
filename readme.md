# bw-auto — Bilibili 会员购抢票脚本

从零上手的 B 站会员购抢票工具。扫码登录 → 交互式选择场次票档 → 到点毫秒级自动下单 → 提示去 App 支付。

## 环境要求

| 工具 | 最低版本 | 检查方式 |
|------|----------|----------|
| Python | 3.11+ | `python --version` |
| pip | 23.0+ | `pip --version` |
| Bilibili App | 任意 | 扫码登录用 |
| 终端 | 支持 UTF-8 | Windows Terminal / PowerShell |

## 安装

```bash
# 1. 进入项目目录
cd bw-auto

# 2. 安装依赖 + 注册 bw-auto 命令
pip install -e .

# 3. 验证安装
bw-auto --help
```

## 使用方法

### 第一步：扫码登录（首次或 Cookie 过期时）

```bash
bw-auto login
```

终端会显示二维码，用 Bilibili App 扫码即可。登录成功后 Cookie 保存在 `.cookies.json`，下次不用重新登录。

### 第二步：查看商品信息

```bash
bw-auto info --id <项目ID>
```

示例：
```bash
bw-auto info --id 1000322
```

输出会显示场次列表和每个场次的票档（名称、价格、库存）。

> **如何获取项目 ID？** 在 Bilibili 会员购网页版打开商品详情页，URL 中 `id=` 后面的数字即是：
> `https://show.bilibili.com/platform/detail.html?id=1000322`
> 这里的 `1000322` 就是项目 ID。

### 第三步：抢票

```bash
bw-auto grab --id <项目ID>
```

脚本会依次让你选择：
1. **场次** — 哪个日期/时间段的票
2. **票档** — 哪个价格档位
3. **购买人** — 从 B 站已保存的购买人中选择
4. **确认** — 确认所有选择后开始倒计时
5. **自动下单** — 到开售瞬间自动发送下单请求

```
bw-auto grab --id 1000322

>>> 加载商品 1000322 ...
  上海·某漫展

可选场次:
  [1] 6月14日  开售: 2026-04-24 20:00:00
  选择场次编号: 1

可选票档:
  [1] 单人预售票  ￥98  库存:100
  [2] 双人预售票  ￥178 库存:50
  选择票档编号: 1

选择购买人:
  [1] 张三  138****1234
  选择购买人编号: 1

--- 订单确认 ---
  商品: 上海·某漫展
  场次: 6月14日
  票档: 单人预售票  x1  ￥98
  购买人: 张三  138****1234
  确认并开始等待抢票? [y/N]: y

  [开售时间] 2026-04-24 20:00:00
  [等待时长] 3600.0 秒
  进入等待...

  --- 时间到 ---
  [下单] 发送请求...
  [成功] order_id=123456789

========================================
  下单成功！
  订单号: 123456789
  请尽快在 Bilibili App 中完成支付
  未支付订单将在 5-15 分钟后自动取消
========================================
```

## 命令参考

| 命令 | 说明 | 参数 |
|------|------|------|
| `bw-auto login` | 扫码登录 | 无 |
| `bw-auto status` | 检查登录状态 | 无 |
| `bw-auto info --id ID` | 查看商品详情 | `--id` 商品 project_id |
| `bw-auto grab --id ID` | 交互式抢票 | `--id` 商品ID, `--num` 数量(默认1), `--time` 手动指定开售时间, `--pre-fire` 提前发送毫秒数(默认200) |

### 高级参数

```bash
# 手动指定开售时间（不从商品数据读取）
bw-auto grab --id 1000322 --time "2026-06-15 12:00:00"

# 调整提前发送量（越大越早发请求，默认 200ms）
bw-auto grab --id 1000322 --pre-fire 300

# 多张票
bw-auto grab --id 1000322 --num 2
```

## 文件说明

```
bw-auto/
├── readme.md              # 本文件
├── pyproject.toml         # Python 项目配置
├── .env.example           # 环境变量模板
├── .cookies.json          # 登录 Cookie (自动生成，勿提交)
│
└── src/bw_auto/
    ├── main.py            # CLI 入口 — login / info / grab / status
    ├── auth/
    │   ├── qrcode.py      # 二维码生成 + 轮询扫码状态
    │   └── session.py     # Cookie 序列化/反序列化
    ├── api/
    │   ├── client.py      # HTTP 客户端封装 (UA/Cookie/重试)
    │   └── show_api.py    # 会员购 API (商品详情/购买人列表/下单)
    ├── core/
    │   ├── models.py      # 数据模型
    │   ├── item.py        # 商品信息解析
    │   ├── order.py       # 下单请求构造
    │   └── scheduler.py   # 毫秒级精确定时器
    ├── bot/
    │   └── engine.py      # 抢票状态机编排
    └── utils/
        ├── time_sync.py   # 与 B 站服务器时间对齐
        └── terminal.py    # rich 终端美化
```

## 技术要点

### 下单 API

基于 confirmOrder JS 逆向，当前使用 `createV2` 端点：

```
POST https://show.bilibili.com/api/ticket/order/createV2?project_id={id}
Content-Type: application/json

{
    "project_id": "...",
    "screen_id": "...",
    "sku_id": "...",        # 实际字段名仍为 sku_id
    "count": 1,
    "pay_money": 9800,      # 单位：分（98元 = 9800分）
    "order_type": 1,
    "timestamp": 1700000000,
    "buyer_info": {
        "name": "...",
        "tel": "...",
        "id_card_type": 0,
        "id_card_no": "..."
    },
    "deliver_info": {"deliver_type": 0},
    "token": "",
    "newRisk": true,
    "requestSource": "pc-new"
}
```

### 抢票时序

```
开售时间 T
  │
  ├── T-3000ms  时间同步（对齐 B 站服务器时钟）
  ├── T-500ms   准备请求体
  ├── T-200ms   busy-wait 自旋等待（毫秒级精度）
  └── T          发送 POST 请求
```

### 数据模型

Bilibili 会员购的商品结构：

```
商品 (Project)
├── 场次 (Screen) — 不同日期/时间段
│   ├── 票档 (Ticket/SKU) — 不同价格档位
│   ├── 票档 (Ticket/SKU)
│   └── ...
├── 场次 (Screen)
│   └── ...
└── ...
```

## 常见问题

**Q: 登录时二维码没显示？**
A: 终端需要支持 UTF-8。用 Windows Terminal / PowerShell 打开，不要用 cmd。

**Q: `bw-auto` 命令找不到？**
A: 确保执行了 `pip install -e .`，且 Python Scripts 目录在 PATH 里。

**Q: Cookie 过期？**
A: 重新执行 `bw-auto login` 即可，Cookie 通常有效期约 30 天。

**Q: 下单失败？**
A: 常见原因：已售罄、限购、未实名、风控拦截。查看错误信息判断。

**Q: 脚本安全吗？**
A: Cookie 保存在本地 `.cookies.json`，不上传任何服务器。脚本只调 B 站官方 API，不注入/篡改页面。

**Q: 会被封号吗？**
A: 本脚本模拟正常浏览器请求，不做高频轮询。但任何自动化工具理论上都有风险，自行评估。

## License

MIT
