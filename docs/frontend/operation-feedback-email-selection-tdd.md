# 操作反馈与可选邮件收件人：TDD 记录

日期：2026-10-11。规范与实施计划已由用户确认，执行方式为本会话逐项执行。以下是真实运行证据，外部 HTTP/SMTP 均为受控替身；本轮未发送真实通知。

## Task19

- 基线：pytest 300 passed，覆盖率 95.28%，既有警告 1；前端全量 102 passed，退出 0。
- 新增测试位于 frontend/src/App.operations.test.tsx：查询加载/完成/空结果/跨日期、预览加载/标题焦点、两个动作 9999ms/10000ms 超时、迟到响应、自动预览不抢焦点及预览错误零发送，共 13 项。
- RED：前端聚焦运行 7 failed / 6 passed，退出 1。缺失加载提示、查询完成/空记录反馈、正文焦点及超时。直接通过的现有竞态/鉴权/错误保护如实记为回归。
- 测试修正：两处 mock 复用已消费 Response，初次失败含 invalid_response；修正为每次 GET 新 Response 后，用原始未修改生产文件再次运行这两项：2 failed，退出 1，明确因缺少空记录/完成反馈失败。原失败不能作为它们正确 RED 的证据。
- 工具修正：一次编辑从 frontend 目录使用根目录相对路径失败，未写文件；修正后运行，不计功能 RED。
- GREEN：全部前端 115 passed，退出 0；typecheck 退出 0。
- 浏览器：mobile 375×812、desktop 1440×900 的 manual_preview_focus_and_feedback / query_feedback_and_readonly_requests，4 passed，退出 0。真实 FastAPI/SQLite 与 Chromium，外部边界受控；正文聚焦/实际可见、GET-only、查询更新时间和零通知通过。
- 警告：浏览器测试有既有 NO_COLOR/FORCE_COLOR 提示，不影响退出状态；不隐瞒警告。
- 最小修改：就近加载/完成反馈、明确无记录、10 秒主动 GET 上限、查询本次时间与执行时间分开，仅主动预览定位正文；保留原 POST/原键恢复与后台观察逻辑。
- 裁决：current GET 可返回 null，已知 operation-ID GET 不可返回 null；空结果测试使用 current 契约，已知 ID 的 404 保持明确错误。否则会以非法测试响应假造业务失败。
- 剩余：Task20 邮箱选择/邮件主动再次发送、Task21 完整回归/文档与整体审查；真实选择性发送尚未授权/验收。

## 复现命令

前端目录：`npm test -- --run src/App.operations.test.tsx -t 'query_feedback|preview_feedback|manual_query_and_preview_timeout|late_preview_after|automatic_preview_does_not_move_focus'`；全部单元 `npm test -- --run`；类型 `npm run typecheck`；浏览器 `npx playwright test --config playwright.operations.config.ts -g 'manual_preview_focus_and_feedback|query_feedback_and_readonly_requests'`。浏览器解释器按计划 DAILY_REPORT_PYTHON 配置，PYTHONPATH 指向隔离工作区 src，不加载私人 config.yaml/.env。
