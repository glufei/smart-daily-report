# 飞书任务清单只读权限：逐步开通与发布

2026-10-01真实请求返回HTTP400、业务码99991672，明确要求task:tasklist:read或task:tasklist:write。日报只读取，所以本轮只申请task:tasklist:read。App ID、Token和任务内容不写入本指南。

## 1. 进入正确应用

打开 https://open.feishu.cn/app ，登录应用所属租户，选择你已经用于项目的企业自建应用。在应用凭证页面自行核对App ID与本机.env中的DAILY_REPORT_LARK_APP_ID一致；不要另建应用，也不要把App Secret发到聊天。

## 2. 搜索并开通权限

1. 左侧找到“权限管理”（可能位于“开发配置”分组）。
2. 点击“开通权限”或对应的添加/申请权限入口。若当前列表只显示已开通权限，进入新增权限列表后再搜索。
3. 搜索权限标识task:tasklist:read；名称可能按界面显示为查看/读取任务清单，以权限标识为准。
4. 若区分访问身份，选择适用于应用身份tenant_access_token的权限。本项目没有使用个人OAuth Token。
5. 勾选该只读权限，按页面流程确认开通/申请。无需为了这一GET接口选择task:tasklist:write。

如果搜索不到，确认不是在其他应用、个人权限设置、群机器人设置或仅已开通权限列表中搜索。可把“权限管理”页面截图提供给我继续定位，不需要提供任何密钥。

## 3. 创建并发布版本

1. 左侧进入“版本管理与发布”（可能位于“应用发布”分组）。
2. 点击“创建版本”或对应新版本入口。
3. 版本号按此飞书应用当前版本递增，例如已有1.0.0则可用1.0.1；不必与本项目v1.2一致。
4. 更新说明可填写：为智能日报生成器增加task:tasklist:read任务清单只读权限，用于读取已授权清单中的任务，不修改任务。
5. 核对本版本包含刚申请的权限；保留原有能力，应用可用范围须包含本次使用成员。
6. 按页面点击发布或提交审核/申请发布。如租户要求管理员审批，等待并完成审批流程。
7. 确认版本已发布；仅保存草稿、审核中或待发布不能作为权限生效证据。

按钮名称随租户控制台版本可能变化，以页面流程为准。拥有应用管理权限不一定意味着可以免去租户审批。

## 4. 完成后核对真实读取

回复“任务清单只读权限已开通并发布”。本次权限变更无需替换.env的App ID/Secret。我会重新获取租户Token并检查接口。

如果仍失败，继续按新错误码核对：权限审批是否生效、ID是否为tasklist_guid、清单对该应用是否可访问。不把取得Token等同于读取授权，也不把零记录等同于权限失败。

已选择日报验收日期2026-09-30；验收日期是准备生成/核对哪一天的数据。权限和样本满足后先生成预览，具体版本/目标确认后才发送。


## 5. 权限已生效后：区分任务链接和清单链接

2026-10-01重新获取租户Token后，列取清单返回HTTP200/code0，但当前应用可见清单为0。配置的清单任务接口返回HTTP404/code1470404。用户提供的链接是 `/client/todo/detail?guid=...` 单条任务链接，且其GUID与当前 `lark_project_ids` 配置值相同；把任务GUID用于清单接口不能找到清单。单独GET该任务详情返回HTTP403/code1470403，未取得所属清单信息。这里不把403或404伪装成成功空任务，也不据此认定用户的任务被删除。

按以下步骤取得清单链接：

1. 打开飞书客户端，进入“任务”；若主导航没有，在“更多”等应用入口查找任务。
2. 如果正在某条任务的详情弹窗中，先关闭弹窗或返回任务主页面。不要再次点击这条任务自己的“分享”。
3. 在任务页面查找“任务清单”分组，点击具体清单名称。也可在任务详情中找到所属清单名称，点击进入。按钮位置和名称随客户端版本变化，以当前界面为准。
4. “我负责的”“我关注的”等聚合视图不能直接当成目标任务清单。若只有这些视图、任务未加入任何清单，先告知这一情况；不要将任务GUID继续填进配置，也不要为验收虚构历史任务。
5. 在显示清单名称和多条任务的清单页面，点击清单的“分享”或清单标题旁菜单中的分享入口，再复制清单链接。不要打开某条任务后分享该任务。
6. 将复制的清单链接提供给协作者核对；链接不应包含Token、App Secret。当前 `/todo/detail` 链接仍是任务详情链接。清单分享链接常见 `/todo/task_list?guid=...`，若当前客户端给出其他格式，保留完整链接供核对，不仅凭字符串长度判断ID类型。

取得正确清单GUID后，只替换工作区config.yaml中的清单列表，保留其他配置：

```yaml
team:
  # 以下为现有team配置中的相关字段，不能拿这段覆盖整个文件。
  lark_project_ids:
    - 清单分享链接中核对出的tasklist_guid
  lark_task_search_path: /task/v2/tasklists/{tasklist_guid}/tasks
```

