# 本地日报页面与 API

当前代码版本为 v1.7.0（尚未发布 Release）。网页和新生成邮件将报告生成时间显示为中国标准时间（Asia/Shanghai，UTC+08:00）；汇总版不展示提交、任务或消息的逐条时间，原始时间点仍保存在本机数据中。邮件主题按年级、姓名、报告日期和日报名称组成。[汇总版变更与验证](summary-only-report.md)对应当前行为，[2026-10-20 验证记录](../project-verification-2026-10-20.md)及[2026-10-14 审查记录](../project-audit-2026-10-14.md)是旧版历史证据。本页说明只读启动、真实操作和 fixture；首次运行优先按照 [README](../../README.md) 的双窗口步骤。全部请求状态由确定性代码处理；页面不调用模型。真实凭证、配置和日报数据库只保存在本地，不要提交到公开仓库。本机 API 仍返回原始记录，不能向不应接触原始数据的人开放。

## Python 安装与启动（Windows PowerShell）

需要 Python ≥3.11；Web 可选依赖固定为 FastAPI 0.142.2、Uvicorn 0.54.0，本轮在 Python 3.12.14 验证。

```powershell
py -3.12 -m venv .runtime/venv
.\.runtime\venv\Scripts\python.exe -m pip install --upgrade 'pip>=26.2'
.\.runtime\venv\Scripts\python.exe -m pip install -e ".[dev,web]"
.\.runtime\venv\Scripts\daily-report-web.exe --database ".\data\reports.sqlite3"
```

只读 API 默认以 UTC 偏移返回时间；网页会统一换算为中国标准时间。其他 API 客户端若需要不同的响应偏移，可在上述命令末尾添加 `--timezone 'Asia/Shanghai'`；该选项不修改数据库时间，也不改变网页显示。`--config` 操作模式不接受此参数，API 响应偏移使用 `team.timezone` 配置。

网页的报告生成时间仍显示原始 `...Z` 或 `UTC+00:00` 时，先停止旧的前端服务并从当前项目重启、刷新页面；操作模式同时确认后端以 `--config` 启动。已保存时间仍以 UTC 存储，网页固定按中国标准时间展示；例如 `12:36 UTC` 显示为 `20:36（中国标准时间，UTC+08:00）`。修正页面时间显示无需重新生成；旧版通知内容要改为汇总版则需重新生成。

将数据库参数替换为实际已生成日报的 SQLite 路径（与生成 CLI 使用的 `team.database_path` 指向同一文件）。相对路径按启动时工作目录解析。查询服务不会读取 `.env` 或配置、不会连接 GitHub/飞书/SMTP，也不会创建缺失的数据库。

首次克隆不会包含本地数据库；需要虚构示例时复用验收脚本启动：

```powershell
.\.runtime\venv\Scripts\python.exe frontend/e2e/serve_fixture.py --port 8000
```

该脚本只重建固定 `.runtime/e2e/history.sqlite3`，不访问生产库；示例日期 2026-09-25 为正常日报、26 为任务来源失败、27 无日报、28 数据格式错误、29 长文本安全展示、30 正常零记录。实际 API 与该示例服务二选一占用 8000，切换前 Ctrl+C 停止原服务。

默认监听 `127.0.0.1:8000`；端口冲突可使用 `--port 8001`。只读查询示例：

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/reports/YYYY-MM-DD'
```

正常有日报返回结构化 JSON。`generated_at` 按选定展示区序列化为含偏移的 ISO 8601；缺省 `UTC`。日期非法为 400，无已保存日报为 404，已有库缺表/损坏/读取错误为 500；来源部分失败的历史日报仍为 HTTP 200，并携带对应 `failure` 状态。以上 --database 模式不提供生成或推送操作。

如果没有 `py`，可使用已安装的符合版本要求的 Python 绝对路径执行第一行。

## 测试

```powershell
.\.runtime\venv\Scripts\python.exe -m pytest -q
```

完整测试需要安装 `dev,web` 两组依赖。不安装 `web` 的基础 CLI 仍可使用，测试包不会自动跳过 Web 测试。对应版本的测试结果见版本说明。Starlette 对 httpx TestClient 有一项上游弃用提示，当前契约测试可用。

## React 页面（第二个 PowerShell 窗口）

Node `^22.12.0 || ^24.0.0 || >=26.0.0`；本轮 Node 24.15.0、npm 11.12.1。运行：

```powershell
cd frontend
npm ci
$env:VITE_API_MODE = 'readonly'
npm run dev
```

打开 `http://127.0.0.1:5173`，选择数据库中已保存的报告日期，再点击“查看日报”。默认 API 为 `http://127.0.0.1:8000`。若 API 使用另一端口，启动 Vite 前在同一窗口设置 `$env:VITE_API_BASE_URL='http://127.0.0.1:8001'`。此变量仅是公开的本机 HTTP 地址，不能写数据库路径或凭证。Origin 固定使用 127.0.0.1，勿改成 localhost 或监听外网。

