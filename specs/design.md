# 智能日报生成器架构设计（Design）

- 版本：v1.2（2026-10-01）
- 状态：规范与计划已确认；Task15–17实现、Task18完整自动化回归已通过；真实GitHub提交、飞书完成任务及用户确认双渠道收件已核对，工作日消息页面真实验收和最终交付仍待完成；发布版本仍1.1.0（2026-10-03）
- 上游：[`proposal.md`](proposal.md)
- 接口契约：[`contracts/interfaces.md`](contracts/interfaces.md)、[`contracts/data-models.md`](contracts/data-models.md)、[`contracts/http-api.md`](contracts/http-api.md)（v1.1 保留）、[`contracts/web-operations.md`](contracts/web-operations.md)（v1.2 已实现、真实验收待完成）
- 配套来源：作者的[官方章节代码仓库](https://github.com/huangjia2019/sdd-in-action)；当前规范保留原书模型字段，并针对本项目验收要求增加身份键、来源状态和安全诊断字段。

## 1. 架构概览

v1.0 生成链路采用单进程管道式架构，执行方向为：配置/工作日判断 → 独立数据采集 → 身份归一和敏感内容过滤 → 按成员聚合 → Markdown/HTML 生成 → SQLite 历史保存 → 邮件与飞书推送。v1.1 增加只读查询链路；v1.2 增加生成与推送分开的浏览器操作链路。模型与接口通过 `specs/contracts/` 交接，生成链路不由模型编排。

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
| `web/`（v1.2 增量） | HTTP 鉴权/校验、只读投影、调用既有生成/推送能力、记录操作结果 | 在浏览器采集源数据、重做映射/过滤、自动重发不确定通知 |

`generator/formatter.py` 负责校验数据状态并组装 DailyReport；`generator/template.py` 负责 Markdown/HTML 模板渲染与外部链接安全处理。

### 1.2 v1.1 前后端分离（历史设计，继续约束只读模式）

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

### 1.3 v1.1 接口适配评估与 v1.2 事实基线

v1.1 开始前只有 CLI 与内部 Python 函数，不能直接被浏览器调用。此后已经实现 FastAPI GET、React fetch、白名单 DTO、状态测试和真实本机 HTTP 验收。2026-10-01 再次检查 `main.py`、`web/app.py`、`frontend/src/api.ts`、Collector/Notifier 和集成测试，确认真实源平台适配器存在，缺口是浏览器生成/推送入口、操作鉴权、结果追踪和浏览器真实外部验收。不能把上游 API 或 OpenDesign 自身接口当作日报后端接口。

v1.1 唯一业务路由是 `GET /api/v1/reports/{report_date}`，契约保留。直接复用 SQLite 结构化数据，不解析 HTML/Markdown，不在前端重做身份归一/敏感过滤。旧历史未保存投递结果，不推断其“已投递”；v1.2 只为新增操作记录明确结果。

### 1.4 v1.2 联调与交互架构（已确认、待实现）

```text
React ──生成 POST / 本机操作 Bearer──> FastAPI 操作层
                                      ├─> 既有 run_report(dry_run=True)
                                      │   └─> GitHub/飞书 → 映射/过滤 → 日报 SQLite
                                      └─> 独立推送 → 既有 SMTP/飞书 Notifier
React <──历史 GET / 受保护的预览和操作状态 GET──┘
                         操作结果 → 本机独立 SQLite 操作记录
```

采用复用管道的轻量后台操作：POST 持久记录操作并返回 202，FastAPI 同步后台函数在线程池执行既有阻塞 I/O；浏览器查询状态。每个服务只允许一个运行中的 Web 操作，明确单 Uvicorn worker、不启用 reload；不引入 Celery/Redis、不建立待执行队列。同步长 POST 更简单但断线结果难确认；外部任务队列适合多实例，本轮规模不需要。[FastAPI BackgroundTasks](https://fastapi.tiangolo.com/tutorial/background-tasks/) 只是执行机制，不保证崩溃恢复；幂等、排他及中断状态由本项目操作记录保证。

**启动与配置**：原 `--database` 只读启动继续无需源平台秘密；新增互斥的 `--config` 操作启动，加载一次既有 RunConfig，以其 `database_path` 作为唯一日报库。操作启动要求环境变量 `DAILY_REPORT_WEB_TOKEN` 非空且至少 32 个字符，不从 CLI 参数传秘密。来源至少启用一个；已启用飞书来源缺少 App ID/Secret 等必需凭证时启动失败。只读模式不加载 RunConfig、不创建操作记录库，写路由不启用。

**CORS 与 Token**：沿用 loopback Host 与两个明确 Origin（127.0.0.1 的 5173/4173），操作模式允许 GET/POST/OPTIONS 与 Authorization/Content-Type/Idempotency-Key 头，不使用通配 Origin 或 Cookie。OPTIONS 预检不要求 Bearer，但无业务副作用；受保护路由逐次校验 `Authorization: Bearer <本项目操作令牌>`，使用 FastAPI HTTPBearer 与标准库安全比较。CORS 不是鉴权，无 Origin 的脚本请求也必须携带正确令牌。浏览器通过密码输入暂存令牌于内存，退出/刷新清空；绝不将上游 Token/SMTP 密码/Webhook 写入 VITE 环境变量、浏览器存储或 URL。[CORS 官方依据](https://fastapi.tiangolo.com/tutorial/cors/)。

**页面模式**：公开非秘密配置 `VITE_API_MODE` 默认为 readonly；operations 才显示令牌输入、生成、预览与推送交互，并与后端 `--config` 配套。原双窗口启动不设置该变量，继续仅查看历史。进入操作模式并认证后 GET 当前/最近操作，运行中则恢复观察；前端刷新不清除服务端幂等/渠道记录。此模式开关不是鉴权，不能绕过后端 Token 校验。 空或全空格令牌的验证点击由前端本地反馈并聚焦输入框，不请求后端；未认证的生成按钮保持禁用，通过可见提示、aria-describedby与面板内禁用样式说明原因。输入修正后清除本地空值提示，服务端鉴权及原操作恢复逻辑沿用。

**上游认证**：GitHub Token、飞书应用秘密、SMTP 授权码和机器人 Webhook 均复用服务器环境变量配置；后端向 GitHub/飞书传对应 Bearer，SMTP 使用 TLS 和服务器登录凭证。不同飞书接口的 Token 类型、权限和可访问资源必须按真实租户核对，不能仅凭能换取 tenant token 就声称任务接口可用；OAuth/用户登录系统不在本轮范围，若接口实际要求新的身份流程，先报告规范冲突。浏览器只调用本项目 FastAPI。

**业务复用**：生成直接调用既有 `run_report(..., dry_run=True)`，保持工作日、时区、账号映射、敏感过滤及持久化顺序，绝不误用会发送的默认调用。推送从服务器读取并校验已预览日报版本，捕获不可变 DailyReport 快照后仅调用所选 Notifier；不用 `run_report(..., dry_run=False)` 重新采集。不同渠道在独立 try/结果边界内执行。

**记录与重复处理**：新增操作记录库位于日报库同目录 `<日报文件名>.operations.sqlite3`，路径由服务器固定。记录操作 ID/幂等键/请求指纹/日期/类型/状态/日报版本/来源结果/渠道结果/时间及安全错误码，不保存秘密、上游正文或未过滤消息。SQLite 事务原子检查幂等键与全局活动槽；先持久接受记录，再返回 202，终态持久化后释放槽。重启将未完成项标为中断，可能发送过的渠道标为待核实，禁止自动重放。新旧日报 schema 不变，不为旧日期补造投递记录。

**版本与目标**：SHA-256 摘要使用 DailyReport 全部字段的规范 JSON（排序键、无多余空格、UTF-8、日期/时间 ISO 8601、列表保持顺序），摘要本身不包含可展示的秘密。预览返回 ReportView、摘要及固定配置目标的安全标签；具体服务器凭证/路径不返回。推送提交日期、摘要、渠道，摘要不一致为 409 并要求重新预览。两个渠道使用同一个已捕获快照，CLI 后续写入不会更换其内容。

**结果语义**：运行状态与来源状态、渠道状态分别建模。HTTP 202 仅表示已接受操作；SMTP 全部收件人被服务器接受、飞书有明确业务成功码才可记“已接受”。SMTP 部分收件人拒绝记部分失败；发送后读超时/响应不可解析等不能证明未发送的情况记待核实。禁止自动重交浏览器 POST或整渠道重发已接受/部分已接受/待核实通知；仅明确发送前失败或明确拒绝的渠道允许用户再次提交。可证明未发送的暂时故障才复用有上限的重试。

详细路由、DTO、状态码、版本/幂等语义与异常文案见 [`contracts/web-operations.md`](contracts/web-operations.md)。上游记录仍投影为现有 ReportView，并由后端响应模型与前端 Zod 对齐；不从未知字段或记录数量补出成功结果。

### 1.5 必须表面化的现有冲突

- `run_report()` 把未配置来源记为成功空结果，随后对三个来源整体判断全失败。v1.2 选择按**已启用来源**判断：无已启用来源为配置错误；全部已启用来源失败不生成。兼容保留 ReportView 的三个 success/failure 键，新增操作 `sources` 明确标记 disabled，不宣称其真实调用成功；旧历史没有启用元数据时显示“启用情况未记录”。
- 现有飞书任务适配以 tenant Token 调用仅支持 USER Token 的 search，并以更新时间推断状态变更；v1.2 采用用户已确认的“已授权清单 + 所选日期完成任务”。改为 GET `/task/v2/tasklists/{tasklist_guid}/tasks`（支持 TENANT），按 `completed_at` 毫秒时间戳筛选配置时区的 `[当日零点, 次日零点)`；0 表示未完成，不回退 updated_at/created_at。清单响应 `data.items` 为 TaskSummary，含 guid/summary/completed_at/members，足以满足本期范围，无须逐条获取详情；摘要缺链接时保留 null，不拼造链接。仅处理 user/assignee 成员并请求 user_id_type=open_id；每个负责人一条兼容 TaskRecord，以 `(guid, assignee_user_id)` 跨页/清单去重。缺少负责人保留一条未映射记录，沿用现有诊断。任务字段的无效非零时间/缺失 guid 为来源失败，不伪装空。原任意状态迁移语义与 search 方式明确退役，历史结果保留，旧实现待 Task 16 以先失败测试替换。

字段依据：[官方 Python 清单请求](https://raw.githubusercontent.com/larksuite/oapi-sdk-python/v2_main/lark_oapi/api/task/v2/model/tasks_tasklist_request.py)、[TaskSummary](https://raw.githubusercontent.com/larksuite/oapi-sdk-python/v2_main/lark_oapi/api/task/v2/model/task_summary.py)、[官方 Go 模型与毫秒说明](https://raw.githubusercontent.com/larksuite/oapi-sdk-go/v3_main/service/task/v2/model.go)。SDK 版本间时间类型可能为整数或数字字符串，边界解析兼容这两者；这些资料不证明本租户已具备权限，真实授权与非空样本在 Task 18 验证。
- 现有机器人实现只检查旧 `StatusCode` 并默认缺失为 0；v1.2 按平台文档核对新 `code` 与旧字段，明确失败码、矛盾字段或缺失成功证据不能算成功。现有 SMTP 未处理 `send_message()` 返回的部分拒绝收件人，也列入 Task 17 的先失败测试。
- 来源的成员/顶层重复状态仍沿用 §3 的顶层约定；不趁本轮清理无关模型。Notifier 的“不确定发送”安全语义优先于旧的笼统重试规则，只作相关最小修订并补 CLI 回归。

## 2. 技术决策与 ADR

ADR-005（v1.2 已确认）：见 [`adrs/005-superpowers-tdd.md`](adrs/005-superpowers-tdd.md)，明确 Superpowers 是开发流程工具、SDD 文档是真实需求来源；实施计划审查后执行严格 RED/GREEN/REFACTOR、审查和完成前验证。新增浏览器操作沿用 §1.4 的轻量方案。

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
- v1.2 本机操作令牌与上游凭证分离；浏览器不能覆盖配置中的源平台 URL、仓库/群/任务清单、目标地址、库路径或时区。服务器配置变化要求重启和重新预览。
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

邮件、飞书推送分别执行并分别记录结果；单一渠道失败不影响另一渠道。存储失败视为本次执行失败并阻止误报成功；推送失败后保留生成的日报历史。v1.0 日报库本身不记录投递状态，v1.2 新增操作记录才保存受理/拒绝/部分拒绝/待核实；正常日志中的 success 不证明收件人收到。

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

### 8.2 v1.2 Superpowers / TDD 验证增量

1. 每个新增或修改行为先展示测试与业务意图，运行并记录因功能缺失产生的失败；确认 RED 后才写最小前后端业务代码，GREEN 后才能重构。已有复用模块不删除重写，也不谎称旧测试是本轮 RED。流程证据保存在 `docs/frontend/v1.2-tdd-log.md`。
2. pytest：操作鉴权/CORS/模式、请求校验、幂等/并发、后台终态/重启、只读回归、全部已启用来源失败；httpx MockTransport 验证真实适配器的分页/鉴权/字段/重试；SMTP 替身验证邮件内容和发送阶段故障，外部边界 Mock 不替代业务代码。
3. Vitest + Testing Library：令牌不持久化，生成/预览/确认与取消，日期/版本变化，disabled/空/失败来源，渠道独立结果，202/超时不冒充成功，断线不重交 POST。Playwright 使用真实本机 HTTP/SQLite 与受控上游边界验证操作链路和两个既有视口。
4. 每项任务 GREEN 后运行全部 Python/前端测试，披露所有失败/警告；最终运行 typecheck/build/Playwright。Python 总业务覆盖率 ≥90%；新增/修改前端业务模块四项覆盖率分别 ≥90%，执行阶段核验并锁定与现有 Vitest 匹配的官方 coverage provider，不引入第二套 Jest 测试框架。
5. 真实验收另行运行，不让 pytest/npm test 默认联机或发送。使用实际配置的工作日记录核对 GitHub、非空飞书任务与已过滤群消息；页面明确确认目标后发送日报，并分别核对邮件/群内收到。仅输出脱敏证据，真实日志和数据库不提交 Git。
6. 旧版本、离线测试、真实接口受理、实际收件四类证据分别标明；真实数据或权限不可用就是未完成验收。缺陷先进入失败回归测试，再最小修复。完整命令与结果写入 `docs/frontend/v1.2-acceptance.md`。
