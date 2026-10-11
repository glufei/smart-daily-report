# v1.2 本机生成、预览与推送 HTTP 契约

- 版本/状态：v1.3.1；§1–6 描述 v1.2 操作 API 的兼容基线，§7 描述 v1.3 已实现并验收的操作反馈与可选邮件目标。
- 维护：Task22 的计时器 ticket 隔离和飞书 sender 输入校验已实现并验收，不增加 API 端点、字段或状态码；v1.3.0 历史合约与证据保持不变。发布记录见 `docs/frontend/v1.3.1-release.md`。
- 上游：`proposal.md` R01–R12；`design.md` §1.4–§1.5；ADR-005
- 兼容基线：[`http-api.md`](http-api.md) 的 GET / ReportView 不变；所有本文件新接口仅在操作模式启用

## 1. 认证、跨域和启动

- `--database <path>` 为原只读模式；`--config <path>` 为操作模式，两者互斥。配置一次加载，日报库来自 RunConfig，操作记录库为同目录 `<日报文件名>.operations.sqlite3`。默认只绑定 127.0.0.1:8000、单 worker、无 reload。
- 操作模式要求服务端环境变量 `DAILY_REPORT_WEB_TOKEN` 至少 32 字符，缺失/空白/不足或配置错误在启动时失败。令牌由维护者生成/注入，不自动回显，不作为命令行参数；前端密码输入仅存内存。
- 本文件所有 GET/POST 均要求 `Authorization: Bearer <本项目操作令牌>`；非本机 Host 拒绝，未允许 Origin 为 403，正确 Origin 但缺失/错误 Token 为 401。无 Origin 请求也校验 Token。旧历史 GET 保持原只读认证边界。
- 允许 Origin 恰为 `http://127.0.0.1:5173` / `http://127.0.0.1:4173`；操作模式 CORS 方法 GET/POST/OPTIONS，允许头 Authorization/Content-Type/Idempotency-Key，不使用 Cookie 或通配 Origin。合法 OPTIONS 预检不要求 Token，不触发配置加载之外的业务动作。
- 请求/响应为 application/json；所有响应 no-store。成功与错误响应均保留允许 Origin 的 CORS 头，页面须能读取 401/409 等错误；错误不返回秘密/路径/堆栈/上游正文。
- 前端公开配置 `VITE_API_MODE` 仅允许 readonly/operations，默认为 readonly；它只控制界面，不代替后端鉴权。进入 operations 并认证后读取 current，恢复运行状态；此配置不是秘密，不能顺带传入上游凭证。
- POST 的 Idempotency-Key 必填，格式 UUID v4；不能用日期替代键。Body 拒绝未列明字段，所有日期严格合法 YYYY-MM-DD，枚举严格校验；统一校验错误 400，不能混用默认 422。

## 2. 路由

| 路由 | 正常 HTTP | 输入/用途 |
|---|---|---|
| `POST /api/v1/generations` | 202 | `{"report_date":"2026-09-25"}`；采集、生成、写历史，绝不通知 |
| `GET /api/v1/operations/{operation_id}` | 200 | UUID；读取已接受操作及其结果，绝不执行任务 |
| `GET /api/v1/operations/by-key/{request_id}` | 200 | Idempotency-Key；POST 响应丢失时确认是否已接受 |
| `GET /api/v1/operations/current` | 200 | 当前活动操作，若无则最近接受的操作；均无时为 null；刷新后恢复观察 |
| `GET /api/v1/reports/{report_date}/preview` | 200 | 已保存日报白名单视图、版本摘要、配置目标摘要及本版本已有渠道结果 |
| `POST /api/v1/deliveries` | 202 | 日期、预览版本、选定渠道；只发送此日报快照 |

操作路由不存在/非法 ID 返回固定 400/404，不输出 SQLite 记录原文。current/by-key 静态路径必须先于动态 ID 路径匹配。current 返回 OperationView 或 null，最近顺序按 created_at、operation_id 确定，不执行/续跑任务。POST 成功响应为 OperationView，202 表示接受或相同请求仍在运行；相同键的已完成操作重放为 200 返回原终态，不能重新执行。

