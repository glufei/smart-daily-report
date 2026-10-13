# 模块接口契约

本文件是 `specs/design.md` 的规范性子文档。所有签名均为逻辑契约；实现可使用同步 httpx 调用，或在不改变语义时使用异步实现。

v1.1 已确认的浏览器接口单独定义于 [`http-api.md`](http-api.md)。下列接口是内部 Python 能力，不是已经存在的 HTTP API；新增 Web 适配层不改变 Collector/Generator/Notifier 的调用语义。

```python
@dataclass
class CollectionWindow:
    start: datetime
    end: datetime

@dataclass
class RunConfig:
    team_name: str
    timezone: str
    members: list[MemberConfig]
    github_repositories: list[str]
    lark_project_ids: list[str]
    lark_chat_ids: list[str]
    report_keywords: list[str]
    sensitive_keywords: list[str]
    holidays: set[date]
    # secret values are resolved from environment, not stored in the config file

@dataclass
class MemberConfig:
    member_id: str
    display_name: str
    github_logins: list[str]
    lark_user_ids: list[str]
    github_author_names: list[str]  # GitHub 未关联账号时允许匹配的 Git 提交作者名
```

## Collector

```python
collect_commits(
    client: httpx.Client,
    repositories: Sequence[str],
    window: CollectionWindow,
) -> CollectResult[CommitRecord]

collect_tasks(
    client: httpx.Client,
    project_ids: Sequence[str],
    window: CollectionWindow,
    token_provider: TokenProvider,
) -> CollectResult[TaskRecord]

collect_messages(
    client: httpx.Client,
    chat_ids: Sequence[str],
    window: CollectionWindow,
    keywords: Sequence[str],
    sensitive_keywords: Sequence[str],
    token_provider: TokenProvider,
) -> CollectResult[MessageRecord]
```

每个 Collector 只负责其数据源请求和解析。限流、状态码分类、重试和 Token 刷新为确定性逻辑。一个 API 来源内部分页失败时，该来源整体结果为失败，避免将不完整分页伪装成完整成功；错误诊断不得包含敏感正文。

旧 v1.0 搜索模式（v1.2 启用任务时已拒绝并替换为本文件末尾清单 GET 契约）：曾将 `page_token` 放在 URL 查询参数中，`page_size` 保持在已验证可用的请求体位置。`has_more` 为假时停止；为真时必须返回新 `page_token` 才能继续。兼容缺少 `has_more` 的响应时可依据 `page_token` 继续；重复令牌必须作为分页失败返回，不得重复请求同一页。

## Shared

```python
load_config(path: Path, environ: Mapping[str, str]) -> RunConfig
validate_identity_mappings(config: RunConfig) -> None
map_records_to_members(
    config: RunConfig,
    commits: Sequence[CommitRecord],
    tasks: Sequence[TaskRecord],
    messages: Sequence[MessageRecord],
) -> list[MemberReport]
filter_sensitive_messages(
    records: Sequence[MessageRecord],
    sensitive_keywords: Sequence[str],
) -> list[MessageRecord]
write_report(db_path: Path, report: DailyReport) -> None
get_report(db_path: Path, report_date: date) -> DailyReport | None
check_dependencies(config: RunConfig, client: httpx.Client) -> list[HealthCheckResult]
```

映射冲突使配置加载失败；未映射记录不并入任一成员，生成不含原文的诊断计数。GitHub 提交优先按 `author_login` 匹配；仅在该字段缺失时，按显式配置的 `github_author_names` 匹配。提交作者名可由提交者自行填写，配置前须确认身份；不同成员不得配置相同作者名。敏感过滤必须先于映射后持久化/输出执行。

v1.1 已确认补充：`get_report()` 使用只读连接，不创建数据库/表；数据库不存在或指定日期无行返回 `None`，已有库缺表/损坏/读取失败或内容无法反序列化时报告读取错误，不用 `None` 隐藏失败。HTTP 字段及来源状态校验由 Web DTO 适配层负责，不改变 Shared 对既有有效模型的往返读取。`write_report()` 的写入/幂等语义保持，查询不调用写入能力。

