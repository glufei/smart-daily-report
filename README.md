# 智能日报生成器

按 **SDD（Specification-Driven Development，规范驱动开发）** 方法构建的团队日报工具。它从 GitHub 提交、飞书任务和飞书群消息收集工作记录，按成员归属生成「代码提交 / 任务进展 / 协作沟通」三段式日报，保存本地历史，并通过 HTML 邮件和飞书群机器人发送。

项目适合小团队在工作日由外部调度器触发；当前实现是命令行程序，不提供常驻服务、Web 界面或 AI 自动撰写摘要。

## ✨ 核心工程亮点：规范先于代码

本项目以规范作为第一手工件，代码、测试与验收从规范推导：

| 阶段 | 可审查的交付物 | 作用 |
| --- | --- | --- |
| 需求定义 | [`specs/proposal.md`](specs/proposal.md) | 明确目标、范围、三段式日报、异常边界和量化验收标准。 |
| 架构设计 | [`specs/design.md`](specs/design.md)、[`specs/adrs/`](specs/adrs/) | 定义管道架构、模块职责、HTTP/存储决策和非功能性约束。 |
| 接口契约 | [`specs/contracts/`](specs/contracts/) | 固定数据模型、模块签名及「采集失败 ≠ 成功但无记录」的语义。 |
| 任务拆解 | [`specs/tasks.md`](specs/tasks.md) | 将工作拆成 Task 1–10 的依赖 DAG，每项对应可验证交付物。 |
| 实现与验证 | [`src/`](src/)、[`tests/`](tests/) | 按契约实现模块，用 Mock 单元测试和集成测试验证业务意图。 |

**可复核的质量证据：**`pyproject.toml` 设置了总覆盖率 **≥90%** 的自动化门槛，并开启分支覆盖率统计。2026-09-26 最近一次记录为 **64 项测试通过、总覆盖率 91.00%**；因此本项目不宣称 100% 代码覆盖率。GitHub、飞书采集和邮件、飞书推送还完成过一次真实端到端运行，用户确认两个渠道均收到日报，总耗时 4.875 秒。该次飞书任务与消息为零条；真实的非空任务和多页任务响应仍待验证，相关规则已用 Mock 测试覆盖。

## 架构概览

```text
GitHub 提交 ────┐
飞书任务 ───────┼─> Collector ─> Shared ─> Generator ─> SQLite 历史
飞书群消息 ─────┘      采集/解析    映射/过滤     Markdown + HTML
                                                   ├─> SMTP：HTML 邮件
                                                   └─> 飞书机器人：Markdown 卡片
```

- **Collector** 独立访问各数据源，处理分页、超时、限流和飞书 Token 刷新，返回带状态的 `CollectResult`。
- **Shared** 校验配置、判断工作日、按 GitHub/飞书账号映射成员、过滤敏感消息，提供 JSON 日志、HTTP 重试及 SQLite 存储。
- **Generator** 将成员记录渲染成同一份 `DailyReport` 的 Markdown 与 HTML；正常零记录显示「今日无记录」，来源失败显示「数据获取失败」。
- **Notifier** 分别投递邮件和飞书；一个渠道失败仍尝试另一个渠道。根目录 `main.py` 只委托包内编排入口执行。

**设计决策落地：**[ADR-001](specs/adrs/001-http-client.md) 采用可注入、可 Mock 的 `httpx` 客户端，当前程序使用同步 API；[ADR-002](specs/adrs/002-sqlite-storage.md) 采用本地 SQLite，以日报日期为键重复运行时更新当天记录；[ADR-003](specs/adrs/003-collect-result.md) 用 `CollectResult` 区分采集失败与成功空结果。部分来源失败时仍生成可用日报，全部来源失败时不生成、不推送。

## 项目结构

```text
.
├── main.py                         # 命令行启动入口
├── pyproject.toml                  # 依赖、可安装入口及 pytest/覆盖率配置
├── config.yaml.example             # 不含真实密钥的 YAML 配置样例
├── specs/                          # 需求、设计、ADR、契约、任务清单
├── src/smart_daily_report/
│   ├── main.py                     # 工作日判断与整条管道编排
│   ├── collector/                  # GitHub 提交、飞书任务与消息采集
│   ├── generator/                  # 成员日报组装、Markdown/HTML 渲染
│   ├── notifier/                   # SMTP 邮件与飞书机器人投递
│   └── shared/                     # 模型、配置、身份、HTTP、日志、日历、健康检查、存储
└── tests/
    ├── unit/                       # 单模块边界和失败分支
    └── integration/                # Mock 管道集成场景
```

## 快速开始（Windows PowerShell）

### 1. 安装

