# 本机日报页面与 API

v1.1 Task 11–14 已完成：OpenDesign 两轮 UI 原型、React 页面、只读 API 及验收。全部请求状态由确定性代码处理；页面不调用模型。

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

完整测试需要安装 `dev,web` 两组依赖。不安装 `web` 的基础 CLI 仍可使用，测试包不会自动跳过 Web 测试。当前全套结果为 98 项通过、业务代码覆盖率 92.02%；没有跳过测试。Starlette 对 httpx TestClient 有一项上游弃用提示，当前契约测试可用；本轮未为消除提示替换项目既有 httpx 客户端。

## React 页面（第二个 PowerShell 窗口）

Node `^22.12.0 || ^24.0.0 || >=26.0.0`；本轮 Node 24.15.0、npm 11.12.1。运行：

```powershell
cd frontend
npm ci
npm run dev
```

打开 `http://127.0.0.1:5173`，选择数据库中已保存的报告日期，再点击“查看日报”。默认 API 为 `http://127.0.0.1:8000`。若 API 使用另一端口，启动 Vite 前在同一窗口设置 `$env:VITE_API_BASE_URL='http://127.0.0.1:8001'`。此变量仅是公开的本机 HTTP 地址，不能写数据库路径或凭证。Origin 固定使用 127.0.0.1，勿改成 localhost 或监听外网。

构建及预览：

```powershell
npm run typecheck
npm run build
npm run preview
```

预览在 `http://127.0.0.1:4173`。构建时固定 API 地址；改变 `VITE_API_BASE_URL` 后需要重新 build。页面初始不自动查询，缺失日期为“该日期尚无日报”；不会通过浏览器创建日报。API 和 Vite 终端均可 Ctrl+C 结束。测试期间留下的临时示例预览使用 `.runtime/api-smoke.sqlite3`、2026-09-25，只包含虚构数据；查看实际历史需自行用实际 SQLite 路径启动 API。

前端测试（frontend 目录）：

```powershell
npm run test -- --run
npm run test:e2e
```

Playwright 使用已安装的 Google Chrome；需要 Python 环境安装 `dev,web`，默认 `.runtime/venv/Scripts/python.exe`。其他 Python 路径可通过 `DAILY_REPORT_PYTHON` 指定。E2E 自动启动 8765/8766 两个 fixture API 及 5173 Vite，测试前需释放这些端口；不复用其他正在运行的服务。临时库仅位于 `.runtime/e2e/`，不会访问实际日报配置/数据库或发送通知。测试每次只重建自身固定的 fixture 文件。

结果：15 项 Vitest、14 项 Playwright 通过，两种视口均无页面级横向溢出。首次 E2E 在受限进程环境中断言通过但服务清理未结束，Ctrl+C 后退出 1；允许本任务测试子进程正常清理后重跑，14 passed、退出 0。Playwright 有 NO_COLOR/FORCE_COLOR 的环境提示，断言及退出不受影响。

## 锁定依赖与开源复用