推送输入示例（虚构）：

```json
{
  "report_date": "2026-09-25",
  "report_revision": "<64位小写SHA-256十六进制>",
  "channels": ["email", "lark"]
}
```

`channels` 为非空、不重复数组，仅 email/lark；规范化时按固定 email/lark 顺序。浏览器不得传收件地址、Webhook、上游 Token、消息正文、数据库路径、采集 URL、配置路径或强制重发选项。任意有效日期均可生成和推送，无需日期例外标志。

## 3. DTO 与状态

### OperationView

| 字段 | JSON 类型/约束 |
|---|---|
| `operation_id` | UUID v4 字符串 |
| `request_id` | 原 Idempotency-Key，UUID v4 |
| `kind` | generation / delivery |
| `report_date` | YYYY-MM-DD |
| `status` | running / succeeded / partial_failure / failed / skipped / unknown / interrupted |
| `created_at`、`updated_at` | 带时区 ISO 8601 |
| `report_revision` | 64 位小写 SHA-256 或 null；生成尚未成功/未生成时 null |
| `sources` | 恰有 github_commits/lark_tasks/lark_messages；生成操作为 SourceOutcome，推送操作三项均为 null（不重新采集） |
| `deliveries` | 恰有 email/lark，为 DeliveryOutcome |
| `error_code` | 固定安全错误码或 null |

SourceOutcome：`{"status":"pending|success|failure|disabled","error_code":null或固定错误码}`。禁用由服务器配置决定；pending 仅用于未完成来源，不能映射成空记录。内部 RunResult 增加可兼容的来源结果交接（见 interfaces.md），不直接返回 CollectResult.records/message 或内部诊断原文。

DeliveryOutcome：`{"status":"not_requested|pending|accepted|rejected|partial_failure|unknown","attempts":非负整数,"error_code":null或固定错误码}`。not_requested 的 attempts 为 0；pending 仅用于选定但尚无终态的渠道。partial_failure 表示 SMTP 已接受部分收件人、拒绝其他收件人，不可整渠道重发。unknown 表示缺少可证明受理/拒绝的结果，不能显示“失败，可放心重发”。

生成只要至少一个已启用来源成功且持久化成功，就为 succeeded 或 partial_failure（另一个已启用来源失败）；所有已启用来源失败为 failed/all_sources_failed，无日报版本。任意有效日期（包括周末和 `team.holidays` 配置中的日期）均执行相同采集流程，不新建 `skipped/non_workday` 结果。配置无来源或必需凭证缺失在启动时失败。

推送所有选定渠道 accepted 才为 succeeded；任一 unknown 为 unknown（其他渠道保留各自结果）；有 accepted/partial_failure 且另有拒绝或同渠道部分拒绝为 partial_failure；全部明确拒绝为 failed。未选渠道 not_requested，不把其未调用当失败。启动恢复的未完成项为 interrupted；生成不自动恢复，推送 pending 渠道保守记 unknown，不重放。

### PreviewView

```text
report: ReportView（复用 v1.1 完整白名单字段）
report_revision: 64位SHA-256
sources: 生成该版本时的SourceOutcome三键对象 | null
targets:
  email: {enabled: boolean, label: string, previous: DeliveryOutcome | null}
  lark:  {enabled: boolean, label: string, previous: DeliveryOutcome | null}
```

targets.label 为配置目标的安全摘要（邮件收件人数/脱敏地址，飞书为配置的日报群标签）；绝不返回 Webhook、密码或可编辑目标。操作模式允许未配置某个渠道，显示 disabled；选择该渠道 POST 返回 400。整个 SMTP 配置块缺失/为空视为邮件未启用；提供了配置块却缺少 host/sender/非空 recipients，或 TLS 模式/登录必需参数不合法，则启动失败，不能静默禁用掩盖错误。因此需在执行阶段以失败测试最小修订既有全量配置校验，不能让未启用邮件阻止只生成。

