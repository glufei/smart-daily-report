# 操作反馈与可选邮件收件人 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 查询/预览有明确反馈，维护者能勾选配置邮箱，并在独立确认后主动再次发送同一版本邮件。

**Architecture:** 沿用 React/fetch/Zod 与 FastAPI/SQLite 操作层。后台校验配置邮箱子集，保存本次目标快照，调用现有 send_email 一次发送所选列表；请求级幂等和飞书防重复保持。只改本轮反馈、目标与对应兼容边界。

**Tech Stack:** React 19.3.0、TypeScript、Vite、Zod 4.6.5；Python ≥3.11、FastAPI 0.142.2、SQLite/标准库 SMTP；pytest、Vitest、React Testing Library、Playwright。

**Spec:** [proposal §8/N01–N06](../../../specs/proposal.md)、[design §1.6](../../../specs/design.md)、[ADR-006](../../../specs/adrs/006-operation-feedback-email-selection.md)、[web-operations §7](../../../specs/contracts/web-operations.md)、[Task19–21](../../../specs/tasks.md)。书面规范已获用户 2026-10-11“开始工作”确认；本计划待审，业务实现未开始。

## Global Constraints

- 严格遵循 TDD，必须先编写失败的单元/集成测试用例，再实现通过测试的业务代码。逐循环提供测试文件、意图及正确原因的 RED，GREEN 后才提交本循环；语法/依赖错误不计 RED。
- 已确认本会话逐项执行；计划审查后使用 executing-plans，实施前按 using-git-worktrees 检查隔离环境。当前文档分支为 codex/operation-feedback-email-selection；不在 main 写业务代码，不改真实配置/数据库。
- 主动查询/预览的 GET 等待沿用历史查询 10 秒上限；后台操作自动观察 120 秒。日期/Token 变化和失效 ticket 不更新内容、反馈或焦点；停止等待不取消后端任务。
- 375×812、1440×900 两视口；查询、预览、邮箱勾选和确认/取消可用键盘操作。只主动预览成功定位并聚焦正文，状态恢复/轮询不抢焦点。
- 邮件默认无收件人选择；选 email 必须提供非空、无重复、完全匹配配置的 email_recipients。仅飞书时该数组为空；缺失邮件目标不回退全量。
- 同版本邮件新键、独立确认可以主动再次发送；不新增按收件人去重或逐人结果账本。保留同键去重、单活动槽、版本校验、无自动重发、重启中断及飞书原防重复规则。
- 具体邮箱只通过认证操作接口/内存显示，不进入公共历史 GET、日志或仓库中的真实 fixture。历史缺目标为 null，显示“历史记录未记录具体收件人”，不补造旧目标。
- 复用 send_email(report, recipients, smtp_config)，一次 SMTP 提交所选列表；Notifier 公共签名、CLI 默认全量目标、DailyReport、来源适配和工作日规则保持，不新增依赖。
- Python 总业务覆盖率 ≥90%；新增/修改前端业务模块 lines/statements/functions/branches 分别 ≥90%，不缩减现有四模块统计范围；完整测试、类型检查和两模式构建通过。
- 本轮自动测试只用受控 HTTP/SMTP；真实发送需要另行核对版本和目标并明确授权。SMTP 受理与实际收件分别记录，不把离线测试冒充真实验收。

## Review Focus

1. 查询返回 null 或同一状态：本次完成反馈必须出现，旧执行卡片不能冒充新结果。由 Task19 的 empty/refresh 单元测试约束。
2. 预览响应晚于日期/Token 切换或超过 10 秒：迟到响应不能抢焦点或恢复旧确认。由 Task19 的 invalidation/timeout 单元与浏览器测试约束。
3. 邮箱列表乱序、重复或带空格/换行：合法乱序同指纹；重复/变形/配置外地址拒绝且零发送。由 Task20 的 canonical/invalid 服务器与客户端测试约束。
4. 发送前后配置变化或旧库无目标：已接受目标快照不替换；原键回放仍返回原记录，历史地址不猜测。由 Task20 的 snapshot/replay/legacy 测试约束。
5. 同版本邮件再次发送同时选了已受理飞书：组合请求整体拒绝；仅邮件新键可用，丢失响应仍只查原键。由 Task20/21 的 mixed/repeat/loss 测试约束。

## 文件职责与验证入口

