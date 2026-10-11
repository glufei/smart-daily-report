# Task27 日报来源分组与时区显示 TDD 验收

状态：实现与完整自动化回归通过，已纳入 v1.5.0 发布候选 PR #8。Playwright 在 Windows 上的测试进程清理问题已修复；只读与操作模式均完整通过并自然退出。

## 行为与改动

- 日报开头标明“本日报由系统自动生成”，成员“今日总结”说明其数字由成功采集记录自动统计。
- 每位成员的结构统一为“今日总结 → GitHub｜代码提交 → 飞书｜任务与工作消息”。GitHub 下列“提交明细”；飞书下分“任务进展”和“工作消息”。Markdown、邮件 HTML 和 React 页面使用相同来源边界。
- 查询 API 的 `generated_at` 仍为 ISO 8601 带时区时间。操作模式的历史查询和预览均从 `team.timezone` 读取展示时区；只读模式支持 `--timezone`，默认 UTC。API 仅投影时间表示，不写回 SQLite；预览显示转换不改变确认版本哈希，缺失时区的损坏历史记录仍被拒绝。
- 更新了 proposal、design、HTTP API 契约、README 和本机启动指南。未修改历史日报，不执行真实通知发送。

## TDD checkpoints

1. **模板 RED**：新增 `test_report_groups_details_by_platform_and_labels_automated_summary`，先因缺少来源组标题及“系统自动统计”而失败。最小模板实现后该测试通过；将 GitHub 明细标题补入 Markdown/HTML 的同层级测试也通过。
2. **API RED**：新增团队时区投影测试，先得到 `10:00Z` 而非期望的 `18:00+08:00`；只读 CLI 时区参数测试先因不认识 `--timezone` 失败。实现纯读取的时区投影及 CLI 参数后通过，数据库时间点仍是 `10:00+00:00`。
3. **操作启动 RED**：新增配置模式 CLI 测试，先因 `create_app` 未接收 `team.timezone` 而失败；操作启动显式传入配置时区后通过。
4. **页面 RED**：新增来源分组、自动统计说明及时区偏移的 React 测试，先因页面缺少目标区块/显示格式而失败；页面实现后通过。
5. **完整回归**：旧模板标题断言随已确认结构调整；鉴权测试验证应用初始化不能读取业务服务属性，最终实现仅使用启动参数传入的展示时区。
6. **预览 RED/GREEN**：最后走查发现操作模式“预览日报”通过独立 `OperationService`，原先仅历史 GET 路由转换。扩展 `test_preview_does_not_attribute_current_config_to_old_history`，先观察预览返回 `00:00Z` 而应为 `08:00+08:00`；随后只转换 `ReportView`，原始 `DailyReport` 和存储字节保持不变。浏览器操作场景增加 `UTC+08:00` 断言。

## 首轮浏览器退出问题与修复

初次重跑只读和操作浏览器测试时，所有场景与安全 teardown 均输出通过，但 Playwright 随后卡在 Windows `webServer` 清理阶段，命令不能返回退出码。加入 `DEBUG=pw:webserver` 后确认停在 “Terminating the WebServer”；测试启动的 Vite 与 API 服务仍占用各自端口。根因是 Playwright 的 Windows WebServer 进程清理路径无法可靠回收这组 shell 包装启动的进程。

最小修复是由同一个全局测试设置用 Node `spawn` 直接启动 Python fixture 和 Vite 子进程，并在 global teardown 中先执行原有 SQLite/敏感日志/零副作用校验，再按逆序关闭这些直接子进程。操作与只读模式共用这一生命周期管理；测试端口、fixture 数据及业务断言不变。基线复现是在 teardown 消息后挂起；修复后的单个只读用例、14 项只读套件和 38 项操作套件均自然结束，退出码为 0。

## 验证结果

- Python：`.runtime\venv\Scripts\python.exe -m pytest -q` — **332 passed**，覆盖率高于 **95%**（门槛 90%）。有一项既有 Starlette/httpx TestClient 弃用提示。
- 前端：`npm test -- --run --coverage` — **145 passed**；行 **100%**、语句 **97.38%**、分支 **94.89%**、函数 **98.88%**，均超过 90% 门槛。
- `npm run typecheck`：通过。
- `npm run build`：通过，Vite 构建成功。
- `git diff --check`：通过；Git 仅提示少数文件下次写入时 LF/CRLF 转换。
- 只读 Playwright：移动和桌面共 **14 个用例全部通过**，改用允许的 4173 端口运行；SQLite 字节未变化、没有采集/通知调用，日志不含私密标记，进程以退出码 0 结束。
- 操作模式 Playwright：移动和桌面共 **38 个用例全部通过**，仅使用本地合成来源和测试 SMTP；没有真实邮件或飞书发送，日志未泄露私密标记，进程以退出码 0 结束。两套测试须串行运行，避免争用 Playwright 的共享产物目录。
- 时区补充验收：操作模式生成/预览场景在移动和桌面均通过新增的 `UTC+08:00` 断言。

版本标识复核还发现 Python 包与 FastAPI OpenAPI 元数据仍显示 v1.3.0；新增一致性意图测试先因 `__version__` 为 `1.3.0` 而失败，随后将 Python 包版本同步到项目 v1.4.0，并让 API 复用该唯一版本常量。没有生成或推送真实日报；浏览器操作模式只使用合成边界。
