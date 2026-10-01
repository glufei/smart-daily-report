# 智能日报生成器任务清单

- 版本：v1.2（2026-10-01）
- 状态：规范已确认；Task 1–14 历史完成；Task 15–18 待实施计划审查，尚未执行；v1.2 未验收
- 任务原则：一个任务对应一个可验证交付物；每项验收标准可观察且二值化。
- 执行依据：`proposal.md`、`design.md`、`contracts/`。

## 依赖 DAG

```text
Task 1 → Task 2 ─┬→ Task 3 ─┐
                 ├→ Task 4 ─┤
                 ├→ Task 5 ─┼→ Task 6 → Task 7 ─┐
                 │           │          Task 8 ─┤→ Task 9 → Task 10
                 └───────────┘                  ┘
```

Task 3、4、5、6 在 Task 2 完成后可并行开发，Task 7、8 在 Task 6 完成后可并行开发；Task 9 依赖所有运行模块，Task 10 依赖 Task 9。

v1.1 增量依赖如下；用户已确认整体规范、只读范围及技术方案，Task 11 已核实实际 OpenDesign 0.24.1 软件。

```text
用户确认 proposal → design/ADR-004/http-api → tasks
                          ├→ Task 11（OpenDesign UI 设计） ─┐
                          └→ Task 12（只读 HTTP） ─────────┴→ Task 13 → Task 14
Task 10（已完成） ──────────→ Task 12
Task 10/11/12（回归与验收证据） ───────────────────────────────────────→ Task 14
```

Task 11 与 Task 12 的产物相互独立，可按条件分别完成；Task 13 依赖二者验收，Task 14 依赖 Task 10–13。不在确认前安装设计工具/框架或创建前端代码。每项任务结束均 checkpoint：说明完成项、实际验证结果、未验证/失败项和剩余任务，未通过的 Checklist 不勾选。

## Task 1：项目骨架与配置样例

- **输入依赖**：`specs/design.md` §1、§4；`specs/contracts/interfaces.md`
- **输出文件**：`pyproject.toml`、`config.yaml.example`、`src/` 包骨架、`.gitignore`
- **交付物**：可安装的 Python 项目骨架及无秘密的配置模板。
- **验收 Checklist**：
  - [x] 源码包可由项目配置安装/导入。
  - [x] 运行时依赖声明包含 `httpx`、YAML 解析器及 HTML/Markdown 生成所需依赖。
  - [x] 配置样例含团队时区、节假日、数据源、关键词、推送目标和 GitHub/飞书账号映射键。
  - [x] 配置样例不含真实凭证或可用 Webhook。

## Task 2：Shared 基础层

- **输入依赖**：Task 1；`design.md` §4–§7；`contracts/`
- **输出文件**：`src/smart_daily_report/shared/config.py`、`identity.py`、`calendar.py`、`logging.py`、`errors.py`、`storage.py`、对应 `tests/unit/test_shared.py`
- **交付物**：可独立验证的配置、映射、工作日、安全过滤、JSON 日志与 SQLite 能力。
- **验收 Checklist**：
  - [x] 缺失必填配置和重复映射均返回明确失败，不启动采集。
  - [x] 未关联 GitHub 账号的历史提交仅按显式配置的作者名映射，已关联账号的提交优先使用 login；重复作者名映射导致配置失败。
  - [x] 周末和显式节假日被识别为非工作日，普通工作日识别为工作日。
  - [x] 命中敏感词的消息整体被过滤，测试证明原文不进入返回值、日志和存储。
  - [x] 日志每行均为可解析 JSON，包含时间、级别、事件和运行 ID。
  - [x] SQLite 可创建、写入、读取并按日期幂等处理日报。
  - [x] 上述行为有单元测试覆盖。

## Task 3：GitHub 提交采集器

- **输入依赖**：Task 2；`CommitRecord`、`CollectResult`；接口契约 §Collector
- **输出文件**：`src/smart_daily_report/collector/github.py`、`tests/unit/test_collectors.py`
- **交付物**：可注入 HTTP 客户端、可用 Mock 独立验证的 GitHub 采集器。
- **验收 Checklist**：
  - [x] 返回记录满足 CommitRecord 全字段类型契约并支持分页。
  - [x] 成功空响应返回 `success` 且零条记录。
  - [x] 网络超时/5xx 最多请求 3 次；耗尽返回 `failure`，不返回伪成功空结果。
  - [x] 仅 GitHub rate-limit 403 依据 reset 信息等待并重试；权限 403 不重试。
  - [x] Mock 测试覆盖成功、有分页、空结果、限流、重试耗尽及字段映射。

