# v1.6.6 全项目审查与验证记录

审查跨 2026-10-13 至 2026-10-14 进行，基线为 `392274e`（v1.6.5）。用户要求审查整个项目、修复问题、清理无用途文件、纠正路径和 README，并完成 GitHub 与本地合并。本轮沿用现有手动运行方式。

## 审查范围

| 范围 | 检查内容 |
| --- | --- |
| Python 全部产品模块 | GitHub/飞书采集、分页、Token、错误分类、重试、身份映射、敏感词过滤、报告模板、SMTP/Webhook、SQLite、CLI、FastAPI 和操作状态 |
| 前端全部产品模块 | API 校验、日期和时区、异步请求隔离、令牌验证、预览、邮箱选择、独立推送确认、幂等键、可恢复错误、页面样式 |
| 测试与构建 | Python 单元/集成测试、Vitest、Playwright 两种模式及视口、TypeScript、Vite 两种模式、wheel、可编辑安装及命令入口 |
| 文件和文档 | 跟踪文件清点、重复截图用途、文档相对链接、当前与历史状态、示例配置、包版本和锁文件、私有文件排除 |

后端、Web/前端、文档分别完成独立只读审查；修复后再次复核后端和前端差异。发现的问题由主工作区集中修复，避免并行修改冲突。

## 修复结果

