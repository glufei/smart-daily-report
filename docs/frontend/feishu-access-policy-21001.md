# 飞书访问策略拒绝（21001）排查

错误 `21001` 出现在项目请求飞书 `tenant_access_token` 时，任务或消息接口尚未开始调用。项目会保留安全错误码，并把响应中的 `x-tt-logid` 请求追踪 ID 写入后端 `collection_finished` 日志；该 ID 不包含应用密钥或访问令牌。操作页面提示管理员用此 ID 排查。

请按以下顺序处理：

1. 查看启动后端的终端日志，找到对应来源的 `collection_finished` 记录，复制 `diagnostic_id`。
2. 请飞书租户管理员确认该自建应用当前可用、已获该租户授权且没有被租户策略停用或限制。
3. 将错误码 `21001` 和 `diagnostic_id` 提交给飞书开放平台支持或租户管理员，查询该次请求命中的访问控制策略。
4. 策略调整后重启日报后端并重新采集。不要把 `app_secret`、`tenant_access_token` 或完整认证请求发送到聊天、工单或公开仓库。

该错误不是任务清单权限错误：若令牌成功签发但清单读取权限不足，错误会出现在之后的任务 API 请求中。不要通过自动重试、替换成个人令牌或改写请求来绕过飞书拒绝。

参考：[飞书自建应用获取 tenant_access_token](https://open.feishu.cn/document/server-docs/authentication-management/access-token/tenant_access_token_internal)。该接口以应用身份签发租户访问凭证；项目在此阶段收到平台拒绝时，代码无法代替租户管理员更改策略。