## Task 4：飞书任务采集器

- **输入依赖**：Task 2；`TaskRecord`、`CollectResult`；接口契约 §Collector
- **输出文件**：`src/smart_daily_report/collector/lark.py`、`tests/unit/test_collectors.py`
- **交付物**：独立飞书任务状态变更采集器。
- **验收 Checklist**：
  - [x] 返回记录满足 TaskRecord 契约并仅包含时间窗内状态变更。
  - [x] 正常无记录与来源失败返回不同状态。
  - [x] Token 过期时刷新一次并重放一次；仍失败返回 `failure`。
  - [x] 429/超时/5xx 按共享重试策略执行，耗尽后明确失败。
  - [x] Mock 测试覆盖字段映射、空结果、Token 刷新及失败。
  - [x] 分页令牌通过查询参数传递；`has_more` 为假时停止，重复令牌导致来源失败，避免重复采集和无限请求。

## Task 5：飞书消息采集与过滤

- **输入依赖**：Task 2；`MessageRecord`、`CollectResult`；接口契约 §Collector
- **输出文件**：`src/smart_daily_report/collector/lark.py`、`tests/unit/test_collectors.py`
- **交付物**：独立消息采集器，输出已按 allowlist 与 denylist 过滤的记录。
- **验收 Checklist**：
  - [x] 返回记录满足 MessageRecord 契约并按工作关键词过滤。
  - [x] 敏感词命中整条消息被丢弃，原文不进入日志、结果和 SQLite。
  - [x] Token 过期仅刷新及重放一次。
  - [x] 正常无匹配、采集失败可区分。
  - [x] Mock 测试覆盖关键词、敏感词优先级、Token 刷新和失败。

## Task 6：成员聚合与日报生成

- **输入依赖**：Task 2；数据模型与 Generator 契约（使用契约定义的 Mock CollectResult 开发及测试）
- **输出文件**：`src/smart_daily_report/generator/formatter.py`、`template.py`、`tests/unit/test_generator.py`
- **交付物**：确定性生成三段式 Markdown 与 HTML 的 Generator。
- **验收 Checklist**：
  - [x] 每个配置成员均出现，且三板块顺序固定。
  - [x] 有记录显示记录；成功空结果显示“今日无记录”；失败来源显示“数据获取失败”。
  - [x] 全部来源失败时不创建 DailyReport；至少一个来源成功时允许降级生成。
  - [x] Markdown 与 HTML 的内容和状态一致，外部文本正确转义。
  - [x] Mock 测试验证结构、状态差异、零记录成员和注入文本安全。

## Task 7：SMTP 邮件通知

- **输入依赖**：Task 6；`DailyReport` 与 Notifier 契约
- **输出文件**：`src/smart_daily_report/notifier/email.py`、`tests/unit/test_notifiers.py`
- **交付物**：可 Mock 的 HTML 邮件推送器。
- **验收 Checklist**：
  - [x] 邮件标题包含日期及团队名，正文为 DailyReport HTML。
  - [x] 暂时性发送失败最多重试 2 次；不可重试错误不重试。
  - [x] 返回投递状态、尝试数和安全错误码，不输出 SMTP 凭证。
  - [x] Mock SMTP 测试覆盖成功、重试成功、耗尽和凭证脱敏。

## Task 8：飞书机器人通知

- **输入依赖**：Task 6；`DailyReport` 与 Notifier 契约
- **输出文件**：`src/smart_daily_report/notifier/lark_bot.py`、`tests/unit/test_notifiers.py`
- **交付物**：可 Mock 的 Markdown 飞书推送器。
- **验收 Checklist**：
  - [x] 请求正文为日报 Markdown，目标来自配置。
  - [x] 暂时性发送失败最多重试 2 次；不可重试错误不重试。
  - [x] Webhook 不出现在日志及异常信息中。
  - [x] Mock 测试覆盖成功、失败重试及 Webhook 脱敏。

## Task 9：CLI 与管道编排

