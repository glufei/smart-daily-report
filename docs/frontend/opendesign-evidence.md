# Task 11 OpenDesign UI 证据记录

## 已验证

- 2026-09-30，来源为 [nexu-io/open-design 官方 Windows 发行版](https://github.com/nexu-io/open-design/releases/tag/open-design-v0.24.1)，选择的软件方案来自已确认 ADR-004。
- 版本 `0.24.1`；安装后 `Open Design.exe` 的 ProductVersion 为 `0.24.1.0`；仓库许可证 Apache-2.0。
- 发行资产 `open-design-0.24.1-win-x64-setup.exe`，SHA256 `3a544dca7a5f078029d55f272e218278e52edac55efbfb292d56258113e8a441`，核对官方 API 的 digest 一致。
- 隔离安装位置 `.tools/OpenDesign/`；安装程序返回 0。
- 安装自动打开的窗口曾退出；用户明确允许重新启动并继续 UI 设计后，已成功进入真实 OpenDesign UI。
- UI 项目：`6c2b4e4b-cf40-4cf7-965c-00b613bca782`；会话：`262dde12-f0c7-49b5-ac56-7664fcddf835`。首轮执行完成，UI 显示耗时 7m54s。
- UI 操作截图：`prototypes/opendesign-home.png`、`opendesign-first-input.png`、`opendesign-initial-complete.png`、`opendesign-second-input.png`。
- 软件实际生成文件：`C:\Users\Administrator\AppData\Roaming\Open Design\namespaces\release-stable-win\data\projects\6c2b4e4b-cf40-4cf7-965c-00b613bca782\smart-daily-report.html`。复制保存为 `prototypes/initial.html`，未修改导出源文件。首版 SHA256：`6847cd802a6340b8e06f79c10ee47aef413b174e7b2b16690d08797608936639`。
- 首版两种视口 × 六种状态及键盘查询检查通过（14 项），对应 `prototypes/initial-*.png`；复现脚本 `prototypes/check-prototypes.cjs`。首次键盘检查因原生日期输入包含多个可编辑段而失败，修正测试的 Tab 遍历假设后通过。

## 第二版验收

- 第二轮同一会话 UI 显示已完成、51s；完成截图 `prototypes/opendesign-iteration-complete.png`，原文件复制为 `prototypes/iteration.html`，SHA256 `62f04d1687fdfa23aecad0b40062ecabb4f0d00ec4eb0760625c13418ce61991`。
- 可见修改：正文/记录 15→16px、日期标签 13→14px、日期输入/查询按钮 44→48px、按钮 15→16px。前后截图 `prototypes/initial-375-正常日报.png` 与 `prototypes/iteration-375-正常日报.png`（桌面 1440 同名截图亦可对比）。理由为手机可读性及点击面积。
- 两版 × 两视口 × 六状态 + 键盘查询共 28 项检查通过，`prototypes/checks.json`；包含所有成员三板块、零记录、来源失败。初版与第二版文件差异仅为以上六处 CSS。
- `design-brief.md` 记录真实提交的虚构输入，本身不是软件生成物。
- Task 11 的两版 UI 迭代与状态/视口证据已齐备。手机异常空白及额外 UI 修正被工具拒绝的情况公开记录于 `DESIGN.md`；产品修正该交接缺陷，不伪造第三版。

输入仅含虚构团队与记录；工作目录为 `.runtime/opendesign-work`，只放置设计输入。生成阶段曾尝试枚举父目录 Markdown，UI 显示失败。未向软件提交生产数据库或配置。原型中的演示状态控件仅用于设计验收，产品前端须移除并使用真实 API。
