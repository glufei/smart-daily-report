# Task24：成员日报总结 TDD 与验收记录

- 日期：2026-10-11（Asia/Shanghai）
- 适用代码状态：本地源码 v1.4.0，未推送或发布
- 最新 GitHub 发布版本仍为：v1.3.1
- 范围：在每位成员日报开头展示基于结构化来源记录的数量总结，保留原有三个明细板块。

## 设计规则

- “今日总结”依次列出代码提交数、已完成任务数、协作沟通消息数。
- 来源成功但该成员没有记录时显示 `0 条`；来源失败时显示 `获取失败，数量未知`，不能把失败说成零。
- 总结只做确定性计数，不使用 AI、不改写或推断来源内容。
- Markdown（飞书）和 HTML（邮件）显示相同总结及明细。既有 SQLite 历史快照不回写；不改数据模型、HTTP API、采集及推送流程。

## TDD 证据

先新增两个意图测试，覆盖三来源有记录、正常零记录、单来源失败，以及 Markdown/HTML 的状态和明细一致性。未修改生产模板前运行：

```powershell
.\.runtime\venv\Scripts\python.exe -m pytest tests/unit/test_generator.py -q
```

RED 结果：新增的两个测试均因当前模板没有“今日总结”及来源级总结状态而失败；其余 5 项通过。该单文件运行还触发仓库配置的 90% 全项目覆盖率门槛，因为未运行全套测试，结果为预期。失败不是语法或测试设置错误。

随后只在 `src/smart_daily_report/generator/template.py` 增加统一的计数/状态规则，并分别渲染到 Markdown 与 HTML。GREEN 命令：

```powershell
.\.runtime\venv\Scripts\python.exe -m pytest tests/unit/test_generator.py -q --no-cov
```

实现后的首轮目标测试还发现两处测试预期需校准：一处 Markdown 明细中的冒号按既有安全规则转义，另一处安全回归测试需计入新增的固定总结标题。修正测试断言以符合既有渲染约定后，GREEN 结果为 7 passed。全量回归命令：

```powershell
.\.runtime\venv\Scripts\python.exe -m pytest -q
```

结果：324 passed，覆盖率 95.35%，高于 90% 门槛。输出有一条既有 `StarletteDeprecationWarning`（`httpx` 与 `starlette.testclient` 的弃用提示）；本轮未改测试栈依赖。`git diff --check` 通过。

## 验收边界

本轮未访问真实 GitHub/飞书数据，未调用 SMTP 或飞书推送，也未进行版本号更新、Git 提交、PR 或发布。改动限于生成模板、生成器测试及需求/设计/接口/任务/运行说明文档；前端页面本身和 HTTP API 未更改。
