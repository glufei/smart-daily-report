# 2026-10-20 项目复核与文档校准

本次以 `main` 的 `36bd026`（v1.6.6）为起点，核对运行入口、示例配置、采集与推送边界、前端两种模式、测试、打包、CI 和当前说明文件。只修改与现行行为不一致或不清晰的文档；2026-10-14 的[修复审查记录](project-audit-2026-10-14.md)及更早验收记录保留为历史证据。

本机环境：Windows、Python 3.12.14、Node.js 24.15.0、npm 11.12.1。

## 本机验证

| 检查 | 2026-10-20 结果 |
| --- | --- |
| Python 单元与集成测试 | `370 passed`；总覆盖率 `95.06%`，超过配置的 `90%` 下限 |
| 前端单元测试 | `152 passed`；语句 `97.6%`、分支 `95.2%`、函数 `98.88%`、行 `100%`；各纳入统计的文件均通过 `90%` 门槛 |
| Playwright 只读页面 | 手机与桌面共 `16 passed`；SQLite 保持不变，无禁止的采集或推送调用 |
| Playwright 操作页面 | 手机与桌面共 `38 passed`；使用本地真实 FastAPI/SQLite，外部 HTTP/SMTP 为模拟边界，无真实通知 |
| 前端类型检查及构建 | `npm run build` 在只读模式和 `VITE_API_MODE=operations` 模式均通过 |
| Python 包 | 从干净的 `git archive` 源码构建 `smart_daily_report-1.6.6-py3-none-any.whl` 成功 |
| 依赖一致性与 npm 公告 | `pip check` 通过；`npm audit --audit-level=high` 报告 `0 vulnerabilities` |
| 文档相对链接与私有文件 | 检查 `55` 个 Markdown 文件的 `158` 个相对链接，目标均存在；README、运行说明和本记录的本地章节锚点也已核对；`.env`、`config.yaml`、数据库和 `.runtime` 路径均未被 Git 跟踪 |

测试中有一条 Starlette/httpx TestClient 上游弃用提示；Playwright 有 `NO_COLOR`/`FORCE_COLOR` 提示。它们不影响本次断言和退出码。wheel 在干净归档副本中构建，未改动工作区内被 Git 忽略的旧构建元数据。`npm audit` 只反映查询当时的 npm 公告结果，不等于完成全部依赖安全审计。

## 文档校准

- README 将当前验证数字与 2026-10-14 的历史审查分开，明确首次安装、真实/只读模式、手动推送和 CI/CD 的边界。
- `team.report_keywords: []` 表示**不设包含关键词条件**，但日期、成员映射和敏感词过滤仍生效；旧规范中“必须命中关键词”的表述按现行代码修正。
- 项目当前按需手动运行，未配置定时任务；旧设计中的外部调度只是曾经预留的触发方式，不代表现在已经启用。
- CI 默认构建**只读**前端。操作页面的生产构建需显式设置 `VITE_API_MODE=operations` 与公开 API 地址。Playwright 仍在本地跑，未包含在 GitHub Actions 工作流中。
- 已删除的旧日历工具只保留在历史任务记录中，不再描述为当前 `shared/` 模块。

## 验证边界

本次浏览器测试使用隔离的固定数据，不读取本机真实 `.env`、真实配置或日报库；没有调用 GitHub/飞书生产 API，没有登录 SMTP，也没有发送邮件或飞书消息。外部平台权限、真实收件、真实数据的新鲜度及端到端性能未在本次复核中重新验收。测试通过说明受测的本机逻辑与模拟接口符合断言，不保证外部服务始终可用。

复现命令和启动步骤见 [README](../README.md#开发与验证) 与 [本地运行说明](frontend/local-run.md)。
