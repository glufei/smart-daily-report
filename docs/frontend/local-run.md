# 本机日报页面与 API

当前版本 v1.3.1，Task 11–23 开发、维护和回归完成，发布记录见 [v1.3.1版本说明](v1.3.1-release.md)。本页前半部分说明只读启动，后半部分说明真实操作和 fixture；操作反馈与邮箱选择改进及本机代码/配置目录分离启动方法见 [本轮验收说明](operation-feedback-email-selection-acceptance.md) 和 README 第一节；原 v1.2.0、v1.3.0 记录作为发布基线。首次运行优先按照 [README](../../README.md) 的双窗口步骤。全部请求状态由确定性代码处理；页面不调用模型。最新复核及验证边界见 [v1.3.1维护验证记录](v1.3.1-maintenance-tdd.md)；[v1.2最终交付说明](v1.2-final-handover.md)保留历史证据。

## Python 安装与启动（Windows PowerShell）

需要 Python ≥3.11；Web 可选依赖固定为 FastAPI 0.142.2、Uvicorn 0.54.0，本轮在 Python 3.12.14 验证。

```powershell
py -3.12 -m venv .runtime/venv
.\.runtime\venv\Scripts\python.exe -m pip install -e ".[dev,web]"
.\.runtime\venv\Scripts\daily-report-web.exe --database "E:\MyCode\smart-daily-report\data\reports.sqlite3"
```

将数据库参数替换为实际已生成日报的 SQLite 路径（与生成 CLI 使用的 `team.database_path` 指向同一文件）。相对路径按启动时工作目录解析。查询服务不会读取 `.env` 或配置、不会连接 GitHub/飞书/SMTP，也不会创建缺失的数据库。

本机已核对的历史日期为 **2026-04-23**（只查询日期列）；首次克隆不会包含此数据库。可直接用当前 `.runtime/venv` 启动，无需重新安装。需要虚构示例时复用验收脚本启动：

```powershell
.\.runtime\venv\Scripts\python.exe frontend/e2e/serve_fixture.py --port 8000
```

该脚本只重建固定 `.runtime/e2e/history.sqlite3`，不访问生产库；示例日期 2026-09-25 为正常日报、26 为任务来源失败、27 无日报、28 数据格式错误、29 长文本安全展示、30 正常零记录。实际 API 与该示例服务二选一占用 8000，切换前 Ctrl+C 停止原服务。

