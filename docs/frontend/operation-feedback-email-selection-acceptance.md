# 操作反馈与可选邮件收件人：验收与交付说明

日期：2026-10-11。用户已确认规范和实施计划。本轮基于已发布 v1.2.0 改进操作体验；原标签和历史收件证据保持。当前分支为 codex/operation-feedback-email-selection-implementation，GitHub 合并/新版本发布方式仍待交付选择。

## 使用效果

- 查询执行结果会显示加载、完成或错误提示；相同结果再次查询也更新本次查询时间。实际执行日期与查询时间分别展示，暂无记录明确说明。
- 预览成功提示所选日期，并将键盘焦点和视口定位到正文标题；加载、404、鉴权、网络错误和10秒超时均有反馈。后台恢复和自动轮询不抢焦点。
- 邮件地址来自服务器配置，初始全部未选，显示已选人数。选择邮件却未选地址时禁用发送并说明原因；可以只选导师、不选自己，也可以只发飞书。
- 弹窗展示本次实际地址、日期、版本和渠道；取消不发送。接受记录保存地址快照，执行与断线后的原请求重试都使用该快照，新结果展示此次地址，旧记录明确目标未记录。
- 邮件同版本可通过新请求再次确认发送，可能产生重复；不增加逐收件人去重。原请求仍去重，断线不自动重发；飞书已受理/部分受理/未知继续阻断，新邮件可取消飞书后发送。

## 测试证据与边界

| 验证 | 实际结果 | 边界 |
| --- | --- | --- |
| Python全量 | 314 passed，95.24%，退出0 | 包含采集、CLI、Notifier、API、事务和选择目标；外部服务使用替身 |
| 前端全量 | 133 passed，退出0 | 未跳过测试，四个业务文件保留原统计范围 |
| 前端覆盖率 | statements97.42%、branches95.23%、functions98.82%、lines100% | api.ts/operations.ts四项各100%；App.tsx/OperationPanel.tsx逐文件四项均≥90% |
| 类型与构建 | typecheck及readonly/operations两模式build退出0 | 同一代码树、既有锁定依赖 |
| 只读浏览器 | mobile/desktop共14 passed，退出0 | 数据库不变、零采集/通知、安全内容和键盘查询 |
| 操作浏览器 | mobile/desktop共36 passed，退出0 | 真实FastAPI/SQLite/Chromium；HTTP/SMTP边界受控；375×812、1440×900均无页面横向溢出 |
| 本机配置核对 | 认证GET、两个邮箱初始未选、单选确认/取消、查询反馈和正文焦点通过 | 使用实际配置和既有日报数据库副本；原数据库字节不变；零上游调用、零POST与通知 |
| 本轮真实选择性邮件收件 | **未验收** | 尚未另行授权发送，不能用SMTP替身或旧v1.2.0双渠道收件证据代替 |

警告如实保留：Python有既有Starlette/httpx弃用提示1项；浏览器有NO_COLOR/FORCE_COLOR环境提示。详情及先失败后实现记录见 [TDD日志](operation-feedback-email-selection-tdd.md)。本机核对脚本曾遗漏Vite的127.0.0.1绑定，并因团队与成员同名产生标题定位歧义；沿用项目绑定方式、限定二级正文标题后通过。这两项是验收工具修正，不冒充业务RED或产品缺陷。

## N01–N06对应证据

| 规范 | 主要测试及交付 |
| --- | --- |
| N01 查询反馈 | query_feedback_loading_then_completed_even_when_result_is_unchanged、query_feedback_null_reports_empty_without_authentication_message、query_feedback_completion_describes_the_execution_date；浏览器query_feedback_and_readonly_requests |
| N02 预览定位/错误/超时 | preview_feedback_success_focuses_current_report_heading、manual_query_and_preview_timeout_after_ten_seconds、late_preview_after_date_or_token_change_does_not_focus、automatic_preview_does_not_move_focus；浏览器manual_preview_focus_and_feedback、query_preview_feedback_timeout_and_keyboard_focus |
| N03 精确邮箱选择 | test_selected_email_recipient_is_the_only_smtp_target、test_email_selection_invalid_inputs_send_nothing、email_selection_requires_explicit_recipient_and_confirmation、email_selection_lark_only_sends_empty_address_list、email_selection_count_explains_exactly_how_many_addresses_will_receive；浏览器email_selection_sends_only_confirmed_recipient |
| N04 新邮件请求/原请求/飞书 | test_email_new_key_can_resend_same_revision_but_lark_cannot、test_selected_recipients_are_canonical_idempotency_content、lost_delivery_response_keeps_confirmed_recipient_snapshot_on_explicit_original_retry、mixed_repeatable_email_and_blocked_lark；浏览器email_new_confirmation_resends_while_lark_stays_blocked、post_response_loss_no_resubmit |
| N05 历史与目标快照 | test_target_snapshot_and_replay_do_not_use_changed_config、test_legacy_operation_has_unknown_targets_without_database_rewrite、legacy_target_is_not_inferred_from_current_preview；新目标仅在受保护接口可见 |
| N06 SDD/TDD和交付 | proposal→design/ADR-006/contracts→tasks→已确认实施计划；各阶段真实RED/GREEN、完整回归、README及local-run；最终独立审查结果随后记录 |

## 本机启动与发送

按 [README第一节](../../README.md#一当前电脑直接启动) 完整执行双窗口步骤。本轮代码位于 `E:\worktrees\operation-feedback-email-selection\smart-daily-report`，私人配置/数据库位于 `E:\worktrees\v1-2-real-integration\smart-daily-report`；后端在配置目录运行并将PYTHONPATH设为本轮src，前端从本轮frontend启动。已有8000/5173服务时先在其终端Ctrl+C停止，再启动配套新前后端；刷新旧页面不能让旧后端获得新契约。

选择日期→验证本项目令牌→预览/核对正文→选择邮件及具体地址→按需要取消飞书→推送日报→核对弹窗→确认。取消不会发送；只读查看不需要令牌。服务商受理后检查实际邮箱；Gmail还应检查垃圾邮件，并对可信发件人设置过滤器。未知投递先核实；不要删除操作数据库或用新请求猜测恢复断线。旧前端邮件请求缺email_recipients返回400，前后端必须配套。

## 当前交付状态

Task19–20完成；Task21的实现、全套验证和运行材料已准备，最终独立审查与GitHub交付决定按Superpowers收尾。真实选择性收件保留为未验收，不影响对本轮受控测试已通过的事实描述；不会未经本轮授权发送给真实收件人。代码本地保存，尚未替换作者正在运行的服务、推送分支、合并main或新增Release。