React 19.3.0、React DOM 19.3.0、Vite 8.3.1、TypeScript 7.0.2、Zod 4.6.5；Vitest 5.0.3、Testing Library React 16.3.3、Playwright 1.63.0。`package-lock.json` 与 `npm ci` 验证通过，不添加路由、组件库或状态管理框架。通用校验使用 [Zod（MIT）](https://github.com/colinhacks/zod)，用户意图测试使用 [Testing Library](https://github.com/testing-library/react-testing-library)，浏览器验收复用 [Playwright（Apache-2.0）](https://github.com/microsoft/playwright)；Node 依据 [Vite 官方要求](https://vite.dev/guide/)及 npm engines 核验。

## OpenDesign 工具状态

官方来源：https://github.com/nexu-io/open-design/releases/tag/open-design-v0.24.1 。安装文件 SHA256：`3a544dca7a5f078029d55f272e218278e52edac55efbfb292d56258113e8a441`，与 GitHub 发行资产 digest 一致。

软件安装在 `.tools/OpenDesign/`，与 `.runtime/` 一同被 Git 忽略。初版、第二版、实际输入、截图和可见修改已保存于 `docs/frontend/prototypes/`；详见 `opendesign-evidence.md`。产品不需要 OpenDesign 运行。已公开并修复原型手机异常留白，见 `DESIGN.md` 的交接差异。


## v1.2 真实操作模式（开发验收待完成）

Task15–17已实现。默认仍为只读；操作模式必须成对启动：后端 `--config`，前端 `VITE_API_MODE=operations`。产品不导入 fixture，不会用预制成功数据替代失败响应。当前变更在隔离工作区 `E:\worktrees\v1-2-real-integration\smart-daily-report`，main 尚未合并；本机 Python 依赖环境复用 `E:\MyCode\smart-daily-report\.runtime\venv`，因此以下工作区命令明确设置 PYTHONPATH，避免意外导入 main 的旧代码。

详细填写步骤见 [163邮箱、GitHub与飞书配置指南](v1.2-configuration-163-feishu.md)。

### 窗口 A：配置与真实后端

在工作区放置被忽略的 config.yaml，按 config.yaml.example 设置真实来源、成员映射、固定目标及凭证环境变量名。现有配置中旧 `lark_task_search_path: /task/v2/tasks/search` 必须迁为 `/task/v2/tasklists/{tasklist_guid}/tasks`；`lark_project_ids` 填已授权 tasklist GUID。任务按 completed_at 和团队时区展示所选日期完成的记录，不代表任意历史状态变更。

```powershell
Set-Location 'E:\worktrees\v1-2-real-integration\smart-daily-report'
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
# 将自己保管的 .env 加载到此窗口的进程环境；加载方法见 README。
& 'E:\MyCode\smart-daily-report\.runtime\venv\Scripts\python.exe' -m smart_daily_report.web.main --config '.\config.yaml'
```

必须注入 `DAILY_REPORT_WEB_TOKEN`（至少32字符、非空白的本项目操作令牌）；按配置注入 `DAILY_REPORT_GITHUB_TOKEN`、`DAILY_REPORT_LARK_APP_ID`、`DAILY_REPORT_LARK_APP_SECRET`、`DAILY_REPORT_LARK_WEBHOOK`、`DAILY_REPORT_SMTP_USERNAME`、`DAILY_REPORT_SMTP_PASSWORD`。实际变量名以 YAML 的 *_env 值为准；不要把值写入命令示例、浏览器 URL 或 VITE_*。程序不自动读取 .env。操作令牌必须通过自己安全保管的环境文件/进程注入，刷新页面后需重新输入。

GitHub公共库可匿名但有限流；私有库需读取权限。飞书应用须获租户授权、可读目标清单及群消息，机器人须在固定目标群中可用。真实任务接口已确认要求 task:tasklist:read（或 write，本项目只需 read）；读取scope已在真实请求生效；原清单配置误用任务GUID已修正，但正确清单GET403且应用列取可见清单为0，需清单授权应用访问，见 [具体权限步骤及清单链接](feishu-tasklist-permissions.md)。无需发送邮件时可省略/清空 smtp；配置了 smtp 时 host/sender/非空 recipients、1–65535端口和布尔互斥TLS必填；声明登录环境变量时用户名和密码必须成对存在且非空白，不静默转为匿名连接。数据库路径相对于启动工作目录，操作库位于同目录 `<日报库文件名>.operations.sqlite3`；不要删除操作库来“解除重发限制”。

### 窗口 B：React 操作页面

```powershell
Set-Location 'E:\worktrees\v1-2-real-integration\smart-daily-report\frontend'
$env:VITE_API_MODE = 'operations'
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000'
npm run dev
```

打开 http://127.0.0.1:5173，选择有源数据的工作日，输入本项目操作令牌并点“验证令牌”。点击“采集并生成”只采集、保存、预览；“查看日报”仅查询历史，“预览日报”取得可确认版本和固定目标摘要。核对来源、日期、内容后选渠道、点“推送日报”，在对话中确认日期、摘要和固定目标再发送；取消不会发送。

202只是接受操作。页面每2秒查询、最多观察120秒，停止观察或关页不会取消后端；刷新后重新验证令牌、查询执行结果，不要新建请求猜测重发。丢响应先查询原幂等键；只有查明原键不存在才提供显式同键重试。accepted仅表示服务商受理；须另核对邮件收件箱和飞书群实际内容。部分受理/unknown不整渠道重发；明确rejected可单独重提失败渠道。重新生成会改变日报版本，旧确认被拒绝后需重新预览。

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
