# 智能日报生成器

从配置的 **GitHub 仓库、飞书任务清单和飞书群**采集工作记录，按成员生成日报并保存到本地 SQLite。可在本机网页查看历史，或先采集预览、再单独确认邮件和飞书推送；也提供命令行入口。

**当前版本：v1.6.6。** 后端使用 Python/FastAPI，前端使用 React。

- **内容可信度**：今日概览只统计成功采集且匹配成员的记录；来源失败标为“获取失败”，不会伪装成 0 条。不调用 AI，也不改写源消息。
- **运行方式**：按需手动运行，没有定时任务或自动部署；GitHub Actions 只负责检查和打包，详见 [CI/CD](#cicd自动验证与交付构建文件)。
- **时间与历史**：新生成的网页和邮件把生成、提交、任务及消息时间显示为中国标准时间（Asia/Shanghai，UTC+08:00），不改变原始时间点。历史日报和已保存的邮件 HTML 是快照；修改配置或模板后须重新生成指定日期，旧快照不会自动更新。

## 先选择你要做什么

| 你的情况 | 从哪里开始 |
| --- | --- |
| 已配置好凭证和依赖，直接运行项目 | [一、已配置环境启动](#一已配置环境启动) |
| 第一次下载项目，想先看看页面 | [二、首次安装](#二首次安装) → [三、演示模式](#三演示模式无需外部账号) |
| 第一次下载项目，要连接自己的 GitHub / 飞书 / 邮箱 | [二、首次安装](#二首次安装) → [四、配置并启动真实模式](#四配置并启动真实模式) |
| 只查看已有日报，不采集或发送 | [五、只读模式与命令行](#五只读模式与命令行) |

**下面的命令使用 Windows PowerShell。** 后端和前端分别占用一个终端窗口，启动后保持两个窗口运行。若页面已经能打开、服务也正常运行，可以直接使用，不必重复启动。

## 一、已配置环境启动

适用于已准备好配置文件、凭证和依赖的项目副本。分别打开两个 PowerShell 窗口，并先在每个窗口进入项目根目录。

### 1. 窗口 A：启动真实后端

打开一个 PowerShell 窗口，完整执行以下代码。它会加载该目录的 `.env`，然后启动 API；不会显示密钥。

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'

Get-Content -LiteralPath '.env' -Encoding UTF8 | ForEach-Object {
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

.\.runtime\venv\Scripts\python.exe -m smart_daily_report.web.main --config '.\config.yaml' --port 8000
```

看到 `Uvicorn running on http://127.0.0.1:8000` 就表示后端已启动。终端停在这里等待请求是正常现象，不要关闭窗口。

### 2. 窗口 B：启动前端

再打开一个 PowerShell 窗口，执行：

```powershell
Set-Location 'frontend'
$env:VITE_API_MODE = 'operations'
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000'
npm run dev
```

看到 Vite 的 `Local: http://127.0.0.1:5173/` 后，在浏览器打开 **[http://127.0.0.1:5173](http://127.0.0.1:5173)**。

### 3. 在页面上使用

| 操作 | 使用方法 | 是否发送通知 |
| --- | --- | --- |
| 查看已有日报 | 选择日期 → 点击「查看日报」；无需令牌 | 否，也不重新采集 |
| 采集并生成 | 输入 `.env` 中的 `DAILY_REPORT_WEB_TOKEN` →「验证令牌」→ 选择任意日期 →「采集并生成」 | 否，只采集、保存和预览 |
| 发送日报 | 验证令牌 →「预览日报」→ 核对内容 → 选择渠道和具体邮箱 →「推送日报」→ 核对弹窗地址 →「确认推送」 | 是，发送已确认的版本 |
| 查看执行进度 | 验证令牌后点击「查询执行结果」，查看操作日期、状态与本次查询时间 | 否 |

**操作令牌是本项目的 `DAILY_REPORT_WEB_TOKEN`，不是 GitHub Token、飞书密钥或邮箱授权码。** 空令牌验证会提示输入；令牌未验证时，「采集并生成」保持禁用。页脚「查看已保存的团队日报」是说明文字，查询入口在页面上方。

### 如何只给一位收件人发送

1. 选择日报日期，输入本项目操作令牌，点击「验证令牌」。
2. 点击「预览日报」，看到“已加载…”提示后核对下方正文；成功后页面会定位到正文标题。没有日报时先「采集并生成」，此时不会发送。
3. 勾选「邮件」，在“邮件收件人”中只勾选要发送的邮箱。例如配置中有 `member@example.com` 和 `mentor@example.com`，只勾选后者，就只给后者发邮件。地址由服务器配置提供，页面不支持随意输入新地址，初始全部未选。
4. 不需要飞书通知时，取消「飞书」。只发飞书则取消「邮件」，无需选择邮箱。
5. 点击「推送日报」，逐项核对弹窗中的日期、版本、邮箱地址与飞书目标。点击「取消」不发送；点击「确认推送」才提交。
6. 查看“推送执行结果”中的本次邮箱和渠道状态。「服务商已受理」表示 SMTP 已接受，仍需检查实际收件箱；Gmail 找不到时检查垃圾邮件，找到后点击“不是垃圾邮件”，可为可信发件人设置“从不发送至垃圾邮件”过滤器。

邮件主题按“年级 + 姓名 + 报告日期 + 日报名称”组成；正文包含报告日期及生成时间。每次发送前都应重新预览并核对内容，确认收件人和推送渠道后再提交。

收件人保存在本地私有配置中；要增加或移除收件人，请编辑配置并重启后端。邮箱选择不会跨次保留，每次推送前都需重新勾选。飞书来源若显示“数据获取失败”，该项数量为未知，不能把它当作 0；请在发送前核对预览。项目不会自动发送邮件。

**邮件可以主动再次发送同一日报。** 每次重新选择收件人并独立确认都会产生一个新请求，可能产生重复邮件；系统不按收件人去重。飞书同一版本已受理、部分受理或结果未知时继续禁用再次发送。

断线后先「查询执行结果」，系统查询原请求，不自动再次发送；只有原请求未找到时才提供「重试原请求」，该重试保留原先确认的地址。不要删除操作数据库来解除限制。日期、令牌或预览变化会清空邮箱选择并使旧确认失效。

“查询执行结果”和“预览日报”都会就近显示加载、完成或失败提示。查询完成会更新“本次查询时间”，即使结果没有变化；令牌验证、生成/推送请求及预览等待超过10秒会明确提示并释放页面忙碌状态，后台任务不会因此取消。若生成/推送请求超时，先点“查询执行结果”核对原请求；系统保留原幂等键，绝不自动再次提交。

### 4. 停止项目

分别回到窗口 A、窗口 B，按 **Ctrl+C**。下次启动时重复步骤 1、2 即可；已经安装的依赖不必每次重装。

## 二、首次安装

适用于第一次运行的新环境。已安装依赖且已有配置的环境可跳过本节。

需要 Git、Python **≥3.11**、Node.js **`^22.12.0 || ^24.0.0 || >=26.0.0`**。v1.2.0 已在 Python 3.12.14、Node 24.15.0、npm 11.12.1 上验证。

先克隆仓库，或者直接进入你已经下载的项目根目录。下方命令从项目根目录运行。

```powershell
git clone https://github.com/glufei/smart-daily-report.git
Set-Location '.\smart-daily-report'

py -3.12 -m venv .runtime\venv
.\.runtime\venv\Scripts\python.exe -m pip install --upgrade 'pip>=26.2'
.\.runtime\venv\Scripts\python.exe -m pip install -e '.[dev,web]'

Set-Location frontend
npm ci
Set-Location '..'
```

安装完成后回到项目根目录再按下文打开两个终端；后端命令从项目根目录运行，前端命令从 `frontend` 目录运行。已经克隆过项目时不要再次执行 `git clone`。若没有 `py` 命令，用已安装 Python 的路径替换创建环境那一行，例如 `& 'C:\Python312\python.exe' -m venv .runtime\venv`；实际路径以你的安装位置为准。后续固定使用 `.runtime\venv\Scripts\python.exe`。

安装完后，选择演示模式或真实模式，二者不需要同时启动。

## 三、演示模式：无需外部账号

用于先熟悉界面。使用仓库提供的虚构数据，不需要 `.env`、GitHub/飞书账号或邮箱配置，不发送真实通知。

**窗口 A：**

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
.\.runtime\venv\Scripts\python.exe frontend/e2e/serve_fixture.py --port 8000
```

**窗口 B：**

```powershell
Set-Location 'frontend'
$env:VITE_API_MODE = 'readonly'
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000'
npm run dev
```

打开 **[http://127.0.0.1:5173](http://127.0.0.1:5173)**，选择 **2026-09-25**，点击「查看日报」。这是只读演示，不显示生成或推送控件。其他示例：9 月 26 日来源失败、9 月 27 日无日报、9 月 30 日正常零记录。

切换到真实模式前，在两个演示终端按 Ctrl+C，释放 8000 和 5173 端口。需要演示生成与确认交互时，参阅[操作模式演示](docs/frontend/local-run.md#操作模式可复现-fixture不访问真实平台)。

## 四、配置并启动真实模式

本节适用于新环境。已准备好凭证和依赖的环境可直接使用第一节。

### 1. 准备配置文件和凭证

在项目根目录执行一次；若已有 `config.yaml`，保留现有文件，不覆盖：

```powershell
if (-not (Test-Path -LiteralPath 'config.yaml')) {
    Copy-Item -LiteralPath 'config.yaml.example' -Destination 'config.yaml'
}
```

编辑 `config.yaml`，把示例仓库、成员和收件人替换为自己的信息。示例文件本身不是可直接运行的真实配置。

| 配置项 | 填写内容 |
| --- | --- |
| `team.github_repositories` | 一个或多个仓库名，例如 `[your-name/repo-a, your-name/repo-b]`；只有列出的仓库会被采集 |
| `team.lark_project_ids` | 已授权的飞书**任务清单 GUID**，不是单条任务 GUID |
| `team.lark_chat_ids` | 应用可读取的来源群 ID；与推送 Webhook 的目标群分别配置 |
| `team.report_keywords` | `[]` 收录来源群中已映射成员的全部消息；填写如 `[日报, 进展, 发布]` 时，只收录包含关键词的消息 |
| `members` | 团队成员及其 GitHub / 飞书身份映射 |
| `team.smtp` | 邮件服务器、发件人和收件人；不用邮件时可删除整个 `smtp` 配置块 |
| `team.database_path` | 历史库路径，默认 `data/reports.sqlite3` |

不用的来源列表设为 `[]`，真实操作模式至少要启用一个来源。飞书任务使用 `/task/v2/tasklists/{tasklist_guid}/tasks`，应用还需要对应读取权限和清单访问授权；消息按关键词（配置非空时）、敏感词、成员映射和日期规则筛选。修改 `report_keywords` 后须重启后端并重新「采集并生成」所选日期；「查看日报」只读取已保存内容。

仓库、任务清单、来源群、成员身份和关键词必须使用 YAML 字符串列表，例如 `[owner/repository]`、`[日报, 进展]`；单个值也要放在列表中。标量、数字或空字符串会被明确拒绝，避免错误采集或改变敏感词过滤规则。

再在项目根目录新建 `.env`，按启用的功能填写。下面只有占位示例，须替换为实际值；每行使用 `KEY=VALUE`，值不加引号、不加行尾注释。

```dotenv
DAILY_REPORT_WEB_TOKEN=替换为自己生成并保管的至少32字符操作令牌
DAILY_REPORT_GITHUB_TOKEN=替换为GitHub读取令牌
DAILY_REPORT_LARK_APP_ID=替换为飞书AppID
DAILY_REPORT_LARK_APP_SECRET=替换为飞书AppSecret
DAILY_REPORT_LARK_WEBHOOK=替换为目标群机器人Webhook
DAILY_REPORT_SMTP_USERNAME=替换为发送邮件的邮箱
DAILY_REPORT_SMTP_PASSWORD=替换为邮箱SMTP授权码
```

操作令牌由你自己生成，不需要到 GitHub 或飞书申请。在项目根目录运行下面的命令，把输出的 64 位随机字符串填入 `.env` 的 `DAILY_REPORT_WEB_TOKEN`，并自行保管：

```powershell
.\.runtime\venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

`DAILY_REPORT_WEB_TOKEN` 必填。其他凭证取决于启用的来源和推送渠道，变量名须与 YAML 中的 `*_env` 一致。GitHub 公共仓库可匿名读取；飞书任务/消息需要应用凭证，飞书推送需要 Webhook，SMTP 登录使用邮箱服务商的授权码。

逐步填写示例与权限操作见[163 邮箱、GitHub 与飞书配置指南](docs/frontend/v1.2-configuration-163-feishu.md)、[飞书清单授权说明](docs/frontend/feishu-tasklist-permissions.md)。`.env`、`config.yaml` 和数据库已被 Git 忽略；不要把真实凭证写入 README、前端 `VITE_*` 或浏览器 URL。

### 2. 窗口 A：加载凭证并启动后端

程序**不会自动读取 `.env`**。在同一个 PowerShell 窗口完整执行：

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'

Get-Content -LiteralPath '.env' -Encoding UTF8 | ForEach-Object {
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

.\.runtime\venv\Scripts\python.exe -m smart_daily_report.web.main --config '.\config.yaml' --port 8000
```

### 3. 窗口 B：启动操作页面

```powershell
Set-Location 'frontend'
$env:VITE_API_MODE = 'operations'
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000'
npm run dev
```

打开 **[http://127.0.0.1:5173](http://127.0.0.1:5173)**，按[页面使用步骤](#3-在页面上使用)操作：**验证令牌 → 选择日期 → 采集生成 → 核对预览 → 独立确认推送**。任意有效日期（包括周末及配置节假日）都可以生成和推送。首次运行没有历史日报，点击「查看日报」出现“该日期尚无日报”是正常结果；需先采集生成。

修改 `.env` 或 `config.yaml` 后，需要在窗口 A 停止后端，再重新加载环境变量并启动。飞书任务按所选日期的完成时间筛选。旧配置中的 `team.holidays` 字段仍可读取，但不会阻止任意日期的生成或推送。

## 五、只读模式与命令行

### 只查询已有数据库

停止现有后端，启动以下服务；数据库路径应与真实配置中的 `team.database_path` 一致，且数据库已经存在：

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
.\.runtime\venv\Scripts\python.exe -m smart_daily_report.web.main --database '.\data\reports.sqlite3'
```

只读 API 默认以 UTC 偏移返回时间；网页始终把带时区的时间换算为中国标准时间显示。若其他 API 客户端需要不同的响应偏移，可显式指定 IANA 时区，例如：

```powershell
.\.runtime\venv\Scripts\python.exe -m smart_daily_report.web.main --database '.\data\reports.sqlite3' --timezone 'Asia/Shanghai'
```

`--timezone` 只改变 API 返回的时间偏移，不修改 SQLite 中保存的 UTC 时间，也不改变网页的中国标准时间显示；操作模式的 API 响应偏移使用 `config.yaml` 的 `team.timezone`。

如果网页仍显示原始 `...Z` 时间或 `UTC+00:00`，请停止旧的前端服务，按本节步骤启动当前前端并刷新页面；操作模式还应确认后端由当前代码以 `--config` 启动。网页把 `12:36 UTC` 显示为 `20:36（中国标准时间，UTC+08:00）`，不需要重新采集或修改已保存的数据。

前端使用第三节窗口 B 的命令（`VITE_API_MODE='readonly'`）。只读模式不需要操作令牌或外部凭证，不提供生成与推送，也不会自动创建缺失的历史库。

### 不打开页面，使用 CLI

在项目根目录、已加载 `.env` 的终端中执行；不要与页面生成同时运行：

```powershell
# 检查配置和外部依赖
.\.runtime\venv\Scripts\python.exe -m smart_daily_report.main --config '.\config.yaml' --check

# 采集、生成并保存，但不发送
.\.runtime\venv\Scripts\python.exe -m smart_daily_report.main --config '.\config.yaml' --date 2026-10-05 --dry-run
```

把日期改为要采集的任意有效日期。CLI 去掉 `--dry-run` 会直接向已配置渠道发送；需要先预览再确认时，使用浏览器操作模式。

## 常见问题

| 现象 | 处理方法 |
| --- | --- |
| 8000 / 5173 端口被占用 | 已有本项目服务时直接使用；需要切模式时先在原终端 Ctrl+C，不重复启动 |
| 页面无法连接日报服务 | 确认窗口 A 已启动，前端 API 地址与后端端口一致；使用 `127.0.0.1`，不要换成 `localhost` |
| 没有生成或推送控件 | 前端可能是只读模式；设置 `VITE_API_MODE='operations'` 后重启，并配合后端 `--config` |
| 找不到 `.env` / `config.yaml` | 确认启动目录；首次克隆不包含私有配置，按第四节创建并填写 |
| 操作令牌无效 | 输入 `DAILY_REPORT_WEB_TOKEN` 的实际值；修改文件后重新加载、重启后端并验证 |
| 该日期尚无日报 | 只读查询不会生成；选择已保存日期，或在真实操作模式先生成 |
| 今日无记录 / 数据获取失败 | 前者表示该来源读取成功但没有符合日期、成员映射及关键词等规则的记录；如飞书群已有消息却显示 0 条，检查 `team.report_keywords`。后者需核对权限、配置和网络 |
| 推送结果未知或观察超时 | 先查询执行结果并检查邮箱/群；不要通过新请求或删除操作库猜测重发 |

页面服务为本机单 worker 使用。服务商“受理”不等于实际收到；推送后仍应核对收件箱和目标群。构建预览、改端口及测试演示详见[运行说明](docs/frontend/local-run.md)。

## 开发与验证

后端测试：

```powershell
.\.runtime\venv\Scripts\python.exe -m pytest -q
```

前端检查：

```powershell
Set-Location 'frontend'
npm run typecheck
npm run test -- --run --coverage
npm run build
```

浏览器测试另见[运行说明](docs/frontend/local-run.md#操作模式可复现-fixture不访问真实平台)，需要已安装 Chrome 和可用测试端口。**2026-10-20 本机复核**：Python **370 项 / 覆盖率 95.06%**、前端 **152 项**、桌面与手机浏览器 **54 项**；两种前端模式构建、Python wheel 打包及 `npm audit` 均通过。完整结果与未覆盖的真实平台边界见[本次验证记录](docs/project-verification-2026-10-20.md)。历史修复背景见 [v1.6.6 审查记录](docs/project-audit-2026-10-14.md)。测试截图输出到被忽略的 `.runtime` 目录，不改写历史验收材料。

### CI/CD：自动验证与交付构建文件

[GitHub Actions 工作流](.github/workflows/ci.yml)在 PR、`main` 提交和手动触发时运行：安装 Python 3.12 与 Node.js 24，执行后端测试（总覆盖率至少 90%）、前端测试（覆盖率按文件的行、语句、函数、分支均至少 90%），再进行前端类型检查和构建。任一步失败，整次运行即失败。PR 只做检查；`main` 提交或手动运行全部通过后，再构建 Python wheel，并将 wheel 与前端静态文件上传为保留 14 天的产物。

CI 中未设置 `VITE_API_MODE`，因此其前端产物是**只读模式**。若要部署操作页面，需按[本地构建说明](docs/frontend/local-run.md#react-页面第二个-powershell-窗口)设置 `VITE_API_MODE=operations` 和公开的 API 地址后重新构建。构建产物不是已配置好凭证的在线服务。

这属于持续集成与**可供下载的持续交付产物**，没有部署目标，也不会运行日报、发送邮件或向飞书发消息。工作流只使用仓库代码和测试数据，不需要配置 GitHub / 飞书 / 邮箱密钥；本机 `.env`、`config.yaml` 和 SQLite 历史库均不上传。Playwright 浏览器测试仍按本地运行说明执行，**尚未纳入 CI**。在 GitHub 仓库打开 **Actions → CI and delivery → 某次运行 → Artifacts** 可下载产物；手动运行可使用该工作流的 **Run workflow**。当前工作流会显示检查结果，但是否把它设为合并前必需检查，取决于仓库另行设置的分支保护规则。

## 文档导航

| 想了解 | 文档 |
| --- | --- |
| 本机启动、模式切换、构建与浏览器测试 | [本地运行说明](docs/frontend/local-run.md) |
| 账号与凭证配置、飞书清单授权 | [配置指南](docs/frontend/v1.2-configuration-163-feishu.md)、[清单权限](docs/frontend/feishu-tasklist-permissions.md) |
| 飞书访问策略错误 `21001` | [排查说明](docs/frontend/feishu-access-policy-21001.md) |
| 当前代码的测试结果与边界 | [2026-10-20 验证记录](docs/project-verification-2026-10-20.md) |
| 需求、架构及任务依据 | [需求规范](specs/proposal.md)、[架构设计](specs/design.md)、[任务清单](specs/tasks.md) |
| v1.6.6 的修复与清理经过 | [2026-10-14 全项目审查](docs/project-audit-2026-10-14.md) |

更早的版本说明与验收记录保存在 [`docs/frontend/`](docs/frontend/)；它们描述**当时**的实现与测试，不替代上面的当前运行说明。例如 [v1.5.0 发布说明](docs/frontend/v1.5.0-release.md)、[v1.2 最终交付](docs/frontend/v1.2-final-handover.md)及 [OpenDesign 设计证据](docs/frontend/opendesign-evidence.md)。
