# bw-auto — Agent 指引

Bilibili 会员购抢票（Python 3.11+）：扫码登录、场次票档/购买人选择、可设定脚本启动时间与开售时间、到点下单+间隔重试。入口：`main.py`（CLI）、`web/app.py`（Web UI `bw-auto web`）。核心：`core/`、`api/`、`bot/`。

## Agent skills

以下规则用于**保障基础能力 skill 自动调用**：匹配场景时，必须先 `Read` 对应 `SKILL.md` 并严格执行，**不要**等用户说出 skill 名称，也**不要**只口头提到 skill 却不读取。

Skill 由 Cursor 从用户级目录加载（如 `~/.cursor/skills-cursor/`、`~/.agents/skills/`、`~/.claude/skills/`）；按 **name** 查找即可。

---

### 自动调用（基础功能）

满足任一条件即视为命中，**本轮对话内立即读 skill**：

| Skill | 自动触发条件 |
|-------|----------------|
| **diagnose** | 报错、下单失败、时间同步不准、Cookie/登录异常、性能变慢、测试失败、或用户说「坏了 / debug / 排查」 |
| **web-access** | 需要**搜索**外部资料、打开网页、抓动态页、查会员购/风控文档、或任何不宜只用 `httpx` 直链的联网任务（含登录态页面） |
| **find-skills** | 用户问「怎么做 X」「有没有 skill」「能自动化吗」等，且现有能力不确定时 |
| **tdd** | 新增/修改业务逻辑并应补测试，或用户提到 TDD、红绿重构、集成测试 |
| **improve-codebase-architecture** | 跨模块重构、`core`/`api`/`bot` 边界调整、可测试性/结构讨论，或用户要求「理清架构」 |
| **update-cursor-settings** | 改 Cursor/VS Code 编辑器设置、主题、字体、保存、键位（与本仓库代码无关时） |
| **sdk** | 集成 Cursor SDK、CLI Agent、`@cursor/sdk`、`cursor-sdk`、云 Agent API 等 |

**执行要求：**

1. 命中上表 → **第一条工具调用**读取该 skill（不要先长篇分析再读）。
2. 同一任务可串联多个 skill（例如先 `diagnose` 再 `tdd`）。
3. 禁止「我知道大概怎么做」而跳过 skill；skill 正文优先于通用记忆。

---

### 条件自动（与本项目相关）

| Skill | 触发条件 |
|-------|----------|
| **prototype** | 验证抢票时序、状态机、CLI 交互原型，用户说「先试一版 / 原型」 |
| **split-to-prs** | 改动过大需拆成多个可审查 PR |
| **babysit** | 用户明确要盯 PR、修 CI、处理 review |
| **create-rule** | 为本仓库新增 `.cursor/rules` 或约定 |
| **create-hook** | 为 Agent 事件配置 Cursor hooks |
| **create-skill** | 为本仓库或用户编写新 skill |

---

### 仅用户明确要求时调用

不要自动启用，除非用户点名或使用了对应 slash 命令：

| Skill | 说明 |
|-------|------|
| automate | 仅 **Cursor Automation**（非普通脚本/CI） |
| loop | `/loop` 定时重复 |
| canvas | 本仓库为 CLI，**默认不用**；仅当要做图表/可视化交付物时 |
| ui-ux-pro-max | 本仓库无 Web UI，**默认不用**；仅当新增前端/界面时 |
| caveman | 用户要求极简回复 |
| grill-me / grill-with-docs | 用户要压测方案或对照文档评审 |
| handoff | 用户要会话交接文档 |
| to-prd / to-issues / triage | 用户要 PRD、拆 issue、分流（见下方 Issue tracker） |
| write-a-skill | 用户要写新 skill |
| statusline | CLI 状态栏定制 |

---

### Issue tracker

Issues 在 **GitHub**：`https://github.com/Squirtleeeee/bw-auto`。创建/查询 issue 用 `gh` CLI。

| 分流角色 | 建议标签 |
|----------|----------|
| needs-triage | `needs-triage` |
| needs-info | `needs-info` |
| ready-for-agent | `ready-for-agent` |
| ready-for-human | `ready-for-human` |
| wontfix | `wontfix` |

使用 `triage` / `to-issues` / `to-prd` 前，若标签与上表不一致，以仓库实际标签为准。

---

### Domain docs

- **布局**：单上下文；领域说明以 `readme.md` 与 `src/bw_auto/core/models.py` 为准。
- 无 `CONTEXT.md` / `docs/adr/` 时**不要**强求创建；需要架构决策时再补。
- 涉及 B 站会员购 API、下单字段、时间同步时，以 `readme.md`「技术要点」和 `api/show_api.py` 为权威。

---

### 代码与协作约定

- 改动范围尽量小；风格对齐现有 `src/bw_auto/`。
- **不要**提交 `.cookies.json`、`.env` 或含密钥文件。
- 仅当用户明确要求时才 `git commit` / `git push` / 开 PR。
- 终端命令在 Windows PowerShell 下注意：避免 bash 专用语法（如 `&&`），用 `;` 或分行。
