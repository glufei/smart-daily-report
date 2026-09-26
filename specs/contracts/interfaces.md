# 模块接口契约

本文件是 `specs/design.md` 的规范性子文档。所有签名均为逻辑契约；实现可使用同步 httpx 调用，或在不改变语义时使用异步实现。

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

飞书任务搜索将 `page_token` 放在 URL 查询参数中，`page_size` 保持在已验证可用的请求体位置。`has_more` 为假时停止；为真时必须返回新 `page_token` 才能继续。兼容缺少 `has_more` 的响应时可依据 `page_token` 继续；重复令牌必须作为分页失败返回，不得重复请求同一页。

## Shared

```python
load_config(path: Path, environ: Mapping[str, str]) -> RunConfig
validate_identity_mappings(config: RunConfig) -> None
is_workday(day: date, holidays: set[date]) -> bool
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

Generator 不调用外部 API，不决定重试，不生成 AI 摘要。它必须按模型中的来源状态显示“数据获取失败”或“今日无记录”，并对外部文本做安全转义。

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

流程由确定性代码执行：非工作日跳过；分别采集；全部来源失败时终止且不生成空日报；部分成功则聚合、生成、写入历史；未启用 dry-run 时分别推送。`--check` 只验证配置和依赖，不生成、持久化或推送。

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