- **输入依赖**：Task 1–8；`run_report`、`run_health_check` 契约
- **输出文件**：`src/smart_daily_report/main.py`、`tests/unit/test_http_health_main.py`
- **交付物**：可从命令行执行、健康检查和 dry-run 的完整编排入口。
- **验收 Checklist**：
  - [x] 正常工作日按采集→映射/过滤→生成→存储→逐渠道推送顺序执行。
  - [x] `--check` 不生成、不存储、不推送；成功返回码为 0，失败返回非 0。
  - [x] `--dry-run` 执行采集和生成，但不推送。
  - [x] 非工作日跳过日报生成并记录结构化原因。
  - [x] 单来源失败不阻止其他来源；全部来源失败不生成日报。
  - [x] 邮件失败不阻止飞书发送，飞书失败不撤销邮件结果。
  - [x] 日志包含运行开始/结束、来源记录数/状态及渠道投递结果。

## Task 10：端到端集成与回归验证

- **输入依赖**：Task 9；全部模块与契约
- **输出文件**：`tests/integration/test_pipeline.py`、测试运行配置
- **交付物**：使用全 Mock 适配器验证业务意图的自动化集成套件。
- **验收 Checklist**：
  - [x] 全来源成功时生成、持久化并调用两种推送。
  - [x] 单来源失败时其他来源继续，日报显示对应失败标记。
  - [x] 正常空结果显示“今日无记录”，并与失败状态断言不同。
  - [x] 全来源失败时无日报存储/推送且退出为失败。
  - [x] 非工作日不触发采集、生成、存储或推送。
  - [x] 单渠道推送失败时另一渠道仍被调用且结果被分别记录。
  - [x] 性能基准 fixture 以 5 人 Mock 团队测量生成阶段小于 60 秒。
  - [x] `pytest` 一键运行全部测试成功；覆盖率报告达到项目约定阈值（首期目标不低于 90%，按业务代码统计）。

## 执行结果

以下为 **v1.0 历史执行结果**，不是本轮重跑结果，也不表示 v1.1 已交付。

- 完成 Task 1–10 的实现与 Mock 测试。
- 当前验证：64 项测试通过；总覆盖率 91.00%（高于 90% 门槛，Python 3.12.14）。
- Python 3.12 编译检查与 wheel 构建成功。
- 2026-09-26 真实租户端到端运行：2026-04-23 日报的 GitHub、飞书任务、飞书消息采集均成功；邮件与飞书 Webhook 投递均成功，用户确认两处收到，总耗时 4.875 秒。历史提交作者名映射已在线验证。飞书任务当天为零记录；多页及有记录响应由 Mock 覆盖，仍待真实数据验证。

## 执行顺序

建议顺序：Task 1 → Task 2 → Task 3/4/5/6（满足依赖后并行）→ Task 7/8（满足依赖后并行）→ Task 9 → Task 10。Task 6 的开发可用契约定义的 Mock CollectResult 开始，不需要等待外部 API 接入。

## Task 11：通过 OpenDesign 软件 UI 完成只读页面设计与迭代

- **输入依赖**：用户整体确认 v1.1 规范；`proposal.md` F01/F02/F03/F06；`design.md` §1.2；ADR-004；`contracts/http-api.md`。
- **执行前提**：核实实际 OpenDesign 软件来源/版本和 UI 可用性。安装或连接方式在执行时按已确认候选落实；不可用须报告，不用 CLI 或手写原型冒充 UI 迭代。
- **输出文件**：`docs/frontend/design-brief.md`、`docs/frontend/opendesign-evidence.md`、`docs/frontend/prototypes/`（初版、迭代版及 UI 操作/页面截图）、`docs/frontend/DESIGN.md`（布局、颜色、排版、状态文案与交接约束）。
- **交付物**：可追溯到 OpenDesign UI 的初版及至少一版迭代产物，不接真实数据，不写产品前端代码。
- **验收 Checklist**：
  - [x] F01：记录软件来源、版本/提交、许可证及 UI 运行证据；初版、迭代版输入和导出文件均可定位。
  - [x] F01：至少一处用户可见修改有前后截图及修改依据，可核对确由 OpenDesign UI 迭代完成。
  - [x] F02/F03：原型包含日期输入、团队/生成时间、全部成员三板块，以及加载、无日报、查询错误、正常空记录和来源失败状态，逐项有截图或状态展示。
  - [x] F06：375×812、1440×900 设计产物可打开检查，无页面级横向溢出；控件名称与键盘交互要求写入交接文档。
  - [x] F05：输入/产物仅含虚构 fixture，无真实消息、凭证或生产数据库；无生成、推送、编辑、管理等越界控件。