构建及预览：

```powershell
npm run typecheck
npm run build
npm run preview
```

预览在 `http://127.0.0.1:4173`。构建时固定 API 地址和页面模式；改变它们后需要重新 build。只读模式初始不自动查询，缺失日期为“该日期尚无日报”，不提供生成或推送；真实操作模式见下文。API 和 Vite 终端均可 Ctrl+C 结束。测试期间留下的临时示例预览使用 `.runtime/api-smoke.sqlite3`、2026-09-25，只包含虚构数据；查看实际历史需自行用实际 SQLite 路径启动 API。

前端测试（frontend 目录）：

```powershell
npm run test -- --run
npm run test:e2e
```

Playwright 使用已安装的 Google Chrome；需要 Python 环境安装 `dev,web`，默认 `.runtime/venv/Scripts/python.exe`。其他 Python 路径可通过 `DAILY_REPORT_PYTHON` 指定。E2E 自动启动 8765/8766 两个 fixture API 及 5173 Vite，测试前需释放这些端口；不复用其他正在运行的服务。临时库仅位于 `.runtime/e2e/`，不会访问实际日报配置/数据库或发送通知。测试每次只重建自身固定的 fixture 文件。

以下为历史验收：v1.2.0 发布及最终复核包含 102 项 Vitest、只读 14 项和操作 26 项 Playwright，两种视口均无页面级横向溢出。v1.1 的历史结果为 15 项 Vitest；首次 E2E 在受限进程环境中断言通过但服务清理未结束，Ctrl+C 后退出 1，重跑 14 passed、退出 0。v1.7.0 的本次测试数量与范围见[2026-10-23 验证记录](../project-verification-2026-10-23.md)，不要把这些历史数字当作当前结果。Playwright 有 NO_COLOR/FORCE_COLOR 的环境提示，不据此声称没有警告。浏览器测试会重新生成部分被 Git 跟踪的截图；只做复核时，请在提交前恢复这些截图。

## 锁定依赖与开源复用