sources 来自同日期且同 report_revision 的生成记录；旧 CLI 历史没有此元数据时为 null，页面只声明“来源启用情况未记录”，不能套用现在的配置改写过去来源。previous 取同版本渠道的最新已记录结果，无记录为 null，页面显示“无本轮推送记录”，不能声称从未推送过旧历史。

摘要基于内部 DailyReport 所有字段的规范 JSON：dataclass 递归转换、键排序、separators=(',',':')、ensure_ascii=False、ISO 8601 日期/带时区时间，UTF-8 编码后 SHA-256；数组顺序保留。它是版本一致性标识，不能当作鉴权 Token。

## 4. 排他、幂等和发送时机

1. 先验证 Origin/鉴权/输入，再在 SQLite 事务中查同键。规范化请求指纹包含 kind、日期，以及推送的版本/排序渠道；不包含 Token。已存在同键同指纹返回原记录；同键不同指纹为 409，不改变原状态。
2. 无同键时，若有任意活动操作返回 409 operation_busy；不排队，不取消前一次操作。检查推送日报是否存在/有效、版本和渠道是否匹配，防止页面确认后内容改变；不检查星期或节假日。
3. 推送前检查每个选定渠道在同日报版本的既有记录；accepted/partial_failure/unknown 或中断后的 unknown 禁止重发，返回 409 delivery_not_repeatable。明确 rejected 可在用户查看结果后用新键单独选择该渠道重提；不能附带重发成功渠道。
4. 将运行记录与活动槽原子持久化，再返回 202 并执行后台函数。后台推送使用已校验并捕获的 DailyReport 快照，调用前持久化选定渠道为 pending；无论异常均写安全终态并释放活动槽。渠道结果必须在开始另一渠道前落盘，进程在发送后写结果前崩溃则恢复为 unknown。
5. POST 响应丢失不表示操作未执行。前端保留该次 request_id，先 by-key 查询；未确认前不产生另一键重交。by-key 404 只表示尚无接受记录，前端可由用户显式重试**同键同内容**，禁止自动重发。刷新后可重新读取预览的渠道记录，服务端重复检查仍生效。
6. 前端操作状态 GET 间隔 2 秒，最多自动观察 120 秒后停止轮询并提供“查询执行结果”；这不是后端失败/取消期限。日期切换、AbortController、关闭页面只停止浏览器等待，不取消已接受后端任务；用户重新认证后可查询结果。
7. 本轮不支持多实例/跨进程 Web 调度、强制取消或恢复中断任务；既有 CLI 不加入 Web 活动槽。CLI 覆盖同日期历史时，版本校验防止发送未确认新内容，推送已捕获快照保持不变。

## 5. 错误与异步业务结果

即时拒绝使用旧安全信封 `{"error":{"code":"...","message":"..."}}`；已接受后的业务失败通过 HTTP 200 的 OperationView.status/error_code 表达，不把后台失败变成 HTTP 500 或成功日报。

| HTTP / code | 固定 message / 语义 |
|---|---|
| 400 / invalid_request | 操作参数无效 |
| 400 / invalid_report_date | 日期无效，请使用 YYYY-MM-DD |
| 400 / channel_not_configured | 所选推送渠道未配置 |
| 401 / operation_unauthorized | 操作令牌无效或未提供 |
| 403 / origin_not_allowed | 请求来源未允许 |
| 404 / report_not_found | 该日期尚无日报 |
| 404 / operation_not_found | 未找到该操作记录 |
| 409 / idempotency_conflict | 同一请求标识不能用于不同操作 |
| 409 / operation_busy | 已有操作正在执行，请先查看其结果 |
| 409 / report_revision_changed | 日报已更新，请重新预览后推送 |
| 409 / delivery_not_repeatable | 该渠道已接受或结果待核实，不能重复推送 |
| 500 / storage_read_failed | 日报读取失败，请稍后重新查询 |
| 500 / invalid_report_data | 日报数据格式异常 |
| 500 / operation_storage_failed | 操作记录不可用，未接受新操作 |
| 500 / internal_error | 操作请求处理失败 |