## Task 12：新增复用 SQLite 的只读 HTTP 适配层

- **输入依赖**：用户整体确认 v1.1 规范；Task 2/6/9/10（已完成）；`design.md` §1.2–§1.3；`contracts/http-api.md`；F02/F03/F04/F05/F07。
- **输出文件**：`src/smart_daily_report/web/__init__.py`、`app.py`、`schemas.py`、`main.py`；必要的 `shared/storage.py` 读取改动、`pyproject.toml` 可选依赖和启动入口；`tests/unit/test_web_api.py`、必要的现有存储测试补充；`docs/frontend/local-run.md`。
- **交付物**：`daily-report-web --database <SQLite路径>` 的本机启动入口及唯一业务 GET 查询接口，已实现。
- **验收 Checklist**：
  - [x] F02：临时库中有效日报 GET 返回 200，字段、顺序、时间、来源状态与 HTTP 白名单契约一致；正常空记录和单来源失败均可查询。
  - [x] F03：严格非法日期为 400（含紧凑日期和非法日历日），未保存日期/不存在库/正确空表为 404，缺表/损坏/读取失败为 500；无效 JSON/状态/类型为 500，错误码符合契约且不泄漏路径/正文/堆栈。
  - [x] F04：读取使用 SQLite 只读模式；请求前后数据相同且不存在库不被创建；禁用 Collector/Generator/Notifier/write_report 的替身仍能完成 GET，证明查询无生成/通知副作用；写方法为 405。
  - [x] F05：响应仅含允许字段，不包含配置/秘密/外部用户 ID/已过滤敏感正文；恶意协议 URL 被转为 null，未知/缺失来源状态不被补成成功。
  - [x] F05：入口仅绑定 loopback，无源平台/SMTP 凭证也可查询；Origin/Host 按契约处理，业务响应含 no-store，未允许 Origin 为 403。
  - [x] F07：Python 基础安装不依赖 Web 框架，CLI 不导入 Web 模块；相关新增测试与既有存储/CLI 测试通过，启动说明能在 Windows 按步骤复现。

## Task 13：实现 React 只读页面并接入真实查询接口

- **输入依赖**：Task 11、Task 12 验收通过；`docs/frontend/DESIGN.md`；`contracts/http-api.md`；F02/F03/F05/F06。
- **输出文件**：`frontend/` 的 Vite React TypeScript 工程、`package-lock.json`、页面/状态组件、API DTO 与请求模块、样式；`frontend/src/` 中相关 Vitest/Testing Library 测试；更新 `docs/frontend/local-run.md` 和设计交接证据。
- **交付物**：中文单页，用户明确选择日期再查询，显示真实只读接口结果；原型与实现差异可追溯。
- **验收 Checklist**：
  - [x] F02：查询 fixture 日期后展示保存的团队名、日期、带时区生成时间、完整成员及固定三板块；零记录与来源失败各自使用规范文案。
  - [x] F03：加载、404 无日报、400 输入错误、500 查询错误、网络失败、10 秒超时与无效 JSON 有对应状态测试；错误不展示“今日无记录”，不自动重试。
  - [x] F03：快速依次查询日期 A/B，A 的迟到响应不能覆盖 B；切换/失败不遗留上一日期的内容，取消请求不误报新请求失败。
  - [x] F05：外部文本作为文本展示，恶意 HTML 不执行且非 HTTP(S) 链接不可点击；浏览器只请求本项目只读 API，无真实凭证或数据库路径进入构建产物。
  - [x] F06：375×812、1440×900 下无页面级横向溢出；日期/查询/重新查询有可访问名称，可键盘使用；页面保留 Task 11 确认的设计并记录必要差异。
  - [x] F06：`npm ci`、`npm run typecheck`、`npm run build`、`npm run test -- --run` 均退出 0；Node 要求、依赖版本和 loopback 开发/预览方式已记录。

## Task 14：前后端验收与 v1.0 回归