React 19.3.0、React DOM 19.3.0、Vite 8.3.1、TypeScript 7.0.2、Zod 4.6.5；Vitest 5.0.3、Testing Library React 16.3.3、Playwright 1.63.0。`package-lock.json` 与 `npm ci` 验证通过，不添加路由、组件库或状态管理框架。通用校验使用 [Zod（MIT）](https://github.com/colinhacks/zod)，用户意图测试使用 [Testing Library](https://github.com/testing-library/react-testing-library)，浏览器验收复用 [Playwright（Apache-2.0）](https://github.com/microsoft/playwright)；Node 依据 [Vite 官方要求](https://vite.dev/guide/)及 npm engines 核验。

## OpenDesign 工具状态

官方来源：https://github.com/nexu-io/open-design/releases/tag/open-design-v0.24.1 。安装文件 SHA256：`3a544dca7a5f078029d55f272e218278e52edac55efbfb292d56258113e8a441`，与 GitHub 发行资产 digest 一致。

软件安装在 `.tools/OpenDesign/`，与 `.runtime/` 一同被 Git 忽略。初版、第二版、实际输入、截图和可见修改已保存于 `docs/frontend/prototypes/`；详见 `opendesign-evidence.md`。产品不需要 OpenDesign 运行。已公开并修复原型手机异常留白，见 `DESIGN.md` 的交接差异。


## v1.2 真实操作模式

默认仍为只读；操作模式必须成对启动：后端 `--config`，前端 `VITE_API_MODE=operations`。产品不导入 fixture，不会用预制成功数据替代失败响应。以下命令从项目根目录运行；真实配置与凭证应保存在 Git 忽略的本地文件中。

详细填写步骤见 [163邮箱、GitHub与飞书配置指南](v1.2-configuration-163-feishu.md)。

### 窗口 A：配置与真实后端

在工作区放置被忽略的 config.yaml，按 config.yaml.example 设置真实来源、成员映射、固定目标及凭证环境变量名。现有配置中旧 `lark_task_search_path: /task/v2/tasks/search` 必须迁为 `/task/v2/tasklists/{tasklist_guid}/tasks`；`lark_project_ids` 填已授权 tasklist GUID。任务按 completed_at 和团队时区展示所选日期完成的记录，不代表任意历史状态变更。

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
# 将自己保管的 .env 加载到此窗口的进程环境；加载方法见 README。
.\.runtime\venv\Scripts\python.exe -m smart_daily_report.web.main --config '.\config.yaml'
```

必须注入 `DAILY_REPORT_WEB_TOKEN`（至少32字符、非空白的本项目操作令牌）；按配置注入 `DAILY_REPORT_GITHUB_TOKEN`、`DAILY_REPORT_LARK_APP_ID`、`DAILY_REPORT_LARK_APP_SECRET`、`DAILY_REPORT_LARK_WEBHOOK`、`DAILY_REPORT_SMTP_USERNAME`、`DAILY_REPORT_SMTP_PASSWORD`。实际变量名以 YAML 的 *_env 值为准；不要把值写入命令示例、浏览器 URL 或 VITE_*。程序不自动读取 .env。操作令牌必须通过自己安全保管的环境文件/进程注入，刷新页面后需重新输入。

GitHub公共库可匿名但有限流；私有库需授予当前 PAT 对目标仓库的读取权限。若使用 fine-grained PAT，只授予所需仓库的 `Contents: Read-only`（Metadata 默认只读）；如组织要求审批，需完成管理员批准。Token 只保存在本地 `.env`，不要发布到聊天或仓库；更新 `.env` 后重新加载环境变量并重启服务。GitHub 返回404时先核对仓库路径及 Token 对私有仓库的可见权限，不要将其当成“零条提交”。[GitHub List commits 权限说明](https://docs.github.com/en/rest/commits/commits)。

飞书应用须获租户授权、可读目标清单及群消息，机器人须在固定目标群中可用；权限步骤见 [飞书清单权限说明](feishu-tasklist-permissions.md)。无需发送邮件时可省略或清空 SMTP 配置；配置 SMTP 时，服务器、发件人、收件人及端口必须有效。数据库路径相对于启动工作目录，操作库位于同目录 `<日报库文件名>.operations.sqlite3`；不要删除操作库来解除重发限制。

### 窗口 B：React 操作页面

```powershell
Set-Location 'frontend'
$env:VITE_API_MODE = 'operations'
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000'
npm run dev
```

打开 http://127.0.0.1:5173，选择任意有效日期（包括周末及配置节假日），输入本项目操作令牌并点“验证令牌”。空值或全空格点击验证时仅给本地提示并聚焦，不发请求；未验证时“采集并生成”禁用并显示原因。点击“采集并生成”只采集、保存、预览；“查看日报”仅查询历史，“预览日报”取得可确认版本和服务器配置的可选邮箱，并在成功后定位正文。核对来源、日期、内容后选渠道；选择邮件时必须明确勾选至少一位邮箱，默认全部未选。点击“推送日报”，在弹窗中核对日期、版本、具体地址和飞书目标后再确认；取消不会发送。只给导师发送就只勾选导师邮箱，不选自己的邮箱；不需要飞书则取消该渠道。

邮件主题按“年级 + 姓名 + 报告日期 + 日报名称”组成；邮件正文显示本次生成时间。每次发送前都应核对内容和收件人。

### 日报内容格式

网页预览、邮件和飞书日报显示每位成员的“今日概览”：代码提交、已完成任务和协作沟通的数量，以及已获取记录合计、有记录类别和来源状态。网页、邮件还展示三类记录的数量对比条；它只比较记录条数，不代表工作量或成果质量。不列出提交标题、链接、任务名称、消息正文或逐条时间。来源成功但没有该成员记录时显示“0 条”；来源采集失败时显示“获取失败，数量未知”，不计入合计。数量只根据已采集、已过滤的结构化记录确定性计算，不使用 AI 改写。原始记录仍在本机 SQLite 和本机 API 中，网页仅隐藏显示，不等于删除数据或阻止浏览器网络工具查看响应。

“有记录类别”统计的是三类中数量大于 0 的类别数，不是项目数。例如代码提交 3 条、已完成任务和协作沟通各 0 条时，合计 3 条、有记录类别 1 项。

历史日报保留生成时的 Markdown/HTML 原文。旧版含明细的快照不能直接发送：请使用当前代码对指定日期重新「采集并生成」，核对汇总版预览后再独立确认推送；只读「查看日报」不会更新快照。重新生成会替换该日期本机快照，但不会撤回已发通知。

HTTP 202 只表示操作请求已受理。页面每2秒查询、最多观察120秒，停止观察或关页不会取消后端；刷新后重新验证令牌、查询执行结果，不要新建请求猜测重发。丢响应先查询原幂等键；只有查明原键不存在才提供显式同键重试。accepted仅表示服务商受理；须另核对邮件收件箱和飞书群实际内容。邮件可经新请求、独立确认再次发送同一版本，可能产生重复邮件；部分受理或 unknown 时先核实实际收件，系统不会自动重发。飞书同版本已受理/部分受理/unknown 继续禁止重发，明确 rejected 可单独重提。重新生成会改变日报版本，旧确认被拒绝后需重新预览。

两个窗口按 Ctrl+C 停止。单 Uvicorn worker、无 reload；生产Origin仅127.0.0.1:5173/4173，不要暴露到局域网。生产预览在同模式/公开API地址下 `npm run build`、`npm run preview`；Vite环境变量在构建时确定，切模式需重新构建。回到只读启动时先 `Remove-Item Env:VITE_API_MODE -ErrorAction SilentlyContinue`，并使用后端 --database。

### 操作模式可复现 fixture（不访问真实平台）

```powershell
# 窗口 A，在隔离工作区根目录
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
.\.runtime\venv\Scripts\python.exe frontend/e2e/serve_operations_fixture.py --port 8775
# 窗口 B，在该工作区 frontend
$env:VITE_API_MODE = 'operations'
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8775'
npm run dev -- --port 5174
```

打开 http://127.0.0.1:5174，使用 fixture 提供的测试日期和测试令牌。这是专用测试服务：真实 FastAPI/SQLite/Collector/Notifier，只有 HTTP/SMTP 外部边界使用替身；不会发送真实通知。固定目录 `.runtime/e2e-operations` 的测试文件会重建，绝不指向真实配置/数据库。5174 Origin仅测试工厂注入，不加入产品白名单。

自动回归（frontend）：

```powershell
$env:PYTHONPATH = Join-Path (Split-Path (Get-Location) -Parent) 'src'
$env:DAILY_REPORT_PYTHON = (Resolve-Path '..\.runtime\venv\Scripts\python.exe').Path
# 5173被自己需要保留的服务占用时，可使用产品已允许的4173
$env:DAILY_REPORT_E2E_PORT = '4173'
$env:DAILY_REPORT_E2E_SCREENSHOT_DIR = '../.runtime/audit-screenshots/readonly'
npm run test:e2e
$env:DAILY_REPORT_E2E_SCREENSHOT_DIR = '../.runtime/audit-screenshots/operations'
npx playwright test --config playwright.operations.config.ts
npm run test -- --run --coverage
npm run typecheck
npm run build
```

先释放测试用5173/5174/8765/8766/8775端口。测试使用已安装Chrome；报告见 v1.2-acceptance.md。运行截图中的令牌/来源为公开假值，不能当真实平台或实际收件证据。

## 操作要点

- 「查询执行结果」提供加载/完成/无记录/错误提示，同时展示服务器更新时间与本次查询时间；「预览日报」完成后定位正文标题。主动 GET 超过10秒提示超时，后台任务仍继续。
- 邮箱列表只在操作令牌验证后的预览接口返回；初始全部未选，选择邮件且地址为空时按钮禁用并说明原因。默认仅从 config.yaml 的 smtp.recipients 选择，不能在页面添加任意地址。
- 确认弹窗展示所选具体邮箱；新执行结果记录此次地址。旧历史记录没有该字段时明确“历史记录未记录具体收件人”，不推断旧配置。
- 邮件新请求可以再次发送同版本，可能重复；同一请求仍去重。网络异常先查原键，只有未找到才提供保留原地址的显式重试；禁止自动重发。飞书原阻断规则保持。
- accepted 是服务商受理，不是实际送达。Gmail 收件箱无邮件时检查垃圾邮件及全部邮件；对确认可信的发件人标记“不是垃圾邮件”或建立过滤器，见 README 的发送步骤。
- 前后端新契约必须配套：邮件 POST 必须提供非空 email_recipients；旧页面缺字段将返回400，不会退回给所有人发送。重启后端并从本轮目录启动前端才能使用改进。