| 文件 | 本轮职责 |
|---|---|
| frontend/src/OperationPanel.tsx | 就近动作反馈、10 秒主动 GET 等待、邮箱选择、目标确认与结果展示 |
| frontend/src/App.tsx | 仅主动预览成功的正文标题焦点/滚动；历史查看保持 |
| frontend/src/styles.css | 必要的就近反馈与邮箱布局/焦点样式，沿用现有类 |
| frontend/src/operations.ts | 严格新 DTO、email_recipients 请求及固定错误码 |
| src/smart_daily_report/web/operation_schemas.py | 输入/输出目标字段与严格约束 |
| src/smart_daily_report/web/operations.py | 目标白名单、指纹/快照及 SMTP 子集调用 |
| src/smart_daily_report/shared/operation_storage.py | 持久目标快照，跨请求仅飞书阻断；原键/活动槽保持 |
| src/smart_daily_report/web/operation_routes.py | recipient_not_configured 固定安全文案 |
| frontend/src/test/operationFixture.ts、现有单元/集成/e2e 文件 | 虚构配置邮箱和意图断言，不加载私有运行数据 |
| README.md、docs/frontend/local-run.md | 实现完成后补实际选择/反馈/再次发送操作说明 |
| docs/frontend/operation-feedback-email-selection-tdd.md、operation-feedback-email-selection-acceptance.md | 创建本轮真实 RED/GREEN/checkpoint 与 N01–N06 映射 |

执行环境准备：先读当前 skills/TDD 与隔离工作区规则，检查现有 worktree 和分支；用户已有隔离工作区授权，不重复询问。此处不复制或修改私有 config.yaml/.env/日报库。测试解释器复用本机现有环境，工作目录始终为选定的实现工作区：

```powershell
$taskPython = 'E:\MyCode\smart-daily-report\.runtime\venv\Scripts\python.exe'
$env:PYTHONPATH = (Resolve-Path 'src').Path
$env:DAILY_REPORT_PYTHON = $taskPython
```

下文 Python 命令在实现工作区根目录执行，npm 命令在其 frontend 目录执行；该路径只是当前机器已验证的测试环境，另一台机器应使用其已安装项目依赖的解释器。浏览器测试端口 8775/5174 为受控 fixture；用户真实服务 8000/5173 不作为自动测试目标。浏览器两套依次执行。

## Task 19：明确查询/预览反馈（N01、N02，依赖规范/计划审查）

**Files:** Modify OperationPanel.tsx、App.tsx、必要 styles.css；Test App.operations.test.tsx、e2e/operations.spec.ts；Create 本轮 tdd.md。

**Interfaces:** Consumes 现有 getCurrentOperation/getOperation/getOperationByKey/getPreview(date, token, signal)。Produces `onPreview(value: PreviewView | null, focus?: boolean): void`（可选 focus 默认 false）；只有主动 previewReport 成功传 true，App 的 onPreview 校验日期后更新 controlPreview 并在渲染后 focus/scroll 正文标题。现有自动 show 调用保持一个参数。

- [ ] **19.1 写失败测试**：在既有 setup/response 测试辅助函数上添加下列测试；冻结测试时钟、延迟 Promise/假 timer，SMTP/POST 次数为零。执行结果查询与现有业务终态 message 分开断言。

```ts
// query_feedback_loading_then_completed_even_when_result_is_unchanged
expect(screen.getByRole('button', { name: '正在查询执行结果…' })).toBeDisabled();
expect(screen.getByText(/执行结果查询完成/)).toBeVisible();
expect(screen.getByText(/本次查询时间/)).toBeVisible();
// query_feedback_null_clears_old_operation_and_reports_empty
expect(screen.getByText('暂无执行记录')).toBeVisible();
expect(screen.queryByRole('region', { name: '推送执行结果' })).not.toBeInTheDocument();
// preview_feedback_success_focuses_current_report_heading
expect(screen.getByRole('heading', { name: '示例研发团队' })).toHaveFocus();
expect(screen.getByText(/已加载 2026-09-25 日报预览/)).toBeVisible();
```

同时添加 `manual_query_and_preview_timeout_after_ten_seconds`、`late_preview_after_date_or_token_change_does_not_focus` 和 `automatic_preview_does_not_move_focus`；明确 404/网络/401 文案与失败后无有效旧推送预览。时间测试须断言 9999ms 未超时、10000ms 提示以及迟到结果不覆盖。