- **输入依赖**：Task 10–13 完成；`proposal.md` F01–F07 与全部 v1.0 验收语义。
- **输出文件**：`frontend/e2e/` Playwright 测试与运行配置、必要的 Python 集成测试补充、`docs/frontend/acceptance.md`（规范→测试/证据映射、命令与结果、截图及限制）；更新任务完成记录。
- **交付物**：真实本机 API + 临时 SQLite + 前端的验收证据，测试不访问真实 GitHub/飞书/SMTP，不依赖 OpenDesign 运行时。
- **验收 Checklist**：
  - [x] F01：OpenDesign UI 来源、初版/迭代版和至少一处修改的完整证据可审阅，每项记录可定位到文件，不仅口头声明。
  - [x] F02/F03：浏览器经真实 HTTP 查询 fixture，验证正常日报、零记录、单来源失败、无日报、API 存储错误及离线；接口错误从不伪装为空日报。
  - [x] F04/F05：集成验收查询前后 SQLite 内容相同且无采集/推送调用；恶意内容/链接 fixture 安全；敏感标记和秘密不出现在 API/页面/正常日志中。
  - [x] F06：Playwright 在两个约定视口通过，键盘操作和日期竞态测试通过；前端类型检查、构建、全部单元及浏览器测试均退出 0。
  - [x] F07：全部 Python 测试退出 0，业务代码覆盖率 ≥90%；基础 CLI 安装/导入检查通过，Task 10 的核心场景仍通过。
  - [x] F01–F07：验收记录逐项链接测试或人工证据，列明真实执行的命令和结果；所有未验证/失败项公开记录，只有全部通过才将 Task 11–14 和 v1.1 标记完成。

## v1.1 当前 checkpoint

2026-09-30：用户确认后依次完成设计与接口适配、页面、联调验收。Task 11：OpenDesign 0.24.1 真实 UI 两轮生成，28 项原型检查通过；原型手机留白及未成功提交额外 UI 修正公开记录，产品已修复。Task 12：98 项 Python 测试、92.02% 覆盖率，基础 CLI 导入/运行及真实本机 HTTP 通过。Task 13：npm ci、typecheck、build 和 15 项 Vitest 通过。Task 14：真实 API/临时 SQLite 的 14 项 Playwright 两视口验收退出 0，数据库不变，无生成/采集/通知调用，生产预览通过；首轮清理退出失败与上游提示均有记录。完整映射见 docs/frontend/acceptance.md。Task 1–10 历史结果保留，本轮未访问外部真实数据源。

## v1.2 开发门槛与增量依赖

本轮使用 Superpowers 6.4.2；`proposal.md` R01–R12、`design.md` §1.4–§1.5/§8.2、ADR-005、`contracts/web-operations.md` 是执行依据。按用户指定先提供规范审查，不在审查前新增测试/业务代码、安装产品依赖或运行真实通知。

```text
v1.2 proposal → design/ADR-005/contracts → 本任务清单
       ↓ 用户审查规范
Superpowers writing-plans → 实施计划审查/选定执行方式
       ↓
Task 14（历史基线） → Task 15（操作基础 + GitHub 生成预览）
       → Task 16（飞书任务/消息） → Task 17（SMTP/飞书独立推送）
       → Task 18（真实浏览器验收与完整回归）
```

以上是依赖顺序，不宣称顺序本身保证质量。任务按交付物与失败测试迭代；每个新增/修改业务行为必须经历 RED → 验证失败原因 → GREEN → 全套回归 → 必要重构。测试代码与实际 RED 结果先展示给用户，再写实现。所有任务结束 checkpoint，包含实际命令/退出码、覆盖率范围、失败/警告、未验证项、剩余任务；验收项全部可判定通过/未通过。

新增文件路径为计划的交付归属；规范确认后 writing-plans 再锁定测试代码、函数签名、运行命令与步骤，计划审查通过后才实现。不得凭本清单跳过先失败证据或用已有 98 项通过记录冒充新增 RED/GREEN。

## Task 15：真实 FastAPI 操作基础与 GitHub 数据生成、预览

