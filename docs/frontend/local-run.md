# 本机只读日报页面与 API

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

正常有日报返回结构化 JSON。日期非法为 400，无已保存日报为 404，已有库缺表/损坏/读取错误为 500；来源部分失败的历史日报仍为 HTTP 200，并携带对应 `failure` 状态。接口不提供生成或推送操作。

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