- [ ] **19.2 运行 RED**（前端目录）：`npm test -- --run src/App.operations.test.tsx -t 'query_feedback|preview_feedback|manual_query_and_preview_timeout|late_preview_after|automatic_preview_does_not_move_focus'`。预期行为断言失败，记录退出码；原已存在竞态保护若直接通过如实标为回归保护，不制造 RED。
- [ ] **19.3 最小实现**：OperationPanel 的 queryResult/previewReport 保持原签名，新增各动作的加载/完成/失败反馈与本次时间；null 清空 operation，不复用“令牌已验证”作反馈。主动 GET 用独立 10000ms 超时并按 ticket 清理，不能污染原 120000ms 轮询 deadline。App 保存标题 ref，渲染后消费 focus 标记；日期/Token/预览失效清掉标记。必要滚动尊重 prefers-reduced-motion；不拆分无关组件或引入依赖。
- [ ] **19.4 运行 GREEN/回归**：重跑 19.2，再运行 `npm test -- --run src/App.operations.test.tsx src/App.test.tsx` 和 `npm run typecheck`，预期均退出 0。添加浏览器 `manual_preview_focus_and_feedback` / `query_feedback_and_readonly_requests`，在两个视口断言标题焦点、实际滚动可见、GET-only 和无横向溢出；运行 `npx playwright test --config playwright.operations.config.ts -g 'manual_preview_focus_and_feedback|query_feedback_and_readonly_requests'`。jsdom 不证明真实滚动。
- [ ] **19.5 checkpoint/提交**：写 RED/GREEN 与剩余事项、更新 Task19 实际通过项。只提交本任务文件和记录，提交说明 `feat: clarify operation query and preview feedback`；全量交付仍待 Task21。

## Task 20：配置邮箱选择与邮件主动再次发送（N03–N05，依赖 Task19）

**Files:** Modify operation_schemas.py、operations.py、operation_routes.py、operation_storage.py；frontend operations.ts/OperationPanel.tsx/operationFixture.ts；Test test_web_operations.py、test_operation_storage.py、test_web_operation_pipeline.py、operations.test.ts、App.operations.test.tsx；必要适配旧 e2e/fixture 以保持新契约一致。

**Interfaces:**

- `DeliveryRequest.email_recipients: list[str]` 默认为 []；严格字符串、无重复，email 选定时非空，不选 email 时必须空，排序规范化。配置白名单校验在 OperationService。
- `OperationView.email_recipients: list[str] | None = None`；新 delivery 保存选择（仅飞书 []），generation/旧 payload 为 null。`EmailTargetView(TargetView).recipients: list[str]` 必需，TargetViews.email 使用该类型、lark 不变。
- `OperationStore.accept(..., *, before_insert=None, email_recipients: list[str] | None = None) -> tuple[dict, bool]`；快照复制保存，其他方法保留目标；调用方不得在返回后修改接受记录所用目标。
- `deliverReport(date: string, revision: string, channels: ('email'|'lark')[], emailRecipients: string[], token: string, requestId: string, signal: AbortSignal)` 返回原 Promise<OperationView>；PendingRequest 的 delivery 与 Confirmation 增加 emailRecipients 快照。固定同步码 recipient_not_configured，不加入异步 SafeErrorCode。

- [ ] **20.1 写服务器失败测试**：先写测试而不修改 production DTO。复用 delivery_service/config、假 SMTP 的 sends 和 MockTransport 的 requests；该测试内配置两邮箱，生成/预览后清空请求计数。

```python
def test_selected_email_recipient_is_the_only_smtp_target(config, tmp_path):
    import json
    from smart_daily_report.web.operation_schemas import DeliveryRequest
    config = replace(config, smtp=replace(config.smtp, recipients=['member@example.com', 'mentor@example.com']))
    service, store, cfg, preview, requests, sends = delivery_service(config, tmp_path)
    body = DeliveryRequest.model_validate_json(json.dumps({
        'report_date': '2026-09-25', 'report_revision': preview.report_revision,
        'channels': ['email'], 'email_recipients': ['mentor@example.com']}))
    accepted = service.accept_delivery(body, str(uuid4()))
    service.execute(accepted.view.operation_id, accepted.snapshot)
    assert len(sends) == 1 and str(sends[0]['To']) == 'mentor@example.com'
    assert requests == []
    assert store.get(accepted.view.operation_id)['email_recipients'] == ['mentor@example.com']
```

