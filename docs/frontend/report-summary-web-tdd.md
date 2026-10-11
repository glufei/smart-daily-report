# Task26：网页今日总结与 GitHub 仓库范围 TDD 记录

- 日期：2026-10-11（Asia/Shanghai）
- 发布状态：Task26 已纳入 v1.5.0 发布候选 PR #8；v1.4.0 的历史标签和内容保持不变。
- 目的：在 React 历史日报/预览页解释逐成员记录数量和来源状态，并将项目自身仓库纳入实际采集配置。

## 问题定位

用户展示的 2026-10-11 日报在三类来源中均显示“今日无记录”，页面也没有“今日总结”。检查后确认：实际运行的配置仅列出 `glufei/Lab-Attendance-System`，没有列出当日产生提交的 `glufei/smart-daily-report`；同时 React 页面此前只渲染三类明细，没有实现服务端 Markdown/HTML 已有的“今日总结”展示。

历史日报是生成时保存的快照。添加仓库不会回填或重算旧日报；必须重启已加载配置的后端并重新采集生成。来源状态为成功但数据为空的报告只能表示采集响应成功且当前数据集中没有记录，不能证明其他未配置仓库也没有提交。

## TDD RED / GREEN

先在 `frontend/src/App.test.tsx` 添加意图测试，覆盖：

- 有记录成员的三类数量，以及“今日总结”出现在明细标题之前；
- 成功来源的零记录显示 `0 条`；
- 失败来源显示 `获取失败，数量未知`，不得降级显示为零。

RED 命令：

```powershell
cd frontend
npm test -- --run src/App.test.tsx -t "deterministic summary|failed source counts"
```

RED 结果：新测试按预期失败，原因是页面不存在“今日总结”区域。随后实现最小 React 渲染与摘要样式。状态从预览来源结果优先读取，缺省时使用日报的来源状态；不发新请求、不改响应 DTO。

## 验证结果

- 聚焦摘要测试：2 项通过。
- 前端完整测试：4 个测试文件、143 项通过。
- `npm run typecheck`：通过。
- `npm run build`：通过。
- `git diff --check`：通过；仅出现 Git 关于 LF/CRLF 的提示。
- 本机配置：保留 `glufei/Lab-Attendance-System`，并加入 `glufei/smart-daily-report`。读取和核对只输出仓库名，没有读取或展示凭证。

## 真实数据验收

初次运行时，旧 Token 能读取 `glufei/Lab-Attendance-System`，但对私有仓库 `glufei/smart-daily-report` 返回 HTTP 404；匿名请求也为404。此时页面正确显示“获取失败，数量未知”，未将授权失败误报为零。

用户随后配置了细粒度 Token：Resource owner 为 `glufei`，仅选择 `smart-daily-report` 与 `Lab-Attendance-System`，仓库权限为 `Contents: Read-only`，Metadata 保持 GitHub 必需只读权限。Token 值没有进入聊天或项目文档。

用该本机配置对两个仓库进行验证均返回 HTTP 200。使用 `Asia/Shanghai` 日期窗口重新采集 2026-10-11：`glufei/smart-daily-report` 返回并保存 17 条提交，`glufei/Lab-Attendance-System` 当日 0 条；飞书任务和群消息均读取成功，各 0 条。CLI 以 `--dry-run` 生成并写入真实 SQLite 日报，未触发 SMTP 或飞书推送。

重启真实 FastAPI 后，日报查询 API 返回 GitHub/任务/消息三个来源均 `success`，记录数量为 17/0/0。对实际运行的 React 页面进行浏览器验收，页面显示“今日总结：代码提交 17 条、已完成任务 0 条、协作沟通 0 条”，代码提交板块有 17 条明细；浏览器未报告页面异常。该日期报告已保存在本机数据库，可在 `http://127.0.0.1:5173` 选择 `2026-10-11` 后点击“查看日报”。

本轮没有推送邮件或飞书。Task26 真实数据及页面验收已通过，代码和验收记录已纳入 v1.5.0 发布候选 PR #8。GitHub fine-grained Token 权限依据见[官方提交列表 API 文档](https://docs.github.com/en/rest/commits/commits)。