即时 500 或响应丢失可能发生在持久接受之后，页面一律查询原 request_id，不据此自动重交。新操作的错误码为 all_sources_failed/source_auth_failed/source_unavailable/source_payload_invalid/report_write_failed/delivery_rejected/delivery_partial/delivery_unknown/operation_interrupted/internal_error；旧持久化操作中的 `non_workday`/`skipped` 仅为历史兼容，不会由当前实现新建。映射由确定性代码维护，禁用上游错误正文透传。

## 6. 上游真实性与验证边界

- GitHub 请求由现有采集器发出，按服务器配置 repo/date/timezone 分页和读取提交详情；核对 SHA、作者映射、时间、文件统计。权限失败和成功零记录分开，部分分页失败不能提交部分成功记录。
- 飞书任务采用 tenant Token 读取已授权清单 GET，仅按 completed_at 展示所选日期完成的任务，具体参数与多负责人语义见 interfaces.md/data-models.md。普通更新时间不能证明完成，0/日期外记录不展示，不编造前态；重新打开任务不复原旧完成事件。任务/消息覆盖有效 Token、一次刷新/重放、正常空、权限拒绝及重复分页令牌；权限与非空完成样本须真实核对。
- 机器人成功必须有明确合法业务成功码；HTTP 200 的非零 code、缺字段、矛盾字段和非法 JSON 不算 accepted。缺少可信响应时保守 unknown，不自动再发。
- SMTP 检查所有配置收件人的受理结果；连接/login 成功不是发送成功，send_message 部分拒绝不能算全渠道 accepted。发送之后的超时可能已受理，保守 unknown；只在可证明未发送的暂时错误上重试。
- 离线 pytest/Vitest/Playwright 通过不证明真实集成完成；真实验收需源数据核对和两个通知目标实际收件证据。任何无样本/权限不足/网络失败保留未完成，不用旧记录替代。

## 7. 下一轮增量：可选邮件目标与交互反馈（2026-10-11，已实现，完整回归及独立审查修复完成，交付流程为PR#4 → main → v1.3.0）

### 7.1 PreviewView 与地址可见范围

路由与鉴权保持。`targets.email` 保留 enabled/label/previous，增加必需字段 `recipients: list[str]`，内容来自服务器 smtp.recipients，按配置顺序去重；未启用邮件时为空。仅认证后的预览返回实际邮箱，不返回 SMTP 凭证，不在公共历史 GET、错误正文或日志展示。`targets.lark` 保持原结构及固定标签。

虚构示例：

```json
{
  "email": {
    "enabled": true,
    "label": "邮件（2 位可选收件人）",
    "previous": null,
    "recipients": ["member@example.com", "mentor@example.com"]
  },
  "lark": {"enabled": true, "label": "配置的日报群", "previous": null}
}
```

`previous` 仍是邮件渠道同版本最近结果，不表示任一特定收件人的结果。本轮不创建逐邮箱状态或重复阻断；页面默认未勾选邮箱、勾选后显示所选人数及实际地址。旧结果的 accepted/partial_failure/unknown 不禁用新邮件选择，必须仍提供独立确认和重复风险提示。

### 7.2 DeliveryRequest 的严格目标选择

`POST /api/v1/deliveries` 增加 `email_recipients: list[str]`，默认为空数组；选择 email 时必须提供非空数组，仅飞书时必须为空。示例仅向一位邮箱与飞书发送：

```json
{
  "report_date": "2026-10-05",
  "report_revision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "channels": ["email", "lark"],
  "email_recipients": ["mentor@example.com"]
}
```

- 每个邮箱必须为非空字符串且与当前配置地址完全一致；不允许前端新地址、额外空格/换行或近似匹配，不做模糊大小写映射。SMTP 配置本身不是浏览器可写数据。
- 数组禁止重复，合法请求规范化排序，排序进入指纹/保存记录/发送调用；同一选择的不同输入顺序是同内容。
- 选择 email 而省略/为空/类型非法/重复为 400 invalid_request；未选 email 却携带非空列表同样 400。配置外邮箱为 400 recipient_not_configured，固定文案“所选邮箱不在服务器配置中”；禁止回显恶意地址。
- 已启用邮件的配置包含可用目标；所选渠道未配置仍为 400 channel_not_configured。所有即时拒绝均零通知、零新操作执行，不回退向全体邮箱发送。
- 保留禁止客户端传正文、Webhook、Token、路径、强制忽略日期/版本等字段的规则；旧客户端邮件请求缺少目标返回 400，新旧前后端须配套启动。