- **前置依赖**：Task 2/3/6/9/12/13/14 历史产物；用户确认 v1.2 规范与实施计划；选定 Superpowers 执行方式。
- **输入契约**：R01/R02/R04/R05/R07/R08/R10；`web-operations.md` §1–§5；既有 Collector/RunResult/ReportView。
- **计划输出**：`web/main.py`、`app.py`、`schemas.py` 的最小适配；新增 `web/operations.py`、`shared/operation_storage.py`；必要的 `main.py`/`shared/models.py`/`config.py` 增量；`frontend/src/operations.ts` 及复用 `App.tsx` 的令牌输入/生成预览交互；Python 操作单元/集成测试、前端操作测试；`docs/frontend/v1.2-tdd-log.md`。
- **交付物**：本机鉴权、操作记录、幂等、生成/状态/预览接口和可操作页面；真实运行可使用配置的 GitHub，生成不发送。飞书端到端契约由 Task 16 验证，推送控件/接口由 Task 17 启用。
- **验收 Checklist**：
  - [x] **严格遵循 TDD，必须先编写失败的单元/集成测试用例，再实现通过测试的业务代码。** GitHub 操作/鉴权/记录/前端交互的每个新行为都有正确原因的 RED 命令、非零退出码和 GREEN 记录，测试先展示并运行，未先失败不得写业务代码。
  - [x] 原 `--database` / 前端默认 readonly 模式仍不加载凭证、不创建操作库、不显示操作控件，写方法不可用；`--config` 配套前端 operations，缺令牌/错误配置启动失败。401/未允许 Origin 的 403/合法预检均符合契约；拒绝请求前后无业务或文件变化。
  - [x] GitHub 集成测试通过真实采集器与受控 HTTP 边界，从生成 POST→状态→SQLite→预览完整流转；SHA/成员/时区/提交详情统计与源响应一致，无 Mock 回退。POST/页面生成与所有 GET 均无 SMTP/机器人发送。
  - [x] 同键同内容仅调用生成一次；同键不同内容 409；已有活动操作的新请求 409。已接受记录先于 202 落盘，后台异常落安全终态并释放槽；重启不自动重放，状态/幂等键/current GET 无写业务副作用；页面刷新后可重新认证并恢复观察已有操作。
  - [x] 先失败测试覆盖“只启用 GitHub 且它失败”“未启用任何来源”“非工作日”：不生成、不覆盖旧历史、不通知；来源 disabled 与失败/成功零条可区分。成功生成的 ReportView 保持旧三键状态兼容。
  - [x] 预览版本摘要按契约计算；前端按实际 HTTP/Zod 解析，202/轮询超时不是生成成功；断线先查原 request_id，不自动重交。A/B 日期及旧响应不能覆盖新日期预览，操作令牌不进入 URL/持久存储/构建输出/日志。
  - [x] pytest 与前端全部现有/新增单元测试退出 0；记录 Python 覆盖率 ≥90%、本任务前端业务四项覆盖率各 ≥90%；typecheck/build 通过；checkpoint 公开真实 GitHub 联调尚未由本任务离线测试证明。

## Task 16：真实飞书任务、群消息接入与页面状态一致性

- **前置依赖**：Task 15 验收；Task 4/5 既有适配器；测试租户的接口/权限资料可核对，真实非空任务验收留在 Task 18。
- **输入契约**：R02/R03/R08/R10；Collector/TokenProvider；`design.md` §1.5；`web-operations.md` §3/§6。
- **计划输出**：`collector/lark.py`、`shared/http.py`、必要配置/模型增量；`tests/unit/test_collectors.py`、新的操作集成测试；前端来源/任务/消息状态测试及仅在需要时的最小展示改动；`docs/frontend/v1.2-upstream-contracts.md`；更新 TDD 日志。
- **交付物**：生成操作复用真实飞书适配器，页面正确展示同一次生成的任务/消息和来源结果；接口字段、Token 类型、身份映射与权限有明确依据。
- **验收 Checklist**：
  - [ ] **严格遵循 TDD，必须先编写失败的单元/集成测试用例，再实现通过测试的业务代码。** 实际接口字段/分页/刷新/状态展示的新增或修改行为都有先展示测试、真实正确 RED 与 GREEN；仅复用未修改能力如实标明，不伪造其 RED。
  - [ ] 保存所用官方接口/SDK 字段依据、Token 类型与必需权限；任务清单/群来源只从服务器配置取得。浏览器请求/响应不含 App Secret、上游 Token、群凭证或外部用户 ID，授权失败不伪装空记录。
  - [ ] tenant Token 对已授权 tasklist GUID 发清单 GET，参数/分页符合官方契约；按 completed_at 毫秒及配置时区筛选所选日期完成任务。0、仅标题更新、日期外任务不计入，非法字段为 failure；多 user/assignee 负责人分别映射并按任务/负责人去重，完成时间与页面一致，不编造前态。旧 search 配置明确拒绝并给出迁移说明，不静默沿用。
  - [ ] 任务和消息分页正常完成；缺失/重复下一页令牌为明确来源失败，不无限循环或提交部分成功。Token 失效仅刷新一次并重放一次，再失败明确返回 failure；权限错误不重试为成功。
  - [ ] 生成操作的 GitHub 成功/飞书失败仍保存降级日报；所有已启用来源失败不生成；未启用来源显示未启用。页面正常零条/来源失败/未启用有不同文案，三板块内容与保存数据一致。
  - [ ] 关键词/敏感词规则按既有优先级执行；敏感原文不进入生成结果、日报/操作库、响应、页面或正常日志，外部 HTML/协议安全；生成与 GET 不发送通知。
  - [ ] 全部 Python/前端单元测试退出 0，覆盖率门槛、typecheck/build 通过；checkpoint 列出真实接口验证与非空样本是否已具备，不以 Mock 通过声称租户接入完成。