## Generator

```python
generate_daily_report(
    report_date: date,
    team_name: str,
    members: Sequence[MemberReport],
    source_status: Mapping[str, CollectResultStatus],
    generated_at: datetime,
) -> DailyReport
```

Generator 不调用外部 API，不决定重试，不生成 AI 自然语言摘要。成员区块先按 `DailyReport.source_status` 确定性统计代码提交、完成任务和已过滤协作消息，再展示三类来源明细；来源成功但成员无记录显示“0 条”，来源失败显示“获取失败，数量未知”，不得把失败计为零。Markdown 与 HTML 的总结和明细必须一致，并继续对外部文本做安全转义。

## Notifier

```python
send_email(
    report: DailyReport,
    recipients: Sequence[str],
    smtp_config: SmtpConfig,
) -> DeliveryResult

send_lark_message(
    report: DailyReport,
    webhook_url: SecretStr,
) -> DeliveryResult
```

`SmtpConfig` 支持两种互斥传输模式：STARTTLS（`starttls: true, use_ssl: false`）与隐式 TLS（`starttls: false, use_ssl: true`）。

单一渠道的失败由调用方记录，不改变另一渠道的调用结果。Notifier 对可重试的暂时故障最多重试 2 次；鉴权/参数类错误不重试。返回结果包含 `success: bool`、`attempts: int` 和安全 `error_code`。

## Orchestrator / CLI

```python
run_report(config: RunConfig, report_date: date, dry_run: bool = False) -> RunResult
run_health_check(config: RunConfig) -> HealthCheckResult
main(argv: Sequence[str] | None = None) -> int
```

流程由确定性代码执行：对任意有效日期分别采集；全部来源失败时终止且不生成空日报；部分成功则聚合、生成、写入历史；未启用 dry-run 时分别推送。周末与 `holidays` 配置不参与日期拦截。`--check` 只验证配置和依赖，不生成、持久化或推送。

## YAML 账号映射示例（占位值）

```yaml
team:
  name: example-team
  timezone: Asia/Shanghai
  holidays: []
members:
  - member_id: member-001
    display_name: 张三
    github_logins: [github-example]
    lark_user_ids: [ou-example]
    github_author_names: [legacy-git-author-name]
```

真实 Token、密码和 Webhook 通过环境变量注入。成员外部账号映射必须全局唯一。

## v1.2 Web 操作适配增量（已实现并完成真实外部验收）

- HTTP 接口、受保护 DTO、幂等和中断语义以 [`web-operations.md`](web-operations.md) 为准；操作层复用 Collector/Generator/Notifier，不让浏览器直接调用这些内部函数。
- `run_report(config, report_date, dry_run=True, ...) -> RunResult` 保留签名和现有注入方式。RunResult 兼容增加 `sources: dict[str, CollectResult]`（默认空），交接已启用来源的原始成功/失败结果；禁用由 RunConfig 确定。API 仅投影状态/安全错误码，不返回 records/message 或秘密。
- 修正全失败判断：只计算已启用来源；无已启用来源是配置错误，全部已启用来源失败不生成/写历史，不被禁用来源的兼容 success 状态掩盖。任意有效日期均在日期校验通过后进入采集，不按星期或 `holidays` 跳过。
- 飞书任务签名及 `RunConfig.lark_project_ids`/`lark_task_search_path` 字段名保留兼容；project_ids 实际为已授权 tasklist GUID，path 默认改为 `/task/v2/tasklists/{tasklist_guid}/tasks`。每个 GUID 替换路径模板后 GET，query 为 page_size=100/completed=true/user_id_type=open_id 及后续 page_token，无 JSON body，不设创建日期过滤。显式旧 search 路径在启动时拒绝并提示迁移，不能静默继续用 tenant Token 搜索。健康检查沿用同一清单 GET 契约。只投影 completed_at 落入 CollectionWindow 的 TaskSummary；返回与多负责人语义见 data-models.md。
- 操作层的生成服务只调用 dry_run=True；推送服务先 `get_report()`、校验版本并捕获 DailyReport，然后分别调用 `send_email()` / `send_lark_message()`。严禁以 dry_run=False 的编排代替独立推送。
- 保留 `DeliveryResult.success/attempts/error_code` 及旧调用方式，兼容增加可选 `outcome`（accepted/rejected/partial_failure/unknown）。新推送需明确提供 outcome；accepted 才令 success=True。旧调用未提供 outcome 时不能在 v1.2 操作界面无证据映射成 accepted；过渡映射与 CLI 测试在任务中明确验证。
- SMTP 部分收件人拒绝、机器人新/旧业务码与不确定发送须在 Notifier 的最小增量中表达；可证明发送前未接受的暂时故障才重试，已提交后读超时/不可信响应不自动重发。单渠道异常仍不阻止另一渠道。
- 配置校验按启用能力处理：整个 SMTP 配置块缺失/为空视为禁用邮件，不能阻止仅生成或飞书推送；提供了 SMTP 配置却缺少必需字段时启动失败，不静默禁用。配置了邮件则校验目标/TLS/凭证。对 CLI 无发送的调用保持可用，选择未启用渠道返回明确失败，不尝试连接空主机。
- 前端 API 模块继续使用 fetch + Zod，复用旧 ReportView 类型；新 OperationView/PreviewView 按严格枚举解析。服务器错误正文不作为可执行 HTML 或不受控文案展示。
- 服务函数拆分和文件归属已按 Superpowers 实施计划实现；真实验收及验证边界见 `docs/frontend/v1.2-acceptance.md`，最终复核见 `docs/frontend/v1.2-final-handover.md`。

