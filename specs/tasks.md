# 智能日报生成器任务清单

- 版本：v1.0
- 状态：已确认并实施完成
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

- 完成 Task 1–10 的实现与 Mock 测试。
- 当前验证：64 项测试通过；总覆盖率 91.00%（高于 90% 门槛，Python 3.12.14）。
- Python 3.12 编译检查与 wheel 构建成功。
- 2026-09-26 真实租户端到端运行：2026-04-23 日报的 GitHub、飞书任务、飞书消息采集均成功；邮件与飞书 Webhook 投递均成功，用户确认两处收到，总耗时 4.875 秒。历史提交作者名映射已在线验证。飞书任务当天为零记录；多页及有记录响应由 Mock 覆盖，仍待真实数据验证。

## 执行顺序

建议顺序：Task 1 → Task 2 → Task 3/4/5/6（满足依赖后并行）→ Task 7/8（满足依赖后并行）→ Task 9 → Task 10。Task 6 的开发可用契约定义的 Mock CollectResult 开始，不需要等待外部 API 接入。