### 7.3 目标快照与 OperationView 兼容

新增 `email_recipients: list[str] | null`：

- 新 delivery 操作选择 email 时是确认后的非空规范化列表；仅飞书为 `[]`；generation 为 null。
- 在接受事务中随请求指纹和 payload 保存；后台从接受记录读取目标，不能在执行时改为完整 smtp.recipients。一次 SMTP 调用只传本次列表，邮件 To 与发送信封目标一致。
- 新键接受前校验当前配置白名单和日报版本；重放已存在键则先比较指纹并返回原记录，不因后来配置改变重写已接受的目标。
- 原操作库已有 payload 缺少字段，服务端读取默认 null，前端严格解析允许 null，并提示“历史记录未记录具体收件人”。不回填当前邮箱，不重写旧行或改日报表。
- 地址属于认证接口的目标元数据，不扩展 SafeErrorCode 或用邮箱装入错误信息；固定 `recipient_not_configured` 仅为同步拒绝码。渠道结果继续使用原 DeliveryOutcome 聚合语义。

### 7.4 邮件主动再次发送与不变的请求边界

1. 邮件允许相同 report_date/report_revision 使用新幂等键主动再次推送，包括旧邮件结果 accepted/partial_failure/unknown；没有按收件人或地址组合的额外阻断。确认框展示本次目标和“再次推送可能产生重复邮件”。旧结果 unknown 额外提醒先核实原投递，状态不能被解释为明确失败。
2. 每次新邮件请求均由用户选择目标、点击推送并确认。已接受操作 pending、原请求尚未确认或已有活动槽时，新提交仍禁用/拒绝；不能用新键恢复丢失响应。
3. 同键同规范化 kind/日期/版本/渠道/邮箱选择只执行一次；同键改变任一字段 409 idempotency_conflict。网络断线、超时、500/响应不可解析时继续查询原键，不自动 POST；明确由用户重试原请求仍用同键同内容。
4. 飞书仍按同版本渠道历史 accepted/partial_failure/unknown/pending 阻断。邮件与不可重发飞书的组合请求整体 409 delivery_not_repeatable、零发送；取消飞书后可以提交仅邮件的新请求。
5. 版本匹配、任意日期处理、原子活动槽、重启中断/未知恢复及无自动续跑保持。当前操作新请求不修改历史渠道终态，服务商受理与实际收件依旧分开。

### 7.5 查询/预览的页面反馈契约

- 用户主动查询：开始时按钮/就近状态显示正在查询；成功时显示本次查询完成时间和时区，同时展示操作类型、实际 report_date/状态及服务器时间。null 表示暂无执行记录，清除旧执行卡片，不显示“令牌已验证”冒充查询反馈。
- 用户主动预览：开始时显示加载；成功显示日期/完成并定位正文标题，focus 与 scroll 只属于本次有效请求；404/网络/鉴权错误分别显示现有安全文案。后台恢复或轮询自动预览不移动焦点。
- 查询与主动预览的 GET 等待沿用历史查询 10 秒上限，到期停止浏览器等待并显示重新查询/预览的提示；不执行 POST、不取消后端操作。后台操作 120 秒自动观察上限保持。
- 相同结果重复查询也更新本次查询时间；日期/Token 变化及失效 ticket 的迟到响应不能覆盖提示、内容或焦点。原键断线恢复、鉴权失效清理和旧确认失效规则保持。
- 操作预览失败不会使旧展示成为有效推送预览；存在已加载的只读历史内容时允许保留展示，但必须明确“预览未就绪”，推送依据只能是当前成功的 controlPreview。