要求 **Python 3.11 或更高版本**。在项目根目录运行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item config.yaml.example config.yaml
```

若本机只有其他符合要求的 Python 版本，将第一行改为对应的 `py -3.x`。后续命令固定使用虚拟环境中的解释器，避免把依赖安装到另一套 Python。

### 2. 配置数据源和成员

编辑项目根目录的 `config.yaml`：设置 `team.name`、`team.timezone`、`team.github_repositories`、需要启用的 `team.lark_project_ids` / `team.lark_chat_ids`、`team.smtp`，以及 `members` 中的账号映射。邮件收件人必须是 YAML 列表，例如 `recipients: [leader@example.com]`。不用的飞书来源可保留空列表。历史 GitHub 提交若没有 `author.login`，可在相应成员下配置经核实的 `github_author_names`。

`config.yaml` 只保存配置项和**环境变量名**，不能写入 Token、应用密钥、SMTP 授权码或真实 Webhook。此项目不会自动读取 `.env`；如果使用 `.env` 文件，应先将其加载到**当前 PowerShell 进程环境**。在项目根目录自行创建 `.env`，当前完整接入示例需要以下六项：

```dotenv
DAILY_REPORT_GITHUB_TOKEN=替换为GitHub令牌
DAILY_REPORT_LARK_APP_ID=替换为飞书AppID
DAILY_REPORT_LARK_APP_SECRET=替换为飞书AppSecret
DAILY_REPORT_LARK_WEBHOOK=替换为飞书群机器人Webhook
DAILY_REPORT_SMTP_USERNAME=替换为SMTP登录邮箱
DAILY_REPORT_SMTP_PASSWORD=替换为SMTP授权码
```

GitHub 公共仓库可匿名采集，但配置令牌可避免较低的匿名限流；私有仓库需要有读取权限的令牌。只有启用飞书任务或消息采集时才需要飞书 App ID/Secret；只有启用飞书群推送时才需要 Webhook。SMTP 密码通常是邮件服务商提供的授权码。不要上传 `.env`、复制真实密钥到文档或把含密钥的终端输出发给他人；`.env` 和 `config.yaml` 已加入 `.gitignore`。

在**同一个 PowerShell 窗口**执行下列命令，将简单 `KEY=VALUE` 格式的 `.env` 加载进进程；值不加引号，支持值中含 `=`，空行和以 `#` 开头的行会跳过：

```powershell
Get-Content .env | ForEach-Object {
    $entry = $_.Trim()
    if ($entry -and -not $entry.StartsWith('#')) {
        $separator = $entry.IndexOf('=')
        if ($separator -lt 1) { throw 'Invalid .env line: expected KEY=VALUE' }
        [Environment]::SetEnvironmentVariable(
            $entry.Substring(0, $separator).Trim(),
            $entry.Substring($separator + 1),
            'Process'
        )
    }
}
```

关闭该窗口后，这些进程环境变量即失效。若使用 Windows 任务计划程序，须另行配置该任务的安全凭证注入方式；目前项目不会自动定时运行。

### 3. 检查、预览与正式运行

```powershell
.\.venv\Scripts\python.exe main.py --check
.\.venv\Scripts\python.exe main.py --dry-run
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe main.py --date 2026-04-23 --dry-run
```

- `--check` 验证配置及已启用依赖的轻量连通性，不生成、不入库、不发送；SMTP 仅检查连接，不验证登录或邮件送达。
- `--dry-run` 真实采集、生成并写入 `team.database_path` 指定的 SQLite，但**不发送**邮件或飞书消息。
- 正式运行先写入 SQLite，再分别发送邮件和已配置的飞书通知。`--date YYYY-MM-DD` 可指定历史工作日；未指定时使用配置的团队时区的当天日期。周末和配置的节假日会跳过。
- 日志是一行一条 JSON，可按 `run_id` 追踪采集和投递状态；退出码 `0` 表示成功或非工作日跳过，非零表示失败。

### 4. 运行自动化测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

测试对外部 HTTP API、SMTP 和 Webhook 使用 Mock，不需要真实账户或联网。`pytest` 会同时生成覆盖率报告；项目要求总覆盖率至少 90%。

## 运行边界与安全

- 来源失败与正常零记录分开表示，避免错误地向收件人报告「今日无记录」。飞书消息先按工作关键词筛选，再排除命中敏感词的整条消息；未映射成员只记录计数告警，不把源内容误归给别人。
- 日报中的外部文本在 HTML 中转义，链接仅允许 `http` / `https`。日志不记录 Token、Webhook、SMTP 密码或消息正文。
- SQLite 是本机历史记录，不是备份服务；存储路径、文件访问权限和备份策略由部署环境管理。
- 真实租户的「有任务」和「多页任务」响应尚需在出现相应数据后复核；现阶段这两类行为由 Mock 测试验证。

详细需求、接口和验收依据请参阅 [`specs/`](specs/proposal.md)。
