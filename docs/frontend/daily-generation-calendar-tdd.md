# Task25：每日生成与推送日期规则 TDD 记录

- 日期：2026-10-11（Asia/Shanghai）
- 基线版本：GitHub 已发布 v1.4.0
- 发布状态：Task25 已随 v1.5.0 发布。
- 目标：生成、预览与推送允许任意有效日期，包括周末和 `team.holidays` 配置日期；其他输入、版本、渠道、收件人、安全及确认校验不变。
- `team.holidays` 仍由配置读取以兼容旧配置，但不再参与运行时日期决策。

## RED：先写出新业务意图

在修改产品代码前，先增加/改写 CLI、网页生成及网页推送集成测试，覆盖普通周末和显式配置节假日。测试均以可观察业务结果断言：来源 GET 实际发生、日报落库、操作状态成功、推送进入接受结果；同时确认渠道未配置仍被拒绝。

运行：

```powershell
.\.runtime\venv\Scripts\python.exe -m pytest tests/unit/test_http_health_main.py::test_cli_generates_reports_on_weekends_and_configured_holidays tests/integration/test_web_operation_pipeline.py::test_web_generation_collects_on_weekends_and_configured_holidays tests/integration/test_web_operation_pipeline.py::test_delivery_is_allowed_every_day_and_disabled_channel_remains_rejected -q --no-cov
```

RED：6 个参数化场景全部按预期失败。两个 CLI 案例因 `run_report()` 返回 `skipped=True`；两个网页生成案例结果为 `skipped/non_workday`；两个推送案例因 `OperationError(400, "non_workday")` 被拒绝。失败均精确指向旧日期门禁。

## GREEN：最小实现

移除 `run_report()` 与 `OperationService.accept_delivery()` 中按星期及配置假日拒绝的判断。没有改变日期格式解析、来源采集窗口、时区、保存顺序、预览快照、SMTP/飞书选择、令牌或收件人检查，也没有改动前端：现有日期输入没有工作日禁用逻辑，前端仍照常发送所选日期。

目标测试 GREEN：6 passed。全量 Python 测试首轮发现一项旧集成测试仍断言周末应跳过；按新要求将其更新为验证“周末没有启用数据源时仍返回 `no_sources_configured`”，而不是绕过常规配置检查。重新运行结果：327 passed，业务覆盖率 95.27%。

## 回归验证

- Python：`python -m pytest -q` → 327 passed，覆盖率 95.27%（项目要求 ≥90%）。保留一条既有 Starlette `TestClient`/httpx 弃用警告。
- 前端：`npm test -- --run` → 141 passed。
- 前端：`npm run typecheck` → 通过。
- 前端：`npm run build` → 通过。
- `git diff --check`：通过；Git 提示发布说明文件将在后续 Git 操作时从 LF 转为仓库 CRLF，这是行尾规范提示，不是空白错误。

离线测试通过模拟 GitHub/SMTP/飞书边界验证日期门禁已去除，不代表本轮对真实平台执行采集或真实收件验收。未提交、推送或创建新 Release；下一个发布版本号尚未确定。