## 2026-10-03完整性与输出转义核对

- 消息成功响应必须实际含data/items列表；缺字段或列表类型错误返回invalid_payload，不能表示正常零记录。has_more出现时必须为布尔值；缺少has_more的既有兼容按page_token继续保留。任一后续页异常使整个消息来源失败且records为空。
- GitHub提交详情与列表共用既有限流规则；详情按Link.next读取文件页，以filename去重，统计首个详情页的增删行。后页失败或重复链接整个来源失败，不保存部分文件数。官方接口最多公开3000个文件；达到该边界无法区分恰好3000与上游截断，保守返回details_file_limit，不声称完整计数。该限制不影响其他可用来源生成明确的partial_failure日报。
- Markdown模板转义团队名、成员名、仓库/提交标题、任务标题/状态和消息正文的控制字符、实体与换行；链接先限制HTTP(S)，再编码Markdown目的地址分隔符。HTML沿用安全转义；原始成员记录保持不变。标题/列表/链接仅由模板生成，外部文本不作为新的格式命令。历史已保存日报不自动重写；预览及推送仍绑定原版本快照。

## v1.3 目标选择适配（2026-10-11，已实现及回归通过）

- 新操作字段与兼容性以 [web-operations §7](web-operations.md) 为准。既有 Collector/Generator、DailyReport、send_email/send_lark_message 的公共签名不变；CLI 仍调用配置全量邮箱，Web 发送仅传确认过的配置子集。
- OperationStore.accept 增加可选目标快照参数，生成/旧调用默认 null，新邮件操作为非空列表，新仅飞书为 []；快照入 payload 和请求指纹，finish/record_delivery/recover_interrupted 保留该字段。旧 payload 缺字段按 null 投影，不初始化补造历史地址。
- OperationService.accept_delivery 验证白名单和版本；execute 读取已持久目标，不重新取全部配置邮箱。HTTP DTO、前端 Zod 和测试 fixture 一起更新；配置外目标即时拒绝，不传到 Notifier。
- Store 的同日报版本跨请求阻断只继续约束飞书；邮件允许用户独立确认新请求再次发送。请求键去重、全局活动槽、未知结果/重启恢复与无自动重发保持。邮件仍聚合为原 DeliveryResult，不增加逐收件人账本。
- 原 v1.2 的固定全量邮件/整邮件渠道禁止主动再次发送为历史基线；本增量明确替换相应 Web 规则，不能同时执行冲突约束。Task19–21 已按 TDD 实现并通过回归；v1.3 前后端需配套升级。