## Task 17：预览后真实 SMTP/飞书独立推送与结果交互

- **前置依赖**：Task 15/16 验收；Task 7/8 既有 Notifier；R05/R06/R07；固定服务器目标与 `web-operations.md` 推送契约。
- **计划输出**：`web/operations.py`/`schemas.py`、操作记录增量、`notifier/email.py`/`lark_bot.py`、兼容 DeliveryResult/config/CLI 的必要最小修订；`frontend/src/operations.ts`、`App.tsx` 及必要样式；Notifier/Web 单元/集成、前端推送交互测试；更新 TDD 日志。
- **交付物**：用户查看已保存日报及目标摘要、选渠道确认后只推送该版本；分别显示两渠道受理/拒绝/部分拒绝/待核实，不重新采集。
- **验收 Checklist**：
  - [x] **严格遵循 TDD，必须先编写失败的单元/集成测试用例，再实现通过测试的业务代码。** 推送 API、版本校验、渠道故障、前端确认/取消的测试先提供并运行 RED；SMTP 部分拒绝和机器人非零业务码也先复现失败，再最小修复，保留 GREEN/回归证据。
  - [x] 预览只读显示服务器固定目标摘要；取消确认发送零次。选择未配置渠道为 400，日期不存在为 404，版本改变/已接受或待核实渠道重复推送为 409，拒绝请求发送零次且不重新采集。
  - [x] 邮件内容来自确认的同一 DailyReport HTML，机器人卡片来自其 Markdown；双渠道使用同一捕获版本，只有所选渠道被调用。某渠道明确失败/异常不阻止另一选定渠道，结果分别持久化，历史日报保留。
  - [x] SMTP 登录/连接不能记发送成功；处理全部接受/全部拒绝/部分收件人拒绝和发送后响应不明。飞书同时核对真实业务码约定；HTTP 200 非零 code/缺失成功证据/矛盾字段不算 accepted，不发生默认成功。
  - [x] 重复幂等请求只发送一次；明确拒绝的失败渠道可单独显式重提，不连带成功渠道。已接受/部分已接受/unknown 不整渠道重发，发送后读超时/断线不自动重交；进程中断按契约标记待核实，不自动恢复发送。
  - [x] 页面分别展示推送中/渠道结果及“已接受≠实际收到”；生成按钮、历史查询、刷新、状态查询、关闭页面不触发发送。确认与取消可键盘操作，日期/版本切换使旧确认失效；令牌和 Webhook 不泄漏。
  - [x] 现有 CLI 兼容与全部 Python/前端单元测试退出 0，覆盖率门槛/typecheck/build 通过；checkpoint 声明离线 SMTP 替身/HTTP 响应不等于真实双渠道收件，后者需 Task 18 证据。

## Task 18：真实浏览器运行、双渠道收件与完整回归交付

