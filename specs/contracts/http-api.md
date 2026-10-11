# v1.1 只读 HTTP 接口契约

v1.2 增加的生成、预览与推送接口及 v1.3 操作反馈/邮件目标行为见 [`web-operations.md`](web-operations.md)。本文件继续约束历史 GET 与只读启动；“唯一业务接口/不提供操作”仅指 v1.1 和只读模式，不能禁止后续操作模式的新路由。历史 GET 的副作用、字段及错误语义不变。

- **状态**：2026-09-30 用户已确认；只读接口实现及验收完成
- **上游**：`proposal.md` §4.1 F02–F05；`design.md` §1.2–§1.3；ADR-004
- **复用模型**：[`data-models.md`](data-models.md) 的 DailyReport、MemberReport 与三类记录

## 1. 入口与副作用

唯一业务接口：`GET /api/v1/reports/{report_date}`。读取启动时指定的 SQLite，浏览器不能传数据库路径或配置文件。`report_date` 必须严格为有效的 `YYYY-MM-DD`（例如 `2026-04-23`）；紧凑日期、带时间字符串或不存在的日历日期返回 400，不使用框架默认 422。

接口读取已生成日报，不能采集、生成、写入、推送或联机调用 GitHub/飞书/SMTP。周末或节假日也按既有历史查询，不自动生成；不存在日报只能解释为“该日期尚无日报”，不得猜测原因或声称本次采集失败。

API 只绑定 `127.0.0.1`，默认端口 8000；允许前端 Origin 为 `http://127.0.0.1:5173` 与 `http://127.0.0.1:4173`，Host 仅接受 `127.0.0.1` / `localhost`（测试可显式加入测试 Host）。未允许的 Origin 返回 403，不仅省略 CORS 响应头；不使用 `*` 或 Cookie 凭证。本机无 Origin 请求允许。所有业务响应声明 `Cache-Control: no-store`。

不提供 POST/PUT/PATCH/DELETE 的日报操作，访问该业务资源的这些方法返回 405。OpenAPI/开发文档如启用，只描述本机只读能力。

## 2. 成功响应（200，application/json）

顶层 `ReportView` 是显式白名单投影，不直接序列化 dataclass 的全部属性。

| 字段 | JSON 类型 | 约束 |
|---|---|---|
| `report_date` | string | 与请求日期相同的 YYYY-MM-DD，含义是生成时配置时区中的报告日期 |
| `team_name` | string | 保存时的团队名称 |
| `generated_at` | string | 带时区的 ISO 8601；历史查询及操作模式预览均按团队配置时区投影、只读模式按启动参数 `--timezone` 投影（缺省 UTC）；页面显示返回时区及偏移，不依据浏览器时区改变展示。SQLite 中仍保存 UTC 时间点 |
| `source_status` | object | 三个必填来源键，见下文 |
| `members` | array of MemberView | 保存的配置顺序，包含零记录成员；不得重新读取当前配置覆盖历史成员 |

`source_status` 恰有 `github_commits`、`lark_tasks`、`lark_messages` 三个键，值为 `success` 或 `failure`；禁止从记录数推断状态。至少一个来源成功；全失败状态的历史对象不符合 DailyReport 契约，返回 500 `invalid_report_data`。

| MemberView 字段 | JSON 类型 | 约束 |
|---|---|---|
| `member_id` | string | 内部稳定 ID，成员间唯一 |
| `display_name` | string | 成员显示名 |
| `commits` | array of CommitView | 该成员保存的提交，保留顺序 |
| `tasks` | array of TaskView | 该成员保存的任务，保留顺序 |
| `messages` | array of MessageView | 该成员保存的已过滤消息，保留顺序 |

记录字段如下，全部为必填键，注明 nullable 的允许为 null；未列出的内部字段不输出。

| 对象 | 字段与类型 |
|---|---|
| CommitView | `record_id: string`、`repository: string`、`message: string`、`committed_at: ISO 8601 string with timezone`、`url: string/null`、`additions: integer`、`deletions: integer`、`files_changed: integer` |
| TaskView | `record_id: string`、`title: string`、`status: string`、`status_from: string/null`、`status_to: string/null`、`changed_at: ISO 8601 string with timezone`、`url: string/null` |
| MessageView | `record_id: string`、`content: string`、`sent_at: ISO 8601 string with timezone`、`chat_name: string`、`url: string/null` |

不返回账号映射、外部用户 ID、`github_username`、Markdown、HTML、凭证、配置或诊断原文。URL 复用 `generator/template.py` 的 `safe_url()` 规则，只输出 http/https，否则为 null；前端同样限制协议并按文本渲染外部字段。不得使用 `dangerouslySetInnerHTML` 插入记录或持久化 HTML。

来源状态仅输出顶层值，与现有 Markdown/HTML 模板一致；不输出或合并内部成员 `source_status`，避免两套状态来源影响展示。顶层失败来源对应记录数组必须为空；顶层状态缺失/未知、失败来源有记录、损坏 JSON 或类型/日期不符合契约均视为无效历史数据，由 Web 适配层报告，不补默认成功，不把无效记录静默丢弃。禁止提供“投递成功”字段：现有存储并不能证明投递状态。

成功零记录示例：

```json
{
  "report_date": "2026-04-23",
  "team_name": "示例团队",
  "generated_at": "2026-04-23T10:00:00+00:00",
  "source_status": {"github_commits": "success", "lark_tasks": "success", "lark_messages": "success"},
  "members": [{
    "member_id": "member-001",
    "display_name": "示例成员",
    "commits": [], "tasks": [], "messages": []
  }]
}
```

## 3. 失败响应与确定性页面处理

业务错误采用固定安全文案的 JSON 信封：`{"error":{"code":"report_not_found","message":"该日期尚无日报"}}`。日志只记录事件、来源/请求日期、错误类别与 run_id，不记录响应正文、数据库绝对路径、凭证或堆栈。

| HTTP | error.code | 固定 message | 页面语义 |
|---|---|---|---|
| 400 | `invalid_report_date` | 日期无效，请使用 YYYY-MM-DD | 日期输入错误，不显示空日报 |
| 403 | `origin_not_allowed` | 请求来源未允许 | 查询失败 |
| 404 | `report_not_found` | 该日期尚无日报 | 无日报；与“已有日报但无记录”不同 |
| 405 | `method_not_allowed` | 此接口仅允许查询 | 查询失败，无操作副作用 |
| 500 | `storage_read_failed` | 日报读取失败，请稍后重新查询 | 查询失败；数据库不可读/损坏/缺表，不冒充无日报 |
| 500 | `invalid_report_data` | 日报数据格式异常 | 查询失败；JSON/历史对象校验失败 |
| 500 | `internal_error` | 日报查询失败 | 未预期错误，安全兜底 |

不存在数据库文件或在正确 schema 的空表中找不到日期返回 404；不自动创建文件或表。非法日期先校验，不读取数据库。已有数据库文件缺表返回 500。读事务与只读模式避免查询修改历史；写入依然由 CLI 原事务完成。

页面发送单次 GET。网络不可达或超时显示“无法连接日报服务”，响应 JSON 不符合契约显示“日报响应格式异常”，均提供显式重新查询操作，不自动重试。超时上限 10 秒；发起新日期查询时取消或忽略旧请求，清除旧日期内容，只有最新查询能改变页面状态。

日报内容始终按“代码提交 → 任务进展 → 协作沟通”排列：来源 failure 显示“数据获取失败”；来源 success 且该成员列表为空显示“今日无记录”；否则展示记录。页面 HTTP 状态与日报来源状态是不同维度，HTTP 200 允许包含部分来源失败的历史日报。