同循环添加：`test_email_selection_invalid_inputs_send_nothing`（缺失/空/重复/非字符串/空格/换行/配置外，以及仅飞书携带邮箱）、`test_selected_recipients_are_canonical_idempotency_content`、`test_email_new_key_can_resend_same_revision_but_lark_cannot`、`test_target_snapshot_and_replay_do_not_use_changed_config`、`test_legacy_operation_has_unknown_targets_without_database_rewrite`。通过 TestClient 断言 400 固定文案、GET 认证、零通知；SMTP 本轮仍一次提交选定列表。

- [ ] **20.2 运行服务器 RED**（根目录）：`& $taskPython -m pytest --no-cov tests/unit/test_web_operations.py tests/unit/test_operation_storage.py tests/integration/test_web_operation_pipeline.py -k 'selected_email_recipient or email_selection or selected_recipients or email_new_key or target_snapshot or legacy_operation' -q`。预期选择/快照尚未实现的意图失败；使用现有导入，语法/工具错误需先修正，不算 RED。
- [ ] **20.3 实现服务器契约与最小调用**：按 Interfaces 新增字段和验证。指纹包含 sorted email_recipients；accept 的 before_insert 验证白名单、版本，事务持久捕获选择；后台 send_email 只传 record 中列表，缺有效快照保守不发送。Store 的跨请求重复检查仅选 lark，所有同键与活动槽规则保持。旧 payload 缺字段由响应模型默认 null 解读，不改库；预览 recipients 配置顺序去重，不输出凭证。
- [ ] **20.4 服务器 GREEN 与旧约束裁决**：重跑 20.2；完整运行上述三个测试文件。更新旧 DeliveryRequest/HTTP helper 明确传虚构配置邮箱；将旧“邮件新键禁止重复”断言替换为已确认新行为，保留飞书、旧键、中断、未知无自动执行、版本与零采集断言，不能删除测试来凑通过。CLI/Notifier 既有测试保持原意。
- [ ] **20.5 写前端失败测试**：operations.test.ts 验证严格新 DTO、配置外错误文案、POST 日期/版本/渠道/邮箱和原键；App.operations.test.tsx 验证初始所有邮箱未选、空选择禁用原因、只选导师确认地址、取消零 POST、仅飞书空数组、旧目标 null 说明、accepted/unknown 邮件仍能独立确认新请求且风险可见。

```ts
// email_selection_requires_explicit_recipient_and_confirmation
expect(screen.getByRole('checkbox', { name: 'mentor@example.com' })).not.toBeChecked();
expect(screen.getByText('请选择至少一位邮件收件人')).toBeVisible();
// 取消飞书、勾选导师、打开确认框后：
expect(within(screen.getByRole('dialog')).getByText('mentor@example.com')).toBeVisible();
expect(within(screen.getByRole('dialog')).queryByText('member@example.com')).not.toBeInTheDocument();
// 确认后的 POST 体：
expect(JSON.parse(deliveryCall[1].body as string).email_recipients).toEqual(['mentor@example.com']);
```

添加 `lost_delivery_response_keeps_confirmed_recipient_snapshot`（原 POST 失败后 by-key GET，不自动重发；显式原键重试保持邮箱）、`mixed_repeatable_email_and_blocked_lark_never_sends`、`changing_date_token_or_preview_invalidates_recipient_confirmation`。

- [ ] **20.6 前端 RED**（前端目录）：`npm test -- --run src/operations.test.ts src/App.operations.test.tsx -t 'email_selection|confirmed_recipient|repeatable_email|recipient_confirmation|legacy_target'`。观察因为缺字段/选择/确认快照的行为失败；现有防竞态/无自动重发直接通过的项目如实记录。
- [ ] **20.7 最小前端实现**：Zod 的 OperationView 增加 nullable 目标默认 null，预览邮件要求 recipients；客户端 POST 增加规范化选择，返回目标须与确认一致。OperationPanel 默认邮箱选择 []，邮件与飞书可独立勾选；email 不按 previous 阻断，新确认列具体目标及重复风险，lark 仍按原 blocked。未确认 POST 仍只能查原键，不能启用新发送；新结果显示此次目标，历史 null 明确未记录。旧 outcomeText 中“不能整渠道重发”改为描述实际部分受理/未知及核实建议，相关飞书错误文案保留约束。
- [ ] **20.8 GREEN/集成 checkpoint**：运行 `npm test -- --run src/operations.test.ts src/App.operations.test.tsx`、`npm run typecheck` 与 20.4 Python 文件，预期退出 0。前后端 fixtures 配套：e2e 配置增第二个虚构邮箱，旧需要邮件的流程显式勾选，不把默认改回全量；增量事件记录 To 地址用于 Task21，Notifier 实现不改。记录旧规则变更与未完成真实验收；提交 `feat: select configured email recipients for confirmed delivery`。