- **前置依赖**：Task 15–17 验收；v1.1 历史设计证据；用户实际可读源数据与配置目标；R01–R12。
- **计划输出**：`frontend/e2e/` 操作联调测试与必要 Python 集成测试/运行脚本；`docs/frontend/v1.2-acceptance.md`、`v1.2-upstream-contracts.md`、`v1.2-tdd-log.md`、脱敏截图；更新 README/运行说明/版本和任务 checkpoint。
- **交付物**：可复现的真实操作启动、完整自动化回归、真实源数据核对和邮件/飞书群实际收到的验收记录；未完成项不得补勾。
- **验收 Checklist**：
  - [ ] **严格遵循 TDD，必须先编写失败的单元/集成测试用例，再实现通过测试的业务代码。** 新增运行/联调行为与本阶段发现缺陷先有正确原因的 RED，再业务修改、GREEN 与完整回归；只运行既有代码的验收如实记录，不虚构先失败。
  - [ ] Playwright 通过真实 FastAPI/SQLite 操作链路验证生成不发送、预览/确认/取消、独立渠道结果、鉴权失败、日期竞态、断线不重交与去重；375×812、1440×900 无横向溢出，键盘流程通过。受控上游边界与真实外部联调分别标记。
  - [ ] 用操作模式与真实配置启动，不运行 fixture 服务：选择确有数据的工作日生成，页面 GitHub SHA/成员/日期/统计、至少一条真实飞书任务及安全群消息与源平台一致，SQLite/页面状态一致；无权限或缺非空任务样本该项不通过。
  - [ ] 用户确认同一日报版本、邮件目标摘要和飞书目标后发送；记录服务商响应的安全结果并核对邮件收件箱、群内对应内容实际收到。202/HTTP 200/SMTP 连接/历史 v1.0 收件记录均不能代替此次两处收件证据。
  - [ ] 生成耗时与源平台限流/失败记录明确，不把 Mock 性能当真实网络保证；整个过程中秘密/敏感原文不入仓库或正常日志，真实数据库/配置继续被忽略。
  - [ ] 全部 pytest 退出 0、总业务覆盖率 ≥90%；前端全部单元/浏览器测试、typecheck/build 退出 0，新增/修改业务模块四项覆盖率各 ≥90%；基础 CLI 安装和旧 GET 只读回归通过，失败/警告无遗漏。
  - [ ] README 明确只读/真实操作/fixture 的启动、环境变量名、前端操作令牌输入、外部权限、工作日选择、状态不明处理与停止方式；版本号只在实现和验收后更新为 1.2.0。
  - [ ] R01–R12 逐项映射实际测试和真实证据，Task 15–18 每项有 checkpoint；无数据/权限/网络/收件证据时标记具体未完成项。全部通过后才将 v1.2 标记完成并按用户授权交付 Git。

## v1.2 当前 checkpoint

2026-10-01：已读取现有规范、React/FastAPI/CLI 与采集/推送实现，用户选择“先生成预览，再独立推送”。本轮只更新待审规范/契约/ADR 和未完成任务，尚未编写测试或业务代码、安装依赖、调用真实平台或发送通知。Superpowers 实施计划在规范确认后编写并审查；Task 15–18 均未开始。

2026-10-01 后续 checkpoint：用户已确认 v1.2 规范，并选择“读取已授权任务清单，展示所选日期完成的任务”。该范围已从 proposal 向 design、数据模型/内部/HTTP 契约及 Task 16 同步；旧 Task 1–14 记录未改。实施计划已形成，待用户审查/选定执行方式；现有基线 Python 98 passed、覆盖率 92.02%，前端 15 passed（均退出 0），不算新增 TDD 或真实联调证据。未写业务/测试实现、未发送通知；Task 15–18 保持未完成。

2026-10-01 实现 checkpoint：用户已确认计划/Native执行/隔离工作区；Task15 离线实现验收通过，Task16 代码和离线测试通过（pytest197/93.72%，frontend73，四模块每文件四项≥90，typecheck/build0）。Task16具体租户权限/非空实际样本仍待Task18核对，真实验收不勾选；Task17/18尚未完成，版本仍1.1.0。无真实通知。详见TDD日志及上游契约记录。

2026-10-01 Task17 checkpoint：SMTP/机器人明确受理分类、固定版本推送、逐渠道落盘、React确认/取消与恢复已完成离线验证。pytest249/94.57%，frontend95每文件四项≥90，typecheck/build0。jsdom不能证明键盘模态；Task18浏览器验证及真实权限/非空样本/双渠道实际收件仍未完成，无真实通知。
