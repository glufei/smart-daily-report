# 智能日报生成器

按 **SDD（Specification-Driven Development，规范驱动开发）** 方法构建的团队日报工具。它从 GitHub 提交、飞书任务和飞书群消息收集工作记录，按成员归属生成「代码提交 / 任务进展 / 协作沟通」三段式日报，保存本地历史，并通过 HTML 邮件和飞书群机器人发送。

项目适合小团队在工作日由外部调度器触发生成 CLI；v1.1 已完成 OpenDesign UI 设计迭代、React 浏览器页面和本机只读 HTTP 接口，可按日期查看已保存日报及来源状态。日报不使用 AI 自动撰写摘要。[Web 运行说明](docs/frontend/local-run.md)、[设计证据](docs/frontend/opendesign-evidence.md)、[验收记录](docs/frontend/acceptance.md)。

## v1.2 开发 checkpoint

已实现 React → 真实 FastAPI → GitHub/飞书采集 → SQLite预览，以及单独确认固定版本后SMTP/飞书推送。前端默认仍为只读，操作模式没有 Mock 成功回退。新代码在隔离工作区 `E:\worktrees\v1-2-real-integration\smart-daily-report`，未合并main或推送；2026-10-03已核对非空GitHub2条、飞书完成任务1条，并由用户确认本次邮件与飞书均收到、内容一致、无重复；9/26真实消息采集/过滤/映射通过，但该日是周末，本轮完整自动化回归已通过（pytest260、前端102、浏览器14+26、类型/构建及启动检查）；仍缺工作日消息在页面中的真实验收，版本保留1.1.0。