## Task 21：浏览器完整回归与交付（N01–N06，依赖 Task19–20）

**Files:** Modify frontend/e2e/operations.spec.ts、serve_operations_fixture.py、tests/unit/test_operations_fixture.py、README.md、docs/frontend/local-run.md；Create 本轮 acceptance.md/必要虚构数据截图；更新已批准 specs 的实际状态/checkpoint。

**Interfaces:** 复用 Task19 的 onPreview focus 与 Task20 的 DTO；fixture event 的 email 记录增加 `recipients: list[str]`（从 MIME To 读取），lark/既有 counts() 保持。每个测试比较自己前后增量；仅启动受控 fixture，不读取 config.yaml/.env。

- [ ] **21.1 增加浏览器意图测试**：`email_selection_sends_only_confirmed_recipient`（默认未选、选择导师、确认框/事件仅导师、取消零发送）；`email_new_confirmation_resends_while_lark_stays_blocked`（同版本原键不重放、新确认邮箱可发、飞书不变）；`query_preview_feedback_timeout_and_keyboard_focus`（延迟显示、10 秒反馈、正文焦点、无横向溢出）；保持原 POST 丢失/原键恢复测试并核对目标不变。fixture 日志只含虚构目标。
- [ ] **21.2 fixture/业务行为先失败再修复**：如果 fixture 未记录目标，先运行 test_operations_fixture.py 的新 `test_fixture_records_only_synthetic_selected_email_targets` 观察 RED，再只补测试替身记录，GREEN 后运行新 Playwright。若发现生产缺陷，新增正确原因 RED 后最小修复，不能先改代码再补验收。
- [ ] **21.3 完整回归**：根目录 `& $taskPython -m pytest -q`，必须全部通过且 coverage ≥90%。前端依次 `npm test -- --run --coverage`、`npm run typecheck`、`npx playwright test --config playwright.config.ts`、`npx playwright test --config playwright.operations.config.ts`，全部退出 0，四个现有业务模块逐文件四项 ≥90%。依次设置 `$env:VITE_API_MODE='readonly'` / `'operations'` 后各运行 `npm run build`，两次退出 0；清理仅本轮公开环境变量。记录所有警告/失败和修复复验。
- [ ] **21.4 实际运行与文档**：在真实本机配置下仅验证认证、邮箱选择展示、查询反馈和预览定位，不采集/通知除非另外授权。若需真实选择性推送，先展示版本和目标再获明确发送指令；零外部发送与未验收项如实记，不声称收件成功。README/local-run 更新单邮箱选择、独立确认、主动再次发送与 Gmail 垃圾邮件检查步骤，公共示例均用虚构地址。
- [ ] **21.5 完成审查与交付**：逐项映射 N01–N06、Task19–21；执行 requesting-code-review 与 verification-before-completion，按已选本会话执行方式做一次独立整体审查，再处理确认的问题并复验。真实收件若仍缺保留未验收；不要据旧 1.2.0 证据补勾本轮。通过门槛后由 finishing-a-development-branch 准备审查/合并材料，版本和 GitHub 交付方式在具体结果可审查后确定；不改原 v1.2.0 tag。

## 计划自审与当前 checkpoint（2026-10-11）

- N01→Task19 查询；N02→Task19 焦点/竞态/超时；N03→Task20 白名单与精确目标；N04→Task20/21 原键/主动新请求/飞书；N05→Task20 历史与快照；N06→各任务 TDD 及 Task21 全量/文档/验收。
- 五项 Review Focus 均有归属测试；消费者的字段名和签名与 Interfaces 对齐；无新依赖、逐收件人账本或任意邮箱入口。
- 当前只编写/检查计划与规范；尚未新增测试或生产实现、运行功能测试、发送通知、推送 Git 或升级版本。该记录不替代任何 RED/GREEN。
- 下一步：用户审查本计划，沿用本会话逐项执行方式；再核对隔离环境，先展示并运行 Task19 失败测试。
