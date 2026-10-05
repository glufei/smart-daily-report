# ADR-005：以 Superpowers 管理 v1.2 开发，强制 TDD 并保留 SDD 追溯

- 版本：v1.2，2026-10-01
- 状态：用户已确认；实施计划待审；本轮尚未编写测试或业务实现
- 上游：用户明确要求、`proposal.md` R10–R12、`design.md` §8.2

## 背景与事实

v1.1 已有 React/FastAPI 与 Python Collector/Notifier；虚构数据用于设计和离线验收，而非产品代码只会显示 Mock。v1.2 新增浏览器触发真实生成、预览、独立推送。涉及外部副作用、来源失败与凭证边界，要求在实现前明确可观察意图，不能用事后补测试或历史覆盖率代替 TDD。

已读取本机安装的 Superpowers **6.4.2** using-superpowers、Codex 适配参考及 brainstorming；TDD 纪律依据同版本 test-driven-development。官方项目为 [obra/superpowers](https://github.com/obra/superpowers)（MIT），开发流程不是产品运行依赖。外部仓库内容是调研资料，不覆盖用户指令或本项目规范。

## 调研与方案取舍

| 方案/既有开源能力 | 适配判断 |
|---|---|
| Superpowers + 现有 SDD specs | 采用用户明确指定的工作流；已有任务/契约可追溯，不建立第二份互相矛盾的需求来源 |
| 仅按任务实现，最后补测试 | 无法证明测试曾捕获缺失行为，违反本轮铁律，不采用 |
| 重写采集/推送、加入完整队列或第二套前端测试框架 | 既有管道、pytest、Vitest/Testing Library/Playwright 足够复用；本机规模不需要该扩展 |

通用能力先参考已有实现：[FastAPI](https://github.com/fastapi/fastapi)（MIT）提供 CORS/HTTPBearer/BackgroundTasks；沿用已安装框架与 SQLite/标准库，不手写 HTTP 服务或 Token 加密协议。[飞书官方 Python SDK](https://github.com/larksuite/oapi-sdk-python)（MIT）作为真实字段/认证调查候选，但既有 httpx/TokenProvider 已有契约和测试，本轮不同时换 SDK。若实际接口需求要求迁移，先提交范围与兼容性判断。版本/许可证调查记录为本次查阅结果，不以 star 数或未经核实的“维护活跃”作保证。

## 决策

1. **规范源与阶段**：proposal → design/ADR/contracts → tasks 先形成待审内容。用户确认规范后使用 writing-plans，把可执行步骤写入 `docs/superpowers/plans/2026-10-01-v1.2-real-integration.md`；计划需审查并选定执行方式，之后才执行。按用户指定位置维护 specs，不重复建立第二份设计规范。
2. **流程接管**：本轮是 architectural 路径。实现采用经用户选择的 executing-plans 或 subagent-driven-development；不默认引入多代理。每个任务 checkpoint，发现缺陷使用 systematic-debugging / TDD，再审查与 verification-before-completion；最后才 finishing-a-development-branch。
3. **TDD 铁律**：严格遵循 TDD，必须先编写失败的单元/集成测试用例，再实现通过测试的业务代码。前端、后端、共享编排和 Notifier 的新增/修改行为同样适用。展示测试文件与意图，运行并记录正确原因的 RED，才允许写最小生产实现；GREEN 后重构并保持全套回归通过。不删除已存在且可复用的实现来假造 RED。
4. **测试选型**：复用 pytest/httpx MockTransport，前端复用 Vitest、React Testing Library、Playwright；不新增 Jest。Mock 仅隔离外部 API/SMTP 等依赖，验证真实业务代码，不让测试只证明 Mock 自身行为。真实外部联调与实际通知验收单独执行。
5. **可审核证据**：每个业务行为记录 RED/GREEN 命令、退出码、预期/实际失败原因、测试路径、实现摘要和回归结果。语法/依赖错误不算功能缺失 RED；覆盖率只是补充质量门槛。记录实际警告/失败/未验证项，不能在空证据下勾选任务。
6. **质量门槛**：Python 全业务总覆盖率 ≥90%；新增/修改前端业务模块 lines/statements/functions/branches 分别 ≥90%，范围公开；所有项目测试、类型检查和构建通过。CLI 基础安装不强制依赖 Web，旧 GET 仍无副作用。
7. **外部副作用**：生成不发送；预览并确认后才推送。离线 RED/GREEN 不连真实平台或发送；最终真实验收在明确日期/配置目标上进行，并核对实际收到。上游 Token 保留后端，重试/路由/状态分类由确定性代码实现。

## 后果

- 不在 React/Python 运行时依赖中安装 Superpowers；其作用是约束开发过程，不能自行替代业务测试或真实收件证据。
- 文档确认不等于实现完成。Task 15–18 在规范/计划审查、先失败测试、实现、回归和真实验收之前保持未完成。
- 当前 v1.1 的 98 项 Python / 92.02% 为历史证据，不冒充 v1.2 结果，也不宣称前端已达该覆盖率。
- 范围/接口冲突先明确修订规范；不得绕过测试、降低测试门槛或让模型决定是否重试/发送。