1. **SMTP 服务器身份验证**：STARTTLS 与隐式 SSL 均传入 `ssl.create_default_context()`，验证服务器证书与主机名；隐式 SSL 健康检查使用相同验证规则。证书验证失败时不登录、不发送。原有发送受理、拒绝、部分受理、未知结果和重试边界保持。
2. **GitHub 分页循环检测**：提交详情页使用独立的已访问页集合，避免覆盖提交列表的集合。重复列表链接在再次请求前报 `invalid_pagination`，不会持续循环采集。
3. **空提交信息**：合法的空消息保留为空字符串，不再抛出 `IndexError` 或使当天其他提交被丢弃。
4. **配置字符串列表**：来源、成员身份及关键词拒绝标量、非字符串元素和空白元素，并提供具体字段名。空列表继续表示禁用或无匹配项；成员重复映射规则保持。
5. **前端操作锁恢复**：取消旧请求观察时释放锁，新提交在建立新请求后获取锁。提交过程中修改日期或收到 401 后，查询原请求、重新验证和明确重试均可恢复；原幂等键与确认内容保留，旧响应不能解锁新操作。
6. **数据库连接释放**：日报读写沿用 `OperationStore` 的 `closing()` 模式，事务完成后关闭 SQLite 连接，避免 Windows 文件句柄残留。
7. **邮件飞书时间**：任务与工作消息复用 GitHub 的中国标准时间格式。例如 `2026-09-25 10:00 UTC` 展示为 `2026-09-25 18:00:00（中国标准时间，UTC+08:00）`。原始时间点和采集窗口不变。
8. **邮件群名转义**：群名统一在整行 HTML 输出时转义一次，修复含 `&` 或尖括号的名称显示成实体代码的问题；真实 HTML 解析器测试同时验证可读文本和注入保护。
9. **运行与状态文档**：纠正从 `frontend` 运行时的 Python 相对路径；纠正 README 中品牌标题可配置的误述；将 Task26/27 当前状态改为已发布，保留带日期的历史 checkpoint；明确邮件发送保存的 HTML，更新模板不会改写旧快照。
10. **开发工具安全版本**：OSV 扫描发现本机 pip 25.0.1 和 pytest 8.4.2 命中已知公告；分别更新到 pip 26.2.1、pytest 9.1.1，并将开发依赖最低值提高至 `pytest>=9.0.3`、安装说明补充 `pip>=26.2`。版本依据见 [pytest 公告](https://github.com/advisories/GHSA-6w46-j5rx-g56g)和 [pip 公告](https://github.com/advisories/GHSA-qwm4-qh6w-59xr)，升级后重新完整回归和扫描。

主要缺陷先添加回归测试并观察预期失败，再最小修复。GitHub 分页/空消息、两种 SMTP TLS 验证及配置列表测试首轮共 28 项失败；页面恢复的两项测试首轮均因未发出第二次明确请求而失败。连接释放测试首轮确认读写连接仍打开；群名测试首轮确认可见内容包含实体代码。最终完整测试不跳过这些场景。

## 清理依据

- 删除 `src/smart_daily_report/shared/calendar.py`，以及只验证该旧工具的测试和当前接口声明。产品已允许任意有效日期，工具没有生产调用；保留 `team.holidays` 配置兼容与周末/节假日可生成的现有测试。
- Markdown 无产品代码调用，只用于真实 Markdown 解析器安全测试；从运行依赖移到 `dev`，保持测试所需能力。
- wheel 构建前清理项目根目录中可重新生成的 `build` 缓存，防止已删除模块进入旧构建结果；wheel 内容检查确认没有 `calendar.py`。
- 历史验收目录有 24 对字节相同的截图，但分别属于不同验收轮次且有文档用途，保留。OpenDesign 原型、TDD/发布记录、包标记及根 `main.py` 兼容入口均有保留用途。
- `.env`、`config.yaml`、真实数据库、虚拟环境和历史工作区保持本地私有；不删除、不提交。新的浏览器截图输出到被忽略的 `.runtime/audit-screenshots/`，避免改写既有证据。

## 验证结果

本机：Windows、Python 3.12.14、pytest 9.1.1、pip 26.2.1、Node 24.15.0、npm 11.12.1。

| 检查 | 结果 |
| --- | --- |
| Python 单元与集成测试 | 370 项通过，覆盖率 95.06% |
| 前端单元测试 | 151 项通过；行覆盖率 100%，分支覆盖率 94.74% |
| TypeScript | 类型检查通过 |
| Vite | 只读模式、操作模式生产构建均通过 |
| Playwright 只读模式 | 桌面/手机合计 16 项通过；SQLite 字节不变，无采集或发送 |
| Playwright 操作模式 | 桌面/手机合计 38 项通过；真实本地 API/SQLite，外部 HTTP/SMTP 为合成边界 |
| 前端依赖 | `npm audit --json`：0 个已知漏洞 |
| Python 依赖安全 | 向 OSV 查询本机 31 个外部 Python 包的已安装版本，升级后 0 个匹配公告 |
| Python 环境 | `pip check` 通过；本地可编辑安装版本更新至 1.6.6 |
| Python 打包 | v1.6.6 wheel 构建成功，无私有配置/数据库/废弃模块 |
| 命令入口 | `daily-report.exe --help` 与 `daily-report-web.exe --help` 通过 |
| 文件与链接 | 230 个项目文件、49 个 Markdown 文件；相对链接目标全部存在，所检查的 GitHub Token/私钥模式无匹配 |

本地构建首次因缺少 setuptools 失败，补齐构建工具后重跑成功；既有安装元数据原为 1.3.0，已更新为 1.6.6。受限环境对旧包元数据写入的拒绝经授权执行后完成。测试最初有 3 项 SMTP 夹具参数不兼容，已同步夹具并完整重跑，表中只记录最终结果。

Python 测试仍有 1 项 Starlette/httpx TestClient 上游弃用提示；浏览器运行有 NO_COLOR/FORCE_COLOR 环境提示。它们不影响本次退出码与断言，本轮未为消除提示进行额外升级。依赖扫描反映查询时数据库与已安装版本的匹配结果，不代表不存在尚未披露的问题。

## 复现命令

项目根目录：

```powershell
.\.runtime\venv\Scripts\python.exe -m pytest -q
.\.runtime\venv\Scripts\python.exe -m pip check
.\.runtime\venv\Scripts\python.exe -m pip wheel --no-deps --no-build-isolation . --wheel-dir .runtime/audit-wheel
```

无构建工具时先安装 `setuptools>=68` 和 `wheel`；日常安装依赖仍按 [README](../README.md) 使用 `.[dev,web]`。

从项目根目录进入 `frontend`：

```powershell
Set-Location frontend
npm run typecheck
npm run test -- --run --coverage
$env:VITE_API_MODE = 'readonly'
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000'
npm run build
npm audit --json

$env:PYTHONPATH = Join-Path (Split-Path (Get-Location) -Parent) 'src'
$env:DAILY_REPORT_PYTHON = (Resolve-Path '..\.runtime\venv\Scripts\python.exe').Path
$env:DAILY_REPORT_E2E_PORT = '4173'
$env:DAILY_REPORT_E2E_SCREENSHOT_DIR = '../.runtime/audit-screenshots/readonly'
npm run test:e2e
$env:DAILY_REPORT_E2E_SCREENSHOT_DIR = '../.runtime/audit-screenshots/operations'
npx playwright test --config playwright.operations.config.ts

$env:VITE_API_MODE = 'operations'
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000'
npm run build
```

需要 Chrome 和空闲的 4173、5174、8765、8766、8775 测试端口。测试服务自行启动和退出；没有向实际邮箱或飞书群发送通知。

## 验证边界与同步

本轮检查代码、离线/本机集成行为和配置边界；没有重新核验外部账号授权或真实邮件/飞书送达，也没有重写历史报告。本轮发现的必须修复问题均已有回归测试和独立复核结果。

审查分支为 `codex/comprehensive-project-audit`，目标仓库为 [glufei/smart-daily-report](https://github.com/glufei/smart-daily-report)，合并目标为 `main`。最终提交、远程合并状态与本地主分支一致性以 GitHub 合并记录及本轮交付结果为准。
