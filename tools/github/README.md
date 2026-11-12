# github MCP

当前提供 46 个公开接口。

## 支持的能力

查询账户、仓库及文件，搜索仓库和代码，修改仓库可见性；创建、查询和修改 Issue、PR、标签、里程碑、指派和关联；管理普通评论、请求及移除评审人、提交评审和行内评论；查询 PR 文件、提交和差异，按当前提交及评审检查合并；创建、修改和删除发布版本；查询工作流、运行和日志，手动触发、请求取消及重跑工作流；查询通知并标为已读。

## 对象与操作语义

托管协作对象与共享 Git 仓库关联。PR 的文件和提交来自真实 Git 差异；已合并 PR 使用合并时保存的提交，后续分支移动不改写其展示依据。普通评论允许作者修改删除，历史事件保留修改前内容；删除标签或里程碑会清除关联。

工作流手动触发要求声明 workflow_dispatch 和可接受输入，提交时固定 head_sha。取消是请求状态，执行器后续回报完成结果；重跑另建运行记录，保留原提交和输入。执行器证据由 `local_github/environment.py` 写入，Agent 无法通过公开工具指定工作流成功。

发布记录与 Git 标签分开，删除发布版本保留标签。该模型覆盖仓库日常协作，不实现组织计费、完整团队治理和 CI 容器执行器。

## 接口目录

- `add_comment`：为Issue或PR添加本地评论。kind为issue/pull_request；不向外部平台发送。
- `add_pull_request_review_comment`：在PR差异的RIGHT侧代码行添加本地评审评论，绑定预期head SHA；行号从1开始。
- `cancel_workflow_run`：请求取消正在排队或运行的工作流；最终结果由执行器回报。
- `create_pull_request`：为本地head/base分支创建模拟PR，head须有超出base的提交，重复未关闭PR报错。
- `create_release`：创建本地Release，并在真实本地Git中创建缺失的轻量tag；不会推送；已有tag不可移动。
- `delete_comment`：删除当前用户发表的普通讨论评论。
- `delete_label`：删除仓库标签，同时移除 Issue 和 PR 上的该标签。
- `delete_milestone`：删除里程碑并清除 Issue 和 PR 的关联。
- `delete_release`：删除发布记录，保留对应 Git 标签。
- `dispatch_workflow`：向支持手动触发的工作流提交运行请求，固定当前引用对应的提交。
- `get_file_contents`：浏览已提交的文件或目录；默认读取默认分支，忽略工作区未提交修改。
- `get_me`：读取场景当前用户的本地GitHub资料。
- `get_release`：按tag读取本地模拟Release详情。
- `get_repository`：读取仓库的平台元数据、可见性、默认分支和合并要求。
- `get_workflow_run`：读取预置Actions运行状态、结论、提交SHA及任务信息，不执行CI。
- `get_workflow_run_logs`：按行分页读取预置Actions日志；offset从0开始，limit为1..1000。
- `issue_read`：读取Issue及评论。
- `issue_write`：创建或更新Issue；省略number新建且须title。state为open/closed；None字段不修改，空列表清空。标签须先创建；milestone=0清除里程碑。
- `label_write`：创建或更新标签，支持重命名并同步Issue/PR引用；颜色为不带#的六位十六进制。
- `list_comments`：分页读取 Issue 或 PR 的普通讨论评论。
- `list_issues`：查询本地模拟Issue；state为open/closed/all，query为标题正文子串，offset分页。
- `list_labels`：列出仓库本地标签目录。
- `list_milestones`：列出里程碑并统计其未关闭及已关闭Issue；state为open/closed/all。
- `list_notifications`：列出当前用户的本地预置通知，可筛选仓库及未读状态。
- `list_pull_request_commits`：列出 PR 当前分支相对基线包含的提交。
- `list_pull_request_files`：基于 PR 当前基线和提交列出变更路径、状态及增删行数。
- `list_pull_requests`：查询模拟PR，state为open/closed/merged/all，可按标题正文子串、作者及待评审人筛选。
- `list_releases`：列出本地模拟Release，包括草稿和预发布。
- `list_workflow_runs`：筛选预置Actions运行记录，status为queued/in_progress/completed；不执行CI。
- `list_workflows`：列出场景预置的GitHub Actions工作流，不执行任何CI。
- `mark_notification_read`：将属于当前用户的本地通知标记为已读。
- `merge_pull_request`：真实合并PR，须当前位于干净base分支、head SHA与预期一致、非草稿、满足当前提交评审要求。冲突则恢复操作前仓库和协作数据。
- `milestone_write`：创建或更新里程碑；省略number新建且须title；due_on需时区，空字符串清除日期。
- `pull_request_read`：读取PR、当前分支SHA、三点diff、评论和绑定提交的评审。
- `remove_requested_reviewers`：移除 PR 的待评审人。
- `request_reviewers`：为打开的PR追加评审者；不能请求作者本人评审；只记录本地请求，不发送通知。
- `rerun_workflow`：重新运行已完成的工作流，保持原提交及输入，另建运行记录。
- `search_code`：在指定提交版本的UTF-8代码中按字面子串搜索，返回文件、行号和文本；不是GitHub高级搜索语法。
- `search_repositories`：按ID、名称、owner及描述的大小写不敏感子串查询本地仓库。
- `set_issue_assignees`：替换 Issue 的指派人，空列表清除指派。
- `set_item_labels`：替换 Issue 或 PR 上的标签，空列表清空。
- `submit_review`：提交模拟评审，event为APPROVE/REQUEST_CHANGES/COMMENT，绑定当前head SHA。不能批准或请求修改自己的PR。
- `update_comment`：修改当前用户发表的普通讨论评论。
- `update_pull_request`：修改PR标题正文、草稿状态或open/closed；已合并PR不可修改；linked_issues关联的Issue在合入默认分支时关闭。
- `update_release`：修改发布版本说明以及草稿、预发布状态。
- `update_repository_visibility`：设置仓库可见性；public 公开、private 私有。
