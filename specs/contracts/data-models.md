# 数据模型契约

本文件定义模块间稳定传输的数据语义。类型以 Python 3.11+ 类型表达；具体采用 dataclass 或其他实现不属于本契约。除非注明，时间使用带时区的 ISO 8601 时间，所有内部日期按配置时区解释。书中核心字段以原始名字保留；本项目增加稳定 ID、来源链接和显式状态字段满足模块协作、失败区分与持久化需要。

## CommitRecord

| 字段 | 类型 | 约束/含义 |
|---|---|---|
| `record_id` | `str` | GitHub commit SHA，来源内唯一 |
| `repository` | `str` | `owner/repository` |
| `author_login` | `str \| None` | GitHub 用户名；缺失时保留为 `None` |
| `author_name` | `str \| None` | Git 作者显示名 |
| `message` | `str` | 提交标题/摘要，不包含 diff |
| `committed_at` | `datetime` | 提交时间 |
| `url` | `str` | GitHub commit 页面链接 |
| `member_id` | `str \| None` | 映射后的内部成员 ID；Collector 可先置空，归一阶段填充 |
| `additions` | `int` | 新增行统计；来源不提供时为 0 |
| `deletions` | `int` | 删除行统计；来源不提供时为 0 |
| `files_changed` | `int` | 变更文件数；来源不提供时为 0 |

书中兼容别名：`author` 映射 `author_login`（无 login 时回退显示名），`timestamp` 映射 `committed_at`，`repo` 映射 `repository`。

## TaskRecord

| 字段 | 类型 | 约束/含义 |
|---|---|---|
| `record_id` | `str` | 飞书任务标识 |
| `title` | `str` | 任务标题 |
| `status` | `str` | v1.2 完成任务为 `completed`；旧历史状态值继续可读 |
| `assignee_user_id` | `str \| None` | 飞书用户标识 |
| `changed_at` | `datetime` | v1.2 为来源 `completed_at` 转换的带时区完成时间；不使用普通更新时间替代 |
| `url` | `str \| None` | 任务链接 |
| `member_id` | `str \| None` | 映射后的内部成员 ID |
| `status_from` | `str \| None` | 变更前状态（来源提供时） |
| `status_to` | `str \| None` | 变更后状态；兼容书中状态迁移模型 |

书中兼容属性名：`assignee` 映射 `assignee_user_id`，`updated_at` 返回 `changed_at`；属性名兼容不允许 Collector 以源 updated_at 推造完成事件。v1.2 保留结构与存储 schema；完成记录 `status_from=None / status_to='completed'`，不复原前态。多负责人逐人投影同一 guid，按 `(record_id, assignee_user_id)` 去重；无负责人保留未映射记录，成员归属仍由既有映射处理。清单摘要不含链接时 `url=None`。

## MessageRecord

| 字段 | 类型 | 约束/含义 |
|---|---|---|
| `record_id` | `str` | 飞书消息标识 |
| `sender_user_id` | `str \| None` | 飞书发送者标识 |
| `content` | `str` | 通过敏感词过滤后的文本；敏感命中记录不得构造为可输出对象 |
| `sent_at` | `datetime` | 消息发送时间 |
| `url` | `str \| None` | 消息链接（若 API 提供） |
| `member_id` | `str \| None` | 映射后的内部成员 ID |
| `chat_name` | `str` | 群名称或配置中的群标识 |

书中兼容别名：`sender` 映射 `sender_user_id`，`timestamp` 映射 `sent_at`。

## CollectResult[T]

| 字段 | 类型 | 约束/含义 |
|---|---|---|
| `source` | `str` | 稳定来源名，如 `github_commits` |
| `status` | `Literal["success", "failure"]` | 结果状态 |
| `records` | `list[T]` | 成功时记录列表；失败时为空列表 |
| `error_code` | `str \| None` | 稳定错误类别；成功时为空 |
| `message` | `str \| None` | 安全诊断，不含凭证或敏感正文 |
| `attempts` | `int` | 实际尝试次数，至少为 1 |

不变量：`success + []` 表示成功采集但无记录；`failure + []` 表示采集失败。消费者必须依据 `status` 而非列表长度判断失败。

## MemberReport

| 字段 | 类型 | 约束/含义 |
|---|---|---|
| `member_id` | `str` | 内部稳定成员 ID |
| `display_name` | `str` | 报告显示名称 |
| `commits` | `list[CommitRecord]` | 该成员提交 |
| `tasks` | `list[TaskRecord]` | 该成员任务 |
| `messages` | `list[MessageRecord]` | 该成员的安全消息 |
| `source_status` | `dict[str, CollectResultStatus]` | 各来源成功/失败状态；供每个板块显示空/失败 |
| `github_username` | `str` | 书中 `MemberReport` 字段；用于身份映射和兼容展示 |

书中兼容别名：`name` 映射 `display_name`。

## DailyReport

| 字段 | 类型 | 约束/含义 |
|---|---|---|
| `report_date` | `date` | 报告对应的本地日期 |
| `team_name` | `str` | 配置团队名 |
| `members` | `list[MemberReport]` | 按配置顺序排列，包含无记录成员 |
| `source_status` | `dict[str, CollectResultStatus]` | 各来源总体状态 |
| `markdown` | `str` | 三段式成员日报 Markdown |
| `html` | `str` | 与 Markdown 同内容的安全 HTML 表示 |
| `generated_at` | `datetime` | 生成时间 |

若所有来源均失败，Generator 不得返回 DailyReport；此条件由编排接口定义。所有来源成功但记录为空时可以生成显示“今日无记录”的日报。

书中兼容别名：`date` 映射 `report_date`。

## CollectResultStatus

| 字段/值 | 语义 |
|---|---|
| `success` | 来源调用成功，可能有记录或零条记录 |
| `failure` | 来源调用失败；日报对应区域显示“数据获取失败” |
