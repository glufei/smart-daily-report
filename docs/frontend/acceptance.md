# v1.1 验收记录

日期：2026-09-30。Task 11–14 实现与验收完成；已确认的本机只读范围交付。

## Task 12：只读 API

| 规范 | 验证依据 | 结果 |
|---|---|---|
| F02 数据/顺序/状态 | `test_query_preserves_content_order_and_only_exposes_contract_fields`、`test_empty_report_and_partial_source_failure_are_both_valid_history` | 通过 |
| F03 日期、缺失与读取错误不能混淆 | `test_invalid_date_is_400_before_any_database_read`、缺失库/空表/损坏库/异常读取/坏 JSON/无效状态系列测试 | 通过 |
| F04 查看无副作用 | `test_query_never_invokes_generation_or_notifications_or_changes_database`、`test_shared_reader_uses_sqlite_read_only_mode`、写方法拒绝测试 | 通过 |
| F05 白名单/过滤/安全错误/本机 Origin | 响应字段测试、`test_filtered_message_does_not_leak_through_new_query_surface`、不可信链接测试、Origin/Host 测试 | 通过 |
| F07 CLI 兼容与回归 | 全部既有测试、独立基础安装环境导入、Web 启动入口测试 | 通过 |

测试文件：`tests/unit/test_web_api.py`；相关既有测试也参与全量运行。

实际命令：`.runtime/venv/Scripts/python.exe -m pytest -q`。结果 **98 passed，无跳过，总业务代码覆盖率 92.02%，退出码 0**。新增 Web 代码后的首轮仅运行既有 64 项测试，虽然断言通过但覆盖率 79.08%、门槛失败；补齐新接口意图测试后达到上述结果，未降低覆盖率阈值。一项上游 Starlette/httpx TestClient 弃用提示保留，当前测试功能通过。

独立 `.runtime/cli-venv` 只执行 `pip install -e .`（不安装 dev/web），然后导入 `smart_daily_report.main` 并确认 `find_spec('fastapi')` / `find_spec('uvicorn')` 均为空，退出码 0。证明基础 CLI 安装不需要 Web 依赖。

实际本机 smoke：使用临时 SQLite 保存两个虚构成员，任务来源为 failure；启动 `daily-report-web --database .runtime/api-smoke.sqlite3`，监听 `127.0.0.1:8000`。PowerShell HTTP 查询 2026-09-25 返回 200、两位成员、`lark_tasks: failure`、`Cache-Control: no-store`；查询不存在的 2026-09-26 返回 404。没有访问真实数据源、生产数据库或发送通知。

## Task 11：OpenDesign UI 原型

F01 来源/版本/许可证/发行包 hash、UI 项目与会话、实际输入、两版源文件及截图见 [OpenDesign 证据](opendesign-evidence.md)。两版由真实软件 UI 生成，第二轮改进正文/记录字号及日期/查询控件高度，原文件不手工改写。F02/F03 六种状态、全部成员三板块、零记录及来源失败；F06 两视口及键盘，复现脚本 `prototypes/check-prototypes.cjs` 运行结果 **28 项通过、退出 0**，细项 `prototypes/checks.json`。F05 只含虚构数据，无越界产品动作。

## Task 13–14：页面与真实 HTTP 验收

| 规范 | 自动化/证据 | 结果 |
|---|---|---|
| F02 全部成员/固定顺序/时间/来源 | `src/App.test.tsx` 的历史展示测试；`e2e/reports.spec.ts` 的 real saved reports；`screenshots/mobile-normal.png`、`desktop-normal.png` | 通过 |
| F03 400/404/500/JSON/网络/10s超时/竞态 | App/api 意图单元测试；E2E missing history、storage read failure、offline、late real A；missing/source-failure/storage-error/loading 截图 | 通过 |
| F04 只读及无通知 | Python 禁用替身测试；fixture 服务禁用采集/生成/写入/通知；E2E teardown 比较两库 SHA256，无 forbidden-call 文件 | 通过 |
| F05 过滤/白名单/文本/链接 | Python whitelist/filter/URL 测试；App 外部文本测试；E2E malicious records、正常日志 marker 扫描；前端构建产物 fixture/私有 marker 扫描 | 通过 |
| F06 375×812、1440×900、键盘、构建 | 全部 E2E 两个 project 的 overflow/键盘断言，含长团队名、长仓库名和长消息；npm ci/typecheck/build/Vitest；生产 preview 两视口真实 HTTP smoke | 通过 |
| F07 CLI 兼容与原场景 | 98 项全量 Python、92.02% 覆盖率，基础安装 CLI 导入/--help，无 FastAPI/Uvicorn；既有集成全部通过 | 通过 |

实际命令（frontend 目录）：`npm ci`、`npm run typecheck`、`npm run build`、`npm run test -- --run` 均退出 0；Vitest **2 个文件、15 项通过**。`npm run test:e2e` **14 passed (14.5s)，退出 0**，无跳过；自动启动真实 FastAPI、临时 SQLite 与 Vite，使用 Chrome，不 Mock 日报 JSON。

E2E 首轮 14 项断言及 teardown 内容验证通过，但受限进程环境未结束子服务清理；主动 Ctrl+C 后退出 1，未将该轮视为整条命令通过。随后允许测试子进程完整清理重跑得到上述退出 0。首次 TypeScript 检查发现测试替身参数元组类型错误，修正后 typecheck/build 退出 0。Playwright 的 NO_COLOR/FORCE_COLOR 提示保留。

生产构建实际 `npm run preview` 监听 127.0.0.1:4173，对 8000 的临时示例 API 查询两视口均通过；`screenshots/production-375.png`、`production-1440.png`。构建 JS/CSS 不包含 fixture 成员、敏感标记、SMTP 密码键、数据库路径或工作目录。

设计交接差异见 [DESIGN.md](DESIGN.md)：产品移除演示控件，加入真实来源状态/记录字段，修复原型 column flex-basis 的手机空白。额外 UI 修正未能提交的工具错误有记录，不能宣称第三版；两版 UI 迭代已满足 F01。检查过手机/桌面实际截图，修复后输入与查询按钮间为正常 12px 间距。

## 实际验证边界

- 本次没有访问实际 GitHub/飞书/SMTP、读取生产数据库或推送通知；真实外部采集/投递历史仍以 v1.0 记录为准。
- 浏览器验收在本机 Chrome 完成，未宣称其他浏览器或公网部署通过；这不属于已确认范围。
- 导师未给软件链接，采用用户已确认的 nexu-io/open-design；若导师后续指定不同产品，需要新一轮规范变更。
- 上游 Starlette/httpx 弃用提示尚存，不影响本次 98 项测试结果。没有未通过的 v1.1 Checklist。
