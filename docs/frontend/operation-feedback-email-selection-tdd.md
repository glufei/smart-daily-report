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


## Task20

- 服务器意图 RED：7 failed / 6 已有保护直接 passed，退出1；GREEN13 passed。覆盖单选精确 To、空/缺失/重复/非字符串/空格/换行/配置外/仅飞书带邮箱、两位选择规范化、原键变目标冲突、邮件新键允许而混合重复飞书拒绝、配置变化后的接受快照与旧记录只读。
- 客户端 RED3 failed（缺 DTO/目标核对/历史默认值），GREEN3 passed；页面独立 RED8 failed（缺勾选和确认、邮件仍被旧规则禁用、缺历史目标说明），GREEN8 passed。先客户端后页面，避免 DTO 错误掩盖页面意图失败。
- 浏览器替身目标证据 RED1 failed（缺第二位候选）；随后补充两位虚构邮箱及从 MIME To 记录实际目标，fixture3 passed。
- 增加断线原请求显式重试目标不变、仅飞书邮箱数组为空、四种飞书阻断回归；这些既有保护直接通过，如实记为回归而非新 RED。
- 完整相关测试：Python104 passed / 既有警告1，前端110 passed，typecheck退出0；均使用受控 HTTP/SMTP，零真实外部发送。
- 裁决：旧邮件新键禁止重发与本轮已批准需求冲突，选择主动再次发送；旧测试保留为飞书阻断/原键未知或中断不得自动执行，未删除保护测试。公共 helper 明确勾选虚构地址，不把页面默认改回全选。没有按收件人去重账本。
- 剩余：Task21完整浏览器/覆盖率/构建/文档/审查；真实选择性收件未授权、未验收。


## Task21

- 复用Task20.8已先失败后通过的虚构目标记录替身；浏览器新增只选导师/取消、新确认邮件再次发送而飞书保持、10秒主动预览超时与键盘定位。旧丢响应、双击、原键恢复、只读、恶意文本与版本变化测试保持。
- 规范核对发现已选人数未展示：先新增 email_selection_count_explains_exactly_how_many_addresses_will_receive，RED1 failed、退出1（缺0位文本）；补一行人数提示后全量前端133 passed、退出0，原四文件四项覆盖率均≥90%。
- Python全量314 passed/95.24%、既有警告1；typecheck及readonly/operations build退出0；只读浏览器14 passed/退出0。操作浏览器36 passed/退出0，人数补充后再次完整复验，不以旧截图代替最终代码。
- 实际配置只读核对：使用两个真实配置邮箱及10/5已保存日报的数据库副本，认证、查询完成、预览正文焦点、初始未选和单地址确认/取消通过；原数据库字节不变；无采集、POST或实际通知。脚本首次遗漏显式127.0.0.1绑定、随后团队和成员同名导致标题定位歧义；沿用项目启动绑定、限定二级标题后通过，均为工具错误，不计RED。
- README/local-run明确当前代码和配置目录、选择单邮箱、独立确认、邮件主动再次发送、飞书限制、原请求恢复与Gmail垃圾邮件核对。公共截图/fixture仅虚构地址。真实选择性收件未授权、未验收；版本仍1.2.0，旧标签不变，GitHub交付待选择。