启动真实操作：在该工作区根目录设置 `PYTHONPATH=src` 并注入本机操作令牌及 YAML 指定的后端凭证，再用本机Python环境执行 `-m smart_daily_report.web.main --config config.yaml`；另一个窗口在该工作区frontend设置 `VITE_API_MODE=operations` 后 `npm run dev`。浏览器输入本项目操作令牌，先生成预览，再单独确认推送。不会自动读取.env；准确命令、旧飞书任务配置迁移、fixture和异常处理见 [完整启动说明](docs/frontend/local-run.md#v12-真实操作模式开发验收待完成)。

[163邮箱与飞书逐步配置](docs/frontend/v1.2-configuration-163-feishu.md) · [本轮验收与未完成项](docs/frontend/v1.2-acceptance.md) · [TDD记录](docs/frontend/v1.2-tdd-log.md) · [上游契约依据](docs/frontend/v1.2-upstream-contracts.md)。此前v1.0收件与v1.1的fixture测试保留为历史证据，不代替v1.2真实验收。

## ✨ 核心工程亮点：规范先于代码

本项目以规范作为第一手工件，代码、测试与验收从规范推导：

| 阶段 | 可审查的交付物 | 作用 |
| --- | --- | --- |
| 需求定义 | [`specs/proposal.md`](specs/proposal.md) | 明确目标、范围、三段式日报、异常边界和量化验收标准。 |
| 架构设计 | [`specs/design.md`](specs/design.md)、[`specs/adrs/`](specs/adrs/) | 定义管道架构、模块职责、HTTP/存储决策和非功能性约束。 |
| 接口契约 | [`specs/contracts/`](specs/contracts/) | 固定数据模型、模块签名及「采集失败 ≠ 成功但无记录」的语义。 |
| 任务拆解 | [`specs/tasks.md`](specs/tasks.md) | 将工作拆成 Task 1–18 的依赖 DAG，每项对应可验证交付物；v1.1 在用户确认规范后执行。 |
| 实现与验证 | [`src/`](src/)、[`tests/`](tests/)、[`frontend/`](frontend/) | 按契约实现模块，用后端回归、前端意图测试及真实 HTTP 浏览器测试验收。 |

**v1.1 质量证据（2026-09-30）：**Task 11–14 已验收，Python **98 项通过、总覆盖率 92.02%**，Vitest **15 项通过**，Playwright **14 项通过**；两版 OpenDesign 原型有 **28 项状态/视口/键盘检查**。`npm ci`、类型检查与生产构建通过。`pyproject.toml` 保持总覆盖率 **≥90%** 的门槛并统计分支覆盖率。命令、截图、首次失败及验证边界见 [验收记录](docs/frontend/acceptance.md)。

**v1.0 历史证据：**2026-09-26 记录为 64 项测试通过、总覆盖率 91.00%；真实端到端运行曾完成 GitHub/飞书采集及两种推送，用户确认收到，总耗时 4.875 秒。非空任务和多页任务响应仍待真实数据复核。v1.1 验收使用虚构数据和临时库，没有连接真实 GitHub/飞书/SMTP 或发送通知。

## 架构概览

```text
GitHub 提交 ────┐
飞书任务 ───────┼─> Collector ─> Shared ─> Generator ─> SQLite 历史
飞书群消息 ─────┘      采集/解析    映射/过滤     Markdown + HTML
                                                   ├─> SMTP：HTML 邮件
                                                   └─> 飞书机器人：Markdown 卡片

浏览器 React 页面 ──GET 指定日期──> FastAPI 只读适配层 ──mode=ro──> SQLite 历史

OpenDesign UI ──两轮原型与设计交接──> React 页面（设计期，无运行时模型调用）
```

- **Collector** 独立访问各数据源，处理分页、超时、限流和飞书 Token 刷新，返回带状态的 `CollectResult`。
- **Shared** 校验配置、判断工作日、按 GitHub/飞书账号映射成员、过滤敏感消息，提供 JSON 日志、HTTP 重试及 SQLite 存储。
- **Generator** 将成员记录渲染成同一份 `DailyReport` 的 Markdown 与 HTML；正常零记录显示「今日无记录」，来源失败显示「数据获取失败」。
- **Notifier** 分别投递邮件和飞书；一个渠道失败仍尝试另一个渠道。根目录 `main.py` 只委托包内编排入口执行。
- **Web 只读模式** 独立启动，只读取启动时指定的历史库，输出白名单 JSON；查询不会调用采集、生成、写入或推送。只读模式接口为 `GET /api/v1/reports/{report_date}`；v1.2操作模式额外提供鉴权生成、状态、预览与独立推送接口。
- **Frontend** 按日期查看日报；区分无日报、正常零记录、来源失败、查询错误，10 秒超时且不自动重试，旧响应不能覆盖新日期。

**设计决策落地：**[ADR-001](specs/adrs/001-http-client.md) 采用可注入、可 Mock 的 `httpx` 客户端，当前程序使用同步 API；[ADR-002](specs/adrs/002-sqlite-storage.md) 采用本地 SQLite，以日报日期为键重复运行时更新当天记录；[ADR-003](specs/adrs/003-collect-result.md) 用 `CollectResult` 区分采集失败与成功空结果。部分来源失败时仍生成可用日报，全部来源失败时不生成、不推送。

## 项目结构

```text
.
├── main.py                         # 命令行启动入口
├── pyproject.toml                  # 依赖、可安装入口及 pytest/覆盖率配置
├── config.yaml.example             # 不含真实密钥的 YAML 配置样例
├── specs/                          # 需求、设计、ADR、契约、任务清单
├── docs/frontend/                  # OpenDesign 证据、设计交接、截图、启动和验收记录
├── frontend/                       # React / TypeScript / Vite、Vitest 与 Playwright
├── src/smart_daily_report/
│   ├── main.py                     # 工作日判断与整条管道编排
│   ├── collector/                  # GitHub 提交、飞书任务与消息采集
│   ├── generator/                  # 成员日报组装、Markdown/HTML 渲染
│   ├── notifier/                   # SMTP 邮件与飞书机器人投递
│   ├── web/                        # 独立只读 HTTP 入口、响应 DTO 和错误映射
│   └── shared/                     # 模型、配置、身份、HTTP、日志、日历、健康检查、存储
└── tests/
    ├── unit/                       # 单模块边界和失败分支
    └── integration/                # Mock 管道集成场景
```

## v1.1 只读页面启动（Windows PowerShell）

需要 Python **≥3.11**、Node **`^22.12.0 || ^24.0.0 || >=26.0.0`**；本轮验证环境为 Python 3.12.14、Node 24.15.0、npm 11.12.1。查看日报不需要安装 OpenDesign，不需要源平台/SMTP 凭证，也不需要加载 `.env`。

### 1. 首次安装

在项目根目录运行（本机路径 `E:\MyCode\smart-daily-report`；其他电脑替换为自己的仓库路径）：

```powershell
Set-Location 'E:\MyCode\smart-daily-report'
py -3.12 -m venv .runtime/venv
.\.runtime\venv\Scripts\python.exe -m pip install -e ".[dev,web]"
Set-Location frontend
npm ci
```

本机已完成安装，可跳过此步骤。迁移前的 `.venv` 指向旧 Python 路径，本轮统一使用 `.runtime/venv`。没有 `py` 时，第一条安装命令改用已安装 Python 的绝对路径；例如 `& 'C:\路径\python.exe' -m venv .runtime/venv`。Python 版本必须符合要求。

### 2. 窗口 A：启动只读 API

```powershell
Set-Location 'E:\MyCode\smart-daily-report'
.\.runtime\venv\Scripts\python.exe -m smart_daily_report.web.main --database '.\data\reports.sqlite3'
```

保持窗口运行。API 监听 `http://127.0.0.1:8000`。数据库应指向生成 CLI 的 `team.database_path`；本机当前历史库中已保存日期为 **2026-04-23**。其他安装环境请查询其已有日期，不会自动获得本机历史数据。

### 3. 窗口 B：启动浏览器页面

```powershell
Set-Location 'E:\MyCode\smart-daily-report\frontend'
npm run dev
```

打开 **[http://127.0.0.1:5173](http://127.0.0.1:5173)**，选择已保存的日期，点击“查看日报”。当前本机实际历史可选择 **2026-04-23**。页面初始不自动查询；API 与页面都运行后才能读取日报。两个窗口均可按 Ctrl+C 停止。

### 4. 使用可复现的虚构示例

新克隆的仓库不包含实际数据库；若要先看页面，在窗口 A 用下列命令替代步骤 2：

```powershell
Set-Location 'E:\MyCode\smart-daily-report'
.\.runtime\venv\Scripts\python.exe frontend/e2e/serve_fixture.py --port 8000
```

复用已有验收 fixture 脚本，在固定 `.runtime/e2e/` 下重建虚构历史并启动 API，不访问实际库或发通知。保持窗口 B 的前端运行，可选择：

| 日期 | 虚构示例状态 |
| --- | --- |
| 2026-09-25 | 正常日报，两位成员，其中一位零记录 |
| 2026-09-26 | 任务来源失败，其他板块正常 |
| 2026-09-27 | 该日期尚无日报 |
| 2026-09-28 | 损坏的历史 JSON，显示查询失败 |
| 2026-09-29 | 长文本及恶意 HTML/协议的安全展示 |
| 2026-09-30 | 已有日报，全部成员零记录 |

实际 API 与示例 API 共用 8000 端口，启动其中一个即可；切换前先在原窗口 Ctrl+C。

### 5. 构建预览及启动排查

在 `frontend` 目录依次执行：

```powershell
npm run typecheck
npm run build
npm run preview
```

打开 **[http://127.0.0.1:4173](http://127.0.0.1:4173)**。API 仍需运行。默认地址是 8000；如其端口被其他应用占用，后端增加 `--port 8001`，前端启动或构建前设置 `$env:VITE_API_BASE_URL='http://127.0.0.1:8001'`。仅填公开的本机 API 地址。

| 现象 | 检查方式 |
| --- | --- |
| 页面提示无法连接日报服务 | 检查窗口 A 是否运行，API 地址/端口是否一致 |
| 该日期尚无日报 | 检查日期和数据库路径；不存在的库不会被自动创建 |
| 日报读取失败 | 检查现有库是否可读、是否具备日报表、是否损坏 |
| 端口占用 | 已启动的本项目服务可继续使用；重启前先 Ctrl+C 停止该窗口 |
| 页面无法打开 | 检查窗口 B，使用 127.0.0.1 的 5173 或预览 4173 地址 |

API 只接受规定的本机 Origin，前端请使用 `127.0.0.1`，不要改成 `localhost`。改了 API 地址后，生产预览必须重新 build。完整说明见 [本机运行文档](docs/frontend/local-run.md)。

## 生成 CLI 启动（Windows PowerShell）

### 1. 安装

要求 **Python 3.11 或更高版本**。在项目根目录运行：

```powershell
py -3.12 -m venv .runtime/venv
.\.runtime\venv\Scripts\python.exe -m pip install -e ".[dev,web]"
Copy-Item config.yaml.example config.yaml
```

若本机只有其他符合要求的 Python 版本，将第一行改为对应的 `py -3.x`。后续命令固定使用虚拟环境中的解释器，避免把依赖安装到另一套 Python。

### 2. 配置数据源和成员

编辑项目根目录的 `config.yaml`：设置 `team.name`、`team.timezone`、`team.github_repositories`、需要启用的 `team.lark_project_ids` / `team.lark_chat_ids`、`team.smtp`，以及 `members` 中的账号映射。邮件收件人必须是 YAML 列表，例如 `recipients: [leader@example.com]`。不用的飞书来源可保留空列表。历史 GitHub 提交若没有 `author.login`，可在相应成员下配置经核实的 `github_author_names`。

`config.yaml` 只保存配置项和**环境变量名**，不能写入 Token、应用密钥、SMTP 授权码或真实 Webhook。此项目不会自动读取 `.env`；如果使用 `.env` 文件，应先将其加载到**当前 PowerShell 进程环境**。在项目根目录自行创建 `.env`，当前完整接入示例需要以下六项：

```dotenv
DAILY_REPORT_GITHUB_TOKEN=替换为GitHub令牌
DAILY_REPORT_LARK_APP_ID=替换为飞书AppID
DAILY_REPORT_LARK_APP_SECRET=替换为飞书AppSecret
DAILY_REPORT_LARK_WEBHOOK=替换为飞书群机器人Webhook
DAILY_REPORT_SMTP_USERNAME=替换为SMTP登录邮箱
DAILY_REPORT_SMTP_PASSWORD=替换为SMTP授权码
```

GitHub 公共仓库可匿名采集，但配置令牌可避免较低的匿名限流；私有仓库需要有读取权限的令牌。只有启用飞书任务或消息采集时才需要飞书 App ID/Secret；只有启用飞书群推送时才需要 Webhook。SMTP 密码通常是邮件服务商提供的授权码。不要上传 `.env`、复制真实密钥到文档或把含密钥的终端输出发给他人；`.env` 和 `config.yaml` 已加入 `.gitignore`。

在**同一个 PowerShell 窗口**执行下列命令，将简单 `KEY=VALUE` 格式的 `.env` 加载进进程；值不加引号，支持值中含 `=`，空行和以 `#` 开头的行会跳过：

```powershell
Get-Content .env | ForEach-Object {
    $entry = $_.Trim()
    if ($entry -and -not $entry.StartsWith('#')) {
        $separator = $entry.IndexOf('=')
        if ($separator -lt 1) { throw 'Invalid .env line: expected KEY=VALUE' }
        [Environment]::SetEnvironmentVariable(
            $entry.Substring(0, $separator).Trim(),
            $entry.Substring($separator + 1),
            'Process'
        )
    }
}
```

关闭该窗口后，这些进程环境变量即失效。若使用 Windows 任务计划程序，须另行配置该任务的安全凭证注入方式；目前项目不会自动定时运行。

### 3. 检查、预览与正式运行

```powershell
.\.runtime\venv\Scripts\python.exe main.py --check
.\.runtime\venv\Scripts\python.exe main.py --dry-run
.\.runtime\venv\Scripts\python.exe main.py
.\.runtime\venv\Scripts\python.exe main.py --date 2026-04-23 --dry-run
```

- `--check` 验证配置及已启用依赖的轻量连通性，不生成、不入库、不发送；SMTP 仅检查连接，不验证登录或邮件送达。
- `--dry-run` 真实采集、生成并写入 `team.database_path` 指定的 SQLite，但**不发送**邮件或飞书消息。
- 正式运行先写入 SQLite，再分别发送邮件和已配置的飞书通知。`--date YYYY-MM-DD` 可指定历史工作日；未指定时使用配置的团队时区的当天日期。周末和配置的节假日会跳过。
- 日志是一行一条 JSON，可按 `run_id` 追踪采集和投递状态；退出码 `0` 表示成功或非工作日跳过，非零表示失败。

### 4. 运行自动化测试

```powershell
.\.runtime\venv\Scripts\python.exe -m pytest -q
```

测试对外部 HTTP API、SMTP 和 Webhook 使用 Mock，不需要真实账户或联网。`pytest` 会同时生成覆盖率报告；项目要求总覆盖率至少 90%。

前端在 `frontend` 目录运行：

```powershell
npm run typecheck
npm run test -- --run
npm run build
npm run test:e2e
```

浏览器验收需要已安装 Google Chrome，默认使用 `.runtime/venv/Scripts/python.exe`；其他解释器可设置 `DAILY_REPORT_PYTHON`。E2E 自动启动 8765/8766 的 fixture API 和 5173 的前端，运行前先停止占用 5173 的开发页面。安装包、环境、node_modules、构建输出、实际配置、凭证及数据库均不提交；虚构原型和验收截图可在仓库查阅。

## 运行边界与安全

- 来源失败与正常零记录分开表示，避免错误地向收件人报告「今日无记录」。飞书消息先按工作关键词筛选，再排除命中敏感词的整条消息；未映射成员只记录计数告警，不把源内容误归给别人。
- 日报中的外部文本在 HTML 中转义，链接仅允许 `http` / `https`。日志不记录 Token、Webhook、SMTP 密码或消息正文。
- SQLite 是本机历史记录，不是备份服务；存储路径、文件访问权限和备份策略由部署环境管理。
- 真实租户的「有任务」已核对1条完成任务；尚无真实多页任务样本，该分页行为目前由离线测试验证。周末和配置假日不生成、不推送；不能用周末消息的采集层证据替代工作日消息的页面验收。

详细需求、接口和验收依据请参阅 [`specs/`](specs/proposal.md)。
