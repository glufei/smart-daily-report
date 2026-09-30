# 智能日报生成器架构设计（Design）

- 版本：v1.1（2026-09-30）
- 状态：用户已确认 v1.1 规范与 ADR；实现与验收完成
- 上游：[`proposal.md`](proposal.md)
- 接口契约：[`contracts/interfaces.md`](contracts/interfaces.md)、[`contracts/data-models.md`](contracts/data-models.md)、[`contracts/http-api.md`](contracts/http-api.md)（v1.1 已确认）
- 配套来源：作者的[官方章节代码仓库](https://github.com/huangjia2019/sdd-in-action)；当前规范保留原书模型字段，并针对本项目验收要求增加身份键、来源状态和安全诊断字段。

## 1. 架构概览

v1.0 生成链路采用单进程管道式架构，执行方向为：配置/工作日判断 → 并发或独立数据采集 → 身份归一和敏感内容过滤 → 按成员聚合 → Markdown/HTML 生成 → SQLite 历史保存 → 邮件与飞书推送。各步骤通过 `specs/contracts/` 定义的数据模型交接。v1.1 增加独立的只读查询链路，具体范围以 `proposal.md` 的已确认范围为准。

```text
GitHub ─────┐
飞书任务 ───┼─> Collector ─> Shared(身份/过滤/结果) ─> Generator ─> SQLite
飞书消息 ───┘                                              ├─> SMTP
                                                         └─> 飞书机器人
```

### 1.1 模块职责

| 模块 | 负责 | 不负责 |
|---|---|---|
| `collector/` | GitHub 提交、飞书任务和消息的 API 访问、分页、源数据解析；每个来源独立返回成功/失败结果 | 身份聚合、日报格式、推送 |
| `generator/` | 接收聚合后的成员报告，按固定三段结构生成 Markdown 和 HTML | 外部 API 调用、秘密读取、消息采集 |
| `notifier/` | 将既有 DailyReport 分别发送至 SMTP 与飞书机器人并报告投递结果 | 数据采集、内容生成、SQLite 查询 |
| `shared/` | 配置与账号映射校验、工作日判断、敏感词过滤、错误类型、JSON 日志、SQLite 存储、共享 HTTP 策略 | 具体数据源业务与日报模板 |
| `main.py` | 命令行入口、确定性编排、部分失败降级、退出码 | 将业务判断委托给模型或隐藏在模块副作用中 |

`generator/formatter.py` 负责校验数据状态并组装 DailyReport；`generator/template.py` 负责 Markdown/HTML 模板渲染与外部链接安全处理。

### 1.2 v1.1 前后端分离（已确认）

```text
外部定时任务 → 既有 Python CLI → Collector/Generator → SQLite → Notifier
                                                       ↑ 只读
浏览器 → frontend/（React + TypeScript + Vite）→ HTTP API（FastAPI）

OpenDesign → 虚构数据原型/设计迭代 → 经审阅的前端实现（设计期工具）
```

- `frontend/`：日期选择、请求状态和结构化日报展示。使用 React 状态与原生 fetch，不增加全局状态框架、SSR 或第二套业务模型。加载、400/404/500/网络错误由确定性代码处理；仅用户重新查询，不自动重试。
- `src/smart_daily_report/web/`：独立 FastAPI 应用工厂、显式响应 DTO、HTTP 错误映射和本机启动入口；只调用 Shared 的读取能力，不调用生成编排器。FastAPI/运行服务器放在 `web` 可选依赖组，CLI 不导入 Web 模块。
- `shared/storage.py`：复用 `get_report()` 的反序列化和既有模型，增加只读读取约束（SQLite `mode=ro`）；`write_report()` 和存储 schema 保持。API 不自动创建数据库/表；不存在文件或已有空表为“无日报”，已有库结构异常/损坏/不可读为安全存储错误。
- OpenDesign 为设计和代码交接工具；其桌面程序、daemon、模型调用和自身 `/api/*` 不属于日报系统运行架构。前端不会在用户查看日报时调用模型。
- 查询接口只接收启动时指定的数据库路径，不复用要求 SMTP/飞书凭证的整份 `load_config()`；浏览器不能指定文件路径，Web 启动不需要源平台或推送凭证。

本机 API 默认 `127.0.0.1:8000`，前端开发/构建预览默认 `127.0.0.1:5173` / `127.0.0.1:4173`，均限制 loopback。API 只允许明确的本机前端 Origin，并校验本机 Host；CORS 不使用 `*`，本期无 Cookie 会话。未允许的 Origin 请求在服务端拒绝，本机无 Origin 请求允许用于契约测试；响应 `Cache-Control: no-store`。公网/局域网发布及认证设计不在本期范围。

### 1.3 现有后端接口适配评估

2026-09-30 检查 `pyproject.toml`、`main.py`、`shared/models.py`、`shared/storage.py` 及现有测试：当前只有 CLI 与内部 Python 函数，没有 HTTP 路由、Web 框架或前端项目。`get_report(db_path, report_date)` 和 `DailyReport` 足以提供指定日期数据，但不能直接被浏览器调用；不能把 GitHub/飞书上游 API 或 OpenDesign 自身接口当作日报后端接口。

新增唯一业务路由 `GET /api/v1/reports/{report_date}`。URL 日期、JSON DTO、状态码和错误格式见 [`contracts/http-api.md`](contracts/http-api.md)。直接复用 SQLite 的结构化数据，不解析 HTML/Markdown，也不在前端重做身份归一/敏感过滤。历史未记录投递状态和失败运行历史，因此本期不展示“已投递”、最近运行失败原因等无法证明的状态。

## 2. 技术决策与 ADR

ADR-004（v1.1 已确认）：见 [`adrs/004-opendesign-frontend.md`](adrs/004-opendesign-frontend.md)，记录 OpenDesign 同名项目调查、候选身份、React/Vue 取舍、Vite 与 FastAPI 适配层。用户已采纳推荐候选与技术方案；实际 OpenDesign 0.24.1 已验证，运行依赖在任务执行时核验并锁定。

ADR-003：见 [`adrs/003-collect-result.md`](adrs/003-collect-result.md)，记录第 7 章暴露的采集返回值契约修正。

ADR-001 与 ADR-002 的独立记录分别位于 [`adrs/001-http-client.md`](adrs/001-http-client.md) 和 [`adrs/002-sqlite-storage.md`](adrs/002-sqlite-storage.md)。

### ADR-001：采用 httpx 作为 HTTP 客户端

- **状态**：已采纳
- **背景**：GitHub 与飞书 API 需要统一的超时、连接管理、限流处理与 Mock 能力；性能目标要求多来源耗时受控。
- **选项**：`requests`（同步生态成熟）、`httpx`（同步/异步 API）、`aiohttp`（异步专用）。
- **决策**：采用 `httpx`；初始命令行实现允许使用同步 API，调用方不得依赖具体 client 实现。
- **理由**：同一客户端同时支持同步与异步接口，适配当前简单运行方式并保留后续并发采集选择；可通过传入 client 或 MockTransport 进行确定性测试。
- **后果**：网络调用必须设置明确连接/读写超时；所有重试与 HTTP 状态码策略由确定性代码执行，不由模型或调用者猜测。

### ADR-002：采用 SQLite 保存日报历史

- **状态**：已采纳
- **背景**：需要保留本地日报历史；团队小、定时运行、无需常驻服务。
- **选项**：SQLite、PostgreSQL、JSON 文件。
- **决策**：使用 SQLite 本地文件，表结构仅存储生成日期、日报结构化内容/渲染内容及创建时间；凭证和未过滤消息不得入库。
- **理由**：免独立服务、Python 标准库支持、满足低并发的本地历史存储需求。
- **后果**：数据库路径可配置；写入使用事务；重复日期的行为必须幂等且由接口契约明确。

## 3. 数据模型与接口

字段类型、可空性、身份键、采集结果状态及公开函数签名以 `specs/contracts/data-models.md` 与 `specs/contracts/interfaces.md` 为准。接口必须能区分 `success + []` 和 `failure`。任何实现不得用空列表代表失败。

v1.1 HTTP 响应是 `DailyReport` 的显式白名单投影，详见 `contracts/http-api.md`；内部模型不删除原有字段，HTTP 不返回全部 dataclass 属性。顶层来源状态须完整；未知状态或损坏数据在 Web DTO 适配时返回错误，不得默认补成 `success`，不在 Shared 读取方法中新增展示层校验。

**状态来源冲突的处理**：内部 `MemberReport.source_status` 与 `DailyReport.source_status` 重复，而现有 `render_markdown()` / `render_html()` 实际使用顶层状态。v1.1 选择沿用模板约定：HTTP 只输出顶层状态，前端所有成员板块据此展示，不输出/合并成员状态。内部重复字段保留兼容；其移除或校验统一列为待清理事项，不包含在本次迭代。

## 4. 配置与身份映射

- 配置文件为 YAML；样例文件不得含真实密钥。
- `members` 中每个内部成员具有稳定且唯一的 `member_id`、显示名称，以及 GitHub login 列表和飞书 user ID 列表。对无法关联 GitHub 账号的历史提交，可显式配置 `github_author_names`；仅当 API 的 `author.login` 缺失时使用该备用映射。
- 每个外部账号最多属于一个 `member_id`；加载配置时检测重复与冲突并失败退出。
- 凭证由环境变量读取，映射表本身不含秘密。
- 公开 GitHub 仓库允许匿名读取；私有仓库通过环境变量提供只读 Token。
- 仓库、飞书项目、群组、关键词、敏感词、时区、节假日和推送目标均来自配置并经过必填项验证。

## 5. 失败处理与优雅降级

### 5.1 采集

每个采集器独立执行，返回 `CollectResult[T]`，包含状态、记录、错误分类和安全诊断信息。正常空结果状态为 `success` 且记录为空。一个采集器失败不取消其他采集器；全部数据源失败则编排器不生成日报。

### 5.2 重试

- 对连接错误、超时、HTTP 429、HTTP 5xx 按固定上限重试；默认最多 3 次总请求（首次 + 最多 2 次重试），退避间隔有上限并尊重服务器 `Retry-After`。
- GitHub 403 仅在响应明确表明 rate limit 且存在 reset 信息时等待到 reset 后重试；权限不足的 403 不重试。
- 飞书 Token 失效时通过 TokenProvider 刷新一次，原请求重放一次；Token 刷新路由本身不递归重试。
- HTTP 4xx（限流与明确 Token 过期除外）不重试。重试耗尽后以来源失败结果返回。
- 重试、等待与状态分类由代码实现；日志记录 attempt、来源、状态类别和耗时，不记录 Token 或消息正文。

### 5.3 推送与存储

邮件、飞书推送分别执行并分别记录成功/失败；单一渠道失败不影响另一渠道。存储失败视为本次执行失败并阻止误报成功；推送失败后保留生成的日报历史及失败状态。

## 6. 安全与隐私

- 飞书消息先应用允许关键词条件，再应用敏感词排除条件；敏感过滤优先级更高。
- 敏感词默认对整条消息做不区分大小写匹配；匹配后丢弃整条消息，不截断保留。
- 原始敏感消息不得写日志、日报、异常文本或 SQLite。解析异常日志只能包含来源、记录 ID（若安全）和错误类别。
- Markdown/HTML 输出对来自外部的文本做适当转义，避免 HTML 注入。
- 密钥仅从环境变量或运行环境秘密注入，日志对授权头、Token、Webhook URL 和 SMTP 凭证脱敏。
- SMTP 支持 STARTTLS 与隐式 TLS 两种互斥模式，以适配常见邮件服务商的安全连接方式。
- 日志与诊断不输出敏感内容；账号映射缺失时仅记不含消息正文的计数/账号标识（账号标识按配置要求脱敏）。

## 7. 可运维性

- 使用标准库 `logging` 输出一行一个 JSON 对象；至少包含时间、级别、事件、运行 ID；采集/推送事件包含来源、耗时、记录数或结果类别。
- CLI 提供正常运行、`--dry-run`、`--check`。`--check` 执行配置校验和配置中必需外部依赖的轻量连通性/鉴权检查，不生成日报、不写历史、不推送；返回码 `0` 为通过，非 `0` 为失败，输出结构化诊断。
- 非工作日跳过是成功结束，记录 `skipped_non_workday` 与日期来源。
- 所有失败、部分失败和跳过均有机器可读日志事件。

## 8. 验证策略

- 单元测试：每个采集器使用 httpx MockTransport 或注入的假客户端；不访问真实外网。验证成功、空结果、分页、重试、限流、Token 刷新及失败结果。
- 单元测试：身份映射冲突、敏感词过滤、工作日判断、格式生成、存储和配置校验。
- 集成测试：注入 Mock 数据和 Mock 推送端，覆盖全成功、单源失败、全源失败、空数据、非工作日、单渠道推送失败。
- 每个任务的验收项映射到测试；测试以可观察意图断言行为，包括失败不能冒充空数据、敏感内容不能泄漏、部分故障不能阻断其他来源。

### 8.1 v1.1 验证增量

- API 使用临时 SQLite 与 FastAPI TestClient/httpx 验证结构化 DTO、400/404/500、严格日期、只读和无采集/生成/推送副作用；用禁用的调用替身证明查询不发通知。覆盖数据库缺失、空表、缺表、损坏、读取异常和不可信文本/链接。
- 前端使用 Vitest + Testing Library 验证状态与文案，Playwright 验证真实查询链路、键盘操作、两种视口和日期切换竞态。Mock 的 JSON 与 HTTP 契约一致，不以 Mock 页面替代最终联调。
- Task 14 运行全部 Python 测试（业务覆盖率仍 ≥90%）、前端类型检查/构建/测试。验收截图、OpenDesign 来源和前后对照记录在 `docs/frontend/`；设计输入只用虚构数据。
- 原 Task 1–10 的已完成标记与历史验证记录保留；v1.1 新任务在实现和验收前全部保持未完成。