默认监听 `127.0.0.1:8000`；端口冲突可使用 `--port 8001`。只读查询示例：

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/reports/2026-04-23'
```

正常有日报返回结构化 JSON。日期非法为 400，无已保存日报为 404，已有库缺表/损坏/读取错误为 500；来源部分失败的历史日报仍为 HTTP 200，并携带对应 `failure` 状态。以上 --database 模式不提供生成或推送操作。

迁移后的原 `.venv` 指向旧的 Python 安装位置，不能运行；本轮保留它，另建 `.runtime/venv`。本机如果没有 `py`，可使用已安装的符合版本要求的 Python 绝对路径执行第一行。本轮实际使用 Codex 提供的 Python 3.12.14 创建此隔离环境。

## 测试

```powershell
.\.runtime\venv\Scripts\python.exe -m pytest -q
```

完整测试需要安装 `dev,web` 两组依赖。不安装 `web` 的基础 CLI 仍可使用，测试包不会自动跳过 Web 测试。v1.2.0 发布时为 286 项通过、覆盖率 95.03%；2026-10-05 最终复核修复健康检查后为 300 项通过、覆盖率 95.28%，无跳过。Starlette 对 httpx TestClient 有一项上游弃用提示，当前契约测试可用；未为消除提示替换项目既有 httpx 客户端。

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

v1.2.0 发布及最终复核：102 项 Vitest、只读 14 项和操作 26 项 Playwright 通过，两种视口均无页面级横向溢出。v1.1 的历史结果为 15 项 Vitest；首次 E2E 在受限进程环境中断言通过但服务清理未结束，Ctrl+C 后退出 1，重跑 14 passed、退出 0。最新环境污染复现、修复和退出结果见最终交付说明。Playwright 有 NO_COLOR/FORCE_COLOR 的环境提示，不据此声称没有警告。

## 锁定依赖与开源复用

React 19.3.0、React DOM 19.3.0、Vite 8.3.1、TypeScript 7.0.2、Zod 4.6.5；Vitest 5.0.3、Testing Library React 16.3.3、Playwright 1.63.0。`package-lock.json` 与 `npm ci` 验证通过，不添加路由、组件库或状态管理框架。通用校验使用 [Zod（MIT）](https://github.com/colinhacks/zod)，用户意图测试使用 [Testing Library](https://github.com/testing-library/react-testing-library)，浏览器验收复用 [Playwright（Apache-2.0）](https://github.com/microsoft/playwright)；Node 依据 [Vite 官方要求](https://vite.dev/guide/)及 npm engines 核验。

## OpenDesign 工具状态

官方来源：https://github.com/nexu-io/open-design/releases/tag/open-design-v0.24.1 。安装文件 SHA256：`3a544dca7a5f078029d55f272e218278e52edac55efbfb292d56258113e8a441`，与 GitHub 发行资产 digest 一致。

软件安装在 `.tools/OpenDesign/`，与 `.runtime/` 一同被 Git 忽略。初版、第二版、实际输入、截图和可见修改已保存于 `docs/frontend/prototypes/`；详见 `opendesign-evidence.md`。产品不需要 OpenDesign 运行。已公开并修复原型手机异常留白，见 `DESIGN.md` 的交接差异。


## v1.2 真实操作模式

Task15–17已实现。默认仍为只读；操作模式必须成对启动：后端 `--config`，前端 `VITE_API_MODE=operations`。产品不导入 fixture，不会用预制成功数据替代失败响应。本机已验收配置和历史库保留在隔离工作区 `E:\worktrees\v1-2-real-integration\smart-daily-report`；本机 Python 依赖环境复用 `E:\MyCode\smart-daily-report\.runtime\venv`，因此以下工作区命令明确设置 PYTHONPATH，明确选择工作区代码而非其他已安装副本。

详细填写步骤见 [163邮箱、GitHub与飞书配置指南](v1.2-configuration-163-feishu.md)。

### 窗口 A：配置与真实后端

在工作区放置被忽略的 config.yaml，按 config.yaml.example 设置真实来源、成员映射、固定目标及凭证环境变量名。现有配置中旧 `lark_task_search_path: /task/v2/tasks/search` 必须迁为 `/task/v2/tasklists/{tasklist_guid}/tasks`；`lark_project_ids` 填已授权 tasklist GUID。任务按 completed_at 和团队时区展示所选日期完成的记录，不代表任意历史状态变更。

```powershell
Set-Location 'E:\worktrees\v1-2-real-integration\smart-daily-report'
$env:PYTHONPATH = 'E:\MyCode\smart-daily-report\src'
# 将自己保管的 .env 加载到此窗口的进程环境；加载方法见 README。
& 'E:\MyCode\smart-daily-report\.runtime\venv\Scripts\python.exe' -m smart_daily_report.web.main --config '.\config.yaml'
```

必须注入 `DAILY_REPORT_WEB_TOKEN`（至少32字符、非空白的本项目操作令牌）；按配置注入 `DAILY_REPORT_GITHUB_TOKEN`、`DAILY_REPORT_LARK_APP_ID`、`DAILY_REPORT_LARK_APP_SECRET`、`DAILY_REPORT_LARK_WEBHOOK`、`DAILY_REPORT_SMTP_USERNAME`、`DAILY_REPORT_SMTP_PASSWORD`。实际变量名以 YAML 的 *_env 值为准；不要把值写入命令示例、浏览器 URL 或 VITE_*。程序不自动读取 .env。操作令牌必须通过自己安全保管的环境文件/进程注入，刷新页面后需重新输入。

GitHub公共库可匿名但有限流；私有库需读取权限。飞书应用须获租户授权、可读目标清单及群消息，机器人须在固定目标群中可用。真实任务接口已确认要求 task:tasklist:read（或 write，本项目只需 read）；读取scope已在真实请求生效；原清单配置误用任务GUID已修正，用户已添加应用为viewer协作者；真实tenant身份清单详情/任务GET200/code0，并生成2026-10-01含1条已完成任务的日报，见 [具体权限步骤及清单链接](feishu-tasklist-permissions.md)。无需发送邮件时可省略/清空 smtp；配置了 smtp 时 host/sender/非空 recipients、1–65535端口和布尔互斥TLS必填；声明登录环境变量时用户名和密码必须成对存在且非空白，不静默转为匿名连接。数据库路径相对于启动工作目录，操作库位于同目录 `<日报库文件名>.operations.sqlite3`；不要删除操作库来“解除重发限制”。

### 窗口 B：React 操作页面

```powershell
Set-Location 'E:\MyCode\smart-daily-report\frontend'
$env:VITE_API_MODE = 'operations'
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000'
npm run dev
```

打开 http://127.0.0.1:5173，选择有源数据的工作日，输入本项目操作令牌并点“验证令牌”。空值或全空格点击验证时仅给本地提示并聚焦，不发请求；未验证时“采集并生成”禁用并显示原因。点击“采集并生成”只采集、保存、预览；“查看日报”仅查询历史，“预览日报”取得可确认版本和服务器配置的可选邮箱，并在成功后定位正文。核对来源、日期、内容后选渠道；选择邮件时必须明确勾选至少一位邮箱，默认全部未选。点击“推送日报”，在弹窗中核对日期、版本、具体地址和飞书目标后再确认；取消不会发送。只给导师发送就只勾选导师邮箱，不选自己的邮箱；不需要飞书则取消该渠道。

202只是接受操作。页面每2秒查询、最多观察120秒，停止观察或关页不会取消后端；刷新后重新验证令牌、查询执行结果，不要新建请求猜测重发。丢响应先查询原幂等键；只有查明原键不存在才提供显式同键重试。accepted仅表示服务商受理；须另核对邮件收件箱和飞书群实际内容。邮件可经新请求、独立确认再次发送同一版本，可能产生重复邮件；部分受理或 unknown 时先核实实际收件，系统不会自动重发。飞书同版本已受理/部分受理/unknown 继续禁止重发，明确 rejected 可单独重提。重新生成会改变日报版本，旧确认被拒绝后需重新预览。

两个窗口按 Ctrl+C 停止。单 Uvicorn worker、无 reload；生产Origin仅127.0.0.1:5173/4173，不要暴露到局域网。生产预览在同模式/公开API地址下 `npm run build`、`npm run preview`；Vite环境变量在构建时确定，切模式需重新构建。回到只读启动时先 `Remove-Item Env:VITE_API_MODE -ErrorAction SilentlyContinue`，并使用后端 --database。

### 操作模式可复现 fixture（不访问真实平台）

```powershell
# 窗口 A，在隔离工作区根目录
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
& 'E:\MyCode\smart-daily-report\.runtime\venv\Scripts\python.exe' frontend/e2e/serve_operations_fixture.py --port 8775
# 窗口 B，在该工作区 frontend
$env:VITE_API_MODE = 'operations'
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8775'
npm run dev -- --port 5174
```

打开 http://127.0.0.1:5174，示例日期2026-09-25，公开假令牌 `public-e2e-only-token-not-a-real-secret-123456`。这是专用测试服务：真实 FastAPI/SQLite/Collector/Notifier，只有 HTTP/SMTP 外部边界使用替身；不会发送真实通知。固定目录 `.runtime/e2e-operations` 的测试文件会重建，绝不指向真实配置/数据库。5174 Origin仅测试工厂注入，不加入产品白名单。

自动回归（frontend）：

```powershell
$env:PYTHONPATH = Join-Path (Split-Path (Get-Location) -Parent) 'src'
$env:DAILY_REPORT_PYTHON = 'E:\MyCode\smart-daily-report\.runtime\venv\Scripts\python.exe'
# 5173被自己需要保留的服务占用时，可使用产品已允许的4173
$env:DAILY_REPORT_E2E_PORT = '4173'
$env:DAILY_REPORT_E2E_SCREENSHOT_DIR = '../docs/frontend/screenshots/v1.2/readonly'
npm run test:e2e
npx playwright test --config playwright.operations.config.ts
npm run test -- --run --coverage
npm run typecheck
npm run build
```

先释放测试用5173/5174/8765/8766/8775端口。测试使用已安装Chrome；报告见 v1.2-acceptance.md。运行截图中的令牌/来源为公开假值，不能当真实平台或实际收件证据。

### 2026-10-03本轮运行和发送状态

真实API8000与React operations5173已恢复，已有10/1非空任务日报保持原版本。用户确认固定版本及双目标后，产品HTTP推送API只提交一次；两渠道accepted且各attempts1，用户已确认两处均收到、内容一致、无重复。另补充4/23真实GitHub2条历史预览，未发送。此段是2026-10-03历史记录：当时同版本邮件和飞书均受整渠道重发保护。本轮邮件主动再次发送规则已替代该邮件限制，飞书规则保持；不要删除操作库。本轮实际确认来自用户对话，未冒充真实浏览器按钮点击，既有浏览器交互回归单独记录。

### 最新检查与使用提示（2026-10-05）

本机真实配置/数据库保留在上述工作区；发布代码通过GitHub分支/PR/main交付，本文工作区命令继续有效。v1.2.0最终286项Python、102项前端及14+26项浏览器测试通过。详见 [完成情况审查](v1.2-completion-audit.md)。修改Python采集/模板代码后，下次使用本文命令重启后端，使进程加载最新实现；启动本身不生成或发送。

输入本项目操作令牌并点击验证后才启用“采集并生成”；空/全空格验证在本地提示并聚焦，无API请求。页脚“查看已保存的团队日报”是说明文字，实际入口是页面上方日期查询控件。

2026-10-05真实工作日消息4条已完成源/SQLite/API/React核对，生成耗时1953ms且发送0次；本机页面可选择2026-04-23查看提交、2026-10-01查看完成任务、2026-10-05查看协作消息。查询旧日报不需要再次发送；主动再次发邮件需要重新选择地址和确认，飞书仍保留同版本限制。不要修改历史日期或删除操作记录库。工作日判断使用项目配置，不宣称国家法定假日/调休适用。


## 操作改进使用要点（2026-10-11）

- 「查询执行结果」提供加载/完成/无记录/错误提示，同时展示服务器更新时间与本次查询时间；「预览日报」完成后定位正文标题。主动 GET 超过10秒提示超时，后台任务仍继续。
- 邮箱列表只在操作令牌验证后的预览接口返回；初始全部未选，选择邮件且地址为空时按钮禁用并说明原因。默认仅从 config.yaml 的 smtp.recipients 选择，不能在页面添加任意地址。
- 确认弹窗展示所选具体邮箱；新执行结果记录此次地址。旧历史记录没有该字段时明确“历史记录未记录具体收件人”，不推断旧配置。
- 邮件新请求可以再次发送同版本，可能重复；同一请求仍去重。网络异常先查原键，只有未找到才提供保留原地址的显式重试；禁止自动重发。飞书原阻断规则保持。
- accepted 是服务商受理，不是实际送达。Gmail 收件箱无邮件时检查垃圾邮件及全部邮件；对确认可信的发件人标记“不是垃圾邮件”或建立过滤器，见 README 的发送步骤。
- 前后端新契约必须配套：邮件 POST 必须提供非空 email_recipients；旧页面缺字段将返回400，不会退回给所有人发送。重启后端并从本轮目录启动前端才能使用改进。