上例是占位示意，不能直接运行。任务ID与清单ID都可能是36位GUID，外形相同不代表可以互换。类型依据见 [官方任务详情请求模型](https://raw.githubusercontent.com/larksuite/oapi-sdk-python/v2_main/lark_oapi/api/task/v2/model/get_task_request.py)和 [任务所属清单模型](https://raw.githubusercontent.com/larksuite/oapi-sdk-python/v2_main/lark_oapi/api/task/v2/model/task_in_tasklist_info.py)。

正确GUID仍需用本项目应用身份读取成功。开通API scope与具体清单的数据访问是两个检查：用户自己能打开清单、调试台个人身份成功，都不能替代应用身份成功。先确认清单所有者/协作者，再按 [飞书任务FAQ](https://open.feishu.cn/document/task-v2/faq) 和 [添加清单成员接口](https://open.feishu.cn/document/task-v2/tasklist/add_members) 核对应用加入清单的最小可阅读角色；不自动改用个人OAuth、不盲目申请写权限。本次仅诊断，尚未修改清单成员或外部访问权限。


## 6. 正确清单仍403：由有权限的人授权应用读取

用户随后提供了 `/client/todo/task_list?guid=...` 的正确清单链接。本机配置已只替换该GUID并通过load_config；用现有租户Token读取正确清单详情和清单任务列表，均HTTP403/code1470403。未取得详情，不能根据空响应推断协作成员列表；读取scope成功也不证明具体资源访问已授权。运行中的后端仍持有启动时配置，待资源授权后重启再采集，旧9/30预览保留为原失败证据。

先在飞书清单的“分享/协作者”界面核对你是否能管理协作成员。如果界面支持搜索当前自建应用/机器人，将其加入并选择“可阅读”；应用名称须对应.env中的同一App ID，不能用推送群的自定义Webhook机器人替代。若客户端只能选择人员，使用官方API调试台由清单所有者/有管理权限的用户操作，不猜测不存在的客户端按钮。

API调试台步骤（这是一次由用户执行的清单授权，不是日报运行时新增OAuth功能）：

1. 打开 [添加清单成员](https://open.feishu.cn/document/task-v2/tasklist/add_members)，选择本项目使用的企业自建应用。
2. 在该接口“API调试台”中选择有权限管理该清单的用户身份user_access_token。页面获取访问凭证时，由清单所有者本人登录/完成授权。不要把用户Token、App Secret复制到聊天、项目.env或前端。
3. 路径参数tasklist_guid填写刚取得的清单GUID；user_id_type选择open_id。
4. 请求体按下面示意填写。id替换为.env中DAILY_REPORT_LARK_APP_ID的实际值（cli_开头），不是App Secret、任务GUID、成员open_id或Webhook。type=app，role=viewer（可阅读）。
5. 核对清单和应用，再由用户点击调试/发送请求。这会把该应用加入该清单，允许读取清单中的任务。请求需要当前调用者的清单管理权限；应用尚不能读时，不使用该应用的tenant_access_token尝试自行授权。
6. 若调试台明确提示缺少scope，按当前接口“权限要求”申请这次管理操作必需的权限并发布/审批；不要仅为了运行时GET盲目加写权限。若提示资源管理权限不足，让清单所有者操作。
7. 成功响应须HTTP200且code=0。之后仍由协作者重新用项目tenant_access_token读取清单任务列表确认，管理请求成功不能替代读取证据。

```json
{
  "members": [
    {
      "id": "cli_替换为当前自建应用AppID",
      "type": "app",
      "role": "viewer"
    }
  ]
}
```

接口方法、路径、TENANT/USER及成员字段依据 [官方添加成员请求SDK](https://raw.githubusercontent.com/larksuite/oapi-sdk-python/v2_main/lark_oapi/api/task/v2/model/add_members_tasklist_request.py)、[成员模型](https://raw.githubusercontent.com/larksuite/oapi-sdk-python/v2_main/lark_oapi/api/task/v2/model/member.py)；可阅读/可编辑应用协作者能力见 [官方Go接口模型](https://raw.githubusercontent.com/larksuite/oapi-sdk-go/v3_main/service/task/v2/model.go)。不要授予editor来代替本轮只读viewer，不扩大到全部租户任务。


## 7. 本轮开通和复验结果

实际客户端分享面板仅提供“搜索用户和群组”，未假定可搜索应用。用户进入添加清单成员调试台，选择开发者user_access_token；权限配置页列出未开通的“查看、创建、更新、删除任务清单”，且明确说明该开发者用户身份调试无需企业管理员审核。勾选该行、点击批量开通并按页面确认后，切回API调试台，保留app/viewer请求，开始调试。用户提供HTTP200/code0成功结果。

用户身份管理权限用于加入协作成员；项目运行时继续用tenant_access_token和应用viewer角色读取，不将个人Token写入.env。独立复验详情和任务GET均200/code0，应用role=viewer；未完成任务0不能当采集失败。用户将已达到测试目的的任务实际标记完成后，completed列表1条，完成日期2026-10-01、负责人匹配当前配置；生成/SQLite/React核对已通过，尚未推送。截图若含Authorization须遮住，不将完整cURL/访问凭证存进仓库或正常日志。
