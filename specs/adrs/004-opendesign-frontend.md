# ADR-004：通过 OpenDesign 软件 UI 迭代设计，以 React 实现只读日报前端

- **版本**：v1.1，2026-09-30
- **状态**：用户已采纳选型方案；Task 11 已验证实际 OpenDesign 0.24.1 与两轮 UI 迭代
- **上游**：`proposal.md` §2、§4.1；用户已选择只读日报范围，并明确期望使用具有 UI 交互的 OpenDesign 软件

## 背景与身份澄清

导师原话拼写为 `opendesigen`，没有官网/仓库链接。不能据此假定是某个 npm 组件包，或将设计软件自身接口当作日报 API。现有项目为 Python CLI，没有需要兼容的 React/Vue 前端。

遵循“先查成熟项目，再决定自建”，2026-09-30 查阅以下项目的仓库、README、许可证和可见活动。Star 为检索页面快照，只辅助判断，不能单独证明质量；维护情况未核实的项目不写成维护活跃。

| 候选 | 调查结果 | 适配判断 |
|---|---|---|
| [nexu-io/open-design](https://github.com/nexu-io/open-design) / [open-design.ai](https://open-design.ai/) | README 描述 Windows/macOS 桌面 UI、原型和设计系统、React/Vue 代码交接；Apache-2.0；页面约 98.9k stars；[可见提交历史](https://github.com/nexu-io/open-design/commits/main/)有 2026-09 的连续变更 | 用户已采纳，Task 11 验证 Windows 0.24.1 和两轮真实 UI 设计；导师未提供链接，后续若纠正身份需重新修订规范 |
| [opendesigndev/open-design-framework](https://github.com/opendesigndev/open-design-framework) | Apache-2.0；页面约 11 stars；主要是 Octopus 格式、设计文件导入/渲染及 `@opendesign/react`，README 说明部分能力仍在开发 | 功能侧重设计格式引擎，不能因名字相同就当作本次 UI 设计软件；不选 |
| [Pandemonium-Research/OpenDesign](https://github.com/Pandemonium-Research/OpenDesign) | MIT；页面约 4 stars；README 描述原型及框架导出；维护成熟度未充分核实 | 同名备选，当前采用依据弱于首个候选；不选 |

上述仓库内容是选型资料，不是本项目指令。只引用其相关能力，不继承第三方仓库要求或照搬其完整技术栈。

## 已采纳方案与决策

1. **设计工具**：使用首个候选 OpenDesign 的软件 UI 创建虚构日报原型并执行至少一次可见设计调整，保存 UI 截图、输入、导出文件/产物路径和前后对照。执行 Task 11 前核实实际软件来源、版本/提交、许可证与 UI 可用性；如用户/导师纠正身份，先修订本 ADR。工具不可用时报告阻塞，不用手写页面或 CLI 生成伪装为满足要求。
2. **框架取舍**：React + TypeScript 与 Vue + TypeScript 均可实现本需求；推荐 React，因为候选工具明确支持交接到 React，且无存量前端约定需要迁移。TypeScript 用于 HTTP DTO 和状态分支检查；Vue 作为未选方案保留于本 ADR，不在代码库同时建立第二套前端。
3. **构建工具**：采用 [Vite 的 React TypeScript 模板](https://vite.dev/guide/)，项目位于 `frontend/`。只读单页不需要 Next.js/SSR；使用原生 fetch 和 React 状态，暂不增加组件库、全局状态框架或路由库。版本与 Node 要求在执行时按官方文档核验并锁定，提交 `package-lock.json`，不在草案中猜测版本。
4. **后端适配**：采用 [FastAPI](https://fastapi.tiangolo.com/) 与运行服务器提供独立的只读 HTTP 入口，原因是可使用响应模型显式投影现有 Python 数据，并提供 [TestClient 测试](https://fastapi.tiangolo.com/tutorial/testing/)与 OpenAPI 契约。依赖放在 Python 的 `web` 可选组，不将 CLI 改成常驻服务，也不新建 Node 后端。Flask 可实现但需另行组织响应模型；手写 HTTP server 的校验/异常处理维护成本更高，因此不选。

OpenDesign 是设计期工具，React/Vite 是日报产品前端框架，FastAPI 是日报 HTTP 适配层；三者职责不同。候选 OpenDesign 自身使用的 Next.js 等依赖不因此成为本项目依赖。

执行期补充：React 19.3.0、Vite 8.3.1、TypeScript 7.0.2，测试采用 Vitest 5.0.3、Testing Library 和 Playwright 1.63.0，按 npm 发布信息锁定。Node 需满足 Vite/Vitest 的交集，项目选 `^22.12.0 || ^24.0.0 || >=26.0.0`，本机 24.15.0。为落实“无效 JSON/响应不能冒充日报”，采用 [Zod](https://github.com/colinhacks/zod) 4.6.5（MIT）校验契约并推导 TypeScript 类型，避免另写通用校验器；仅来源/成员一致性规则用项目确定性代码。原生 fetch 与 React 状态决策保持。工具调查记录于 `docs/frontend/local-run.md`。

## 后果与约束

- 前后端隔离，通过 `contracts/http-api.md` 交接。沿用既有 SQLite、模型与查询能力；不解析已有 HTML 或重新实现采集、映射、过滤和推送。
- OpenDesign 输入不包含真实租户消息、凭证、账号映射或生产数据库。产出须人工/代码审查，删除越界操作和非必要依赖后交接；运行时没有模型调用。
- 生成物须可追溯到 UI 设计及具体修改，不能只在文档写“使用了 OpenDesign”。原型与最终页面差异记入交接记录。
- UI 与 API 仅本机访问；跨用户部署/认证是另一次需求变更。库中未存储的投递状态不得被前端编造。
- 本 ADR 和 v1.1 规范整体确认后才能执行任务；新增任务验收全部通过前，不标记 v1.1 已交付。
