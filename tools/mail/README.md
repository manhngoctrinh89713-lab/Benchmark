# 邮件工具

邮件工作台提供 54 个 MCP 接口。状态保存在运行环境的 `services/mail/state.json`，附件与文件工具共用 `workspace`。邮件内容、发送记录和投递证据分别保存，便于核对实际操作及其后果。

## 功能范围

| 能力 | 接口 |
| --- | --- |
| 查询与阅读 | `list_accounts`、`get_account`、`list_mailboxes`、`search_emails`、`read_email` |
| 会话 | `list_threads`、`read_thread`、`update_threads` |
| 编写、发送及投递状态 | `send_email`、`reply_email`、`forward_email`、`get_send_status` |
| 草稿 | `create_draft`、`list_drafts`、`get_draft`、`update_draft`、`delete_draft`、`send_draft` |
| 附件及邮件导出 | `list_attachments`、`download_attachment`、`export_email`、`update_draft_attachments` |
| 整理与复制 | `update_emails`、`copy_emails` |
| 文件夹与分类 | `create_mailbox`、`update_mailbox`、`delete_mailbox`、`list_categories`、`write_category`、`delete_category` |
| 删除与恢复 | `delete_emails`、`restore_emails`、`empty_mailbox` |
| 通讯录与群组 | `search_contacts`、`get_contact`、`write_contact`、`delete_contact`、`list_groups`、`get_group`、`write_contact_group`、`delete_contact_group`、`resolve_recipients` |
| 邮箱委托与发送身份 | `list_delegates`、`set_delegate`、`remove_delegate`；发送接口支持主地址、别名及两种代理发送方式 |
| 收件规则与自动回复 | `list_rules`、`write_rule`、`delete_rule`、`get_auto_reply`、`set_auto_reply` |
| 定时发送 | `schedule_email`、`list_scheduled_emails`、`update_scheduled_email`、`cancel_scheduled_email` |

Agent 调用时加 `mail__` 前缀。完整参数定义见各接口目录的 `schema.json`；工具说明由实际注册信息生成。

## 账户与权限

`current_actor` 表示实际操作者。每个账户是独立邮箱，可以是个人邮箱或共享邮箱；账户主地址和别名在环境中唯一。

| 权限 | 作用 |
| --- | --- |
| `read` | 查询邮件、草稿、规则和邮箱内容 |
| `write` | 修改邮箱内容、草稿、文件夹、分类、规则和定时任务 |
| `send_as` | 以所选邮箱身份发送，显示 From |
| `send_on_behalf` | 代表所选邮箱发送，From 为所选身份，Sender 为实际操作者地址 |
| `manage` | 管理本邮箱的委托，仅所有者具有 |

四种普通权限独立授予；`write` 不隐含发送权限，`send_as` 不隐含阅读权限。所有者拥有全部权限，可向已登记操作者授予或撤销普通权限。组织目录与组织群组由环境配置，Agent 只能按可见范围查询。个人联系人及个人联系人组归各自操作者所有。

## 查询与对象

阅读邮件不标为已读，查询也不推进时间或运行规则。`search_emails` 返回摘要，`read_email` 返回正文。普通筛选参数同时成立；额外 `filters` 内可选全部或任一条件成立。查询使用有限的结构化条件，按时间、主题、正文与附件总字节数或发件人排序，分页上限为 100。

邮件资源 `id` 与邮件头 `message_id` 分开：移动保留资源 ID，复制产生新资源 ID，并保留原 Message-ID 和会话。会话在账户内组织邮件，按引用关系建立；修改会话作用于调用时的成员快照，返回逐封结果。

草稿、联系人、群组、文件夹、分类、规则、自动回复和定时任务包含版本；相应修改接口可传 `expected_version`。版本不符时该次修改失败。邮件整理也更新邮件版本。

## 编写、附件与地址解析

草稿可暂缺收件人、主题和正文；发送或排队时必须有收件人。回复使用选定邮件的 Reply-To，缺省时使用 From；回复已发送副本时使用原 To。回复全部还考虑原 To/Cc，排除自身并去重，密送名单不参与回复。转发可内联原文，也可附上标准 `.eml`；可以选择是否保留原附件。

发送和草稿接口接收三种收件人表示：明确邮箱地址、`contact:<id>`、`group:<id>`。不按显示姓名猜测地址。多地址联系人使用其默认地址；未指定默认地址的旧联系人须选择明确地址。个人联系人组在编写时展开为地址，组织邮件群组保留群组地址，到实际提交时展开。群组成员可以单独限制可见范围。

附件添加时读取工作区文件并保存字节快照。此后源文件被改写、移动或删除，已编写邮件中的附件不随之改变。单附件上限 25 MiB，每封最多 20 个、合计 50 MiB。替换附件通过同次移除旧 ID、添加新文件完成，新附件获得新 ID。下载及邮件导出不覆盖已有工作区文件。

## 批量操作与删除

邮件批量操作最多 500 个唯一 ID，逐项执行并返回成功或错误；单项失败保留其他成功项，成功操作均写入事件记录。未知账户、目标文件夹或无效公共参数在执行前报错。

归档即移动至 Archive。默认删除将邮件移至 Trash，并保留原位置；恢复返回原文件夹，原位置不存在时进入 INBOX，也可指定其他目标位置。永久删除须传 `permanent=true`。清空文件夹仅处理当时选中的邮件，不删除子文件夹；清空 Trash 须显式永久删除。

删除自定义文件夹同时删除其子文件夹，默认把子树中的邮件移到 Trash，恢复时进入 INBOX；显式永久删除时才移除邮件内容。系统文件夹不可删除、重命名或移动。分类删除只移除分类及相应标记，保留邮件。

## 提交、投递与定时发送

提交发送会建立 Sent 副本、提交记录和发送快照。同一环境中存在的目标邮箱会收到独立收件副本，并生成本地投递证据。收件副本及其导出文件不含密送名单。其他地址的投递结果初始为 `unknown`；主机提供后续证据后才改为 `delivered` 或 `bounced`。

提交状态为 `accepted`，全体收件人已有送达证据时为 `delivered`，全体退信为 `bounced`，部分退信为 `partial`。退信同时生成普通入站通知邮件。`get_send_status` 按群组成员可见范围返回结果；隐藏成员仅以群组地址呈现。事件中保存完整的实际信封地址，供评测端核对。

定时发送消费原草稿并保存冻结内容：正文、附件、明确地址、已解析的联系人和个人组成员均固定。组织群组在到期提交时展开。到期使用原排队操作者的当前发送权限与有效身份；权限已撤销、身份已移除或群组展开无效时，任务记为 `failed`，不产生发送。修改 pending 任务须由原排队操作者完成；有邮箱 write 权限的操作者可取消。任务提交、失败或取消后保留记录。

## 收件自动化

新入站邮件触发收件规则，包含本地发送产生的入站邮件和主机接收的邮件。规则按 priority 升序、同优先级按 ID 执行。conditions 全部成立且 exceptions 无一成立时匹配；空 conditions 匹配所有邮件。支持移动、已读、星标、添加分类、移入 Trash 和转发，动作按列出顺序执行。`stop_processing` 停止后续规则，规则执行失败也遵守该设置。单条规则的动作整体提交或回滚，失败保留原因记录。

规则按其保存操作者的当前授权执行；被删掉的目标文件夹或分类会使规则失败，不自动改投其他位置。规则转发和自动回复产生的邮件仍可被接收和整理，但不会继续触发自动发送。

自动回复在收件规则完成后执行，排除 Trash/Junk、自身及自动邮件。内部按邮箱主地址同域判断，外部可选不回复、只回复邮箱所有者的联系人或回复所有人。时间段左闭右开；每份有效配置对每个地址最多回复一次，修改设置后重置历史。自动回复使用保存操作者当前的 send_as 权限。

## 环境配置与评测端事件

旧环境的 `now/accounts/contacts/messages` 结构可直接载入，首次打开时补齐所有者、系统文件夹、版本和会话等字段。原消息 ID 保持不变。新配置可加入：

| 位置 | 主要字段 |
| --- | --- |
| 顶层 | `now`：带时区 ISO8601；`current_actor`：操作者 ID；`actors`：含 `id/email_address` 的操作者列表 |
| `accounts[]` | `account_name/email_address/mailboxes`；可选 `owner_id/aliases/delegates`，委托项含 `actor_id/permissions` |
| `contacts[]` | `id/name/emails`；可选 `default_email/organization/remark`；个人联系人用 `scope=personal` 和 `owner_id`，组织条目用 `scope=organization` |
| `groups[]` | `id/name/kind/members`；个人组 `kind=personal` 并指定 `owner_id`，组织组 `kind=organization` 并指定 `email_address` |
| 目录可见范围 | 组织联系人及群组可设 `visible_to`；群组另可设 `members_visible_to`。省略或 null 表示全体可见，空列表表示无人可见 |
| `messages[]` | 独立邮件记录，含 `id/message_id/account_name/mailbox/from/to/subject/body/timestamp`；可选 `cc/bcc/reply_to/in_reply_to/references/attachments` |
| `attachments[]` | `id/name/content_type/size/sha256/content_base64`，字节写入状态，工作区文件仅作编写时的来源 |

账户主地址、别名和组织群组地址不得冲突。群组成员为明确邮箱地址，不嵌套群组。文件夹配置可沿用 `mailboxes` 路径列表，载入时建立有稳定 ID 的层级目录。第一次载入时，未指定 owner_id 的账户和个人联系人归 current_actor 所有；需要多个操作者时应明确填写所有者。

主机入口在 `local_mail.environment`，包含 `receive_email`、`advance_time` 和 `record_delivery`。这些入口不注册为 MCP 工具，时间由评测端统一控制。也可从仓库根目录用 PowerShell 调用：

```powershell
$env:PYTHONPATH = (Resolve-Path 'tools/mail/公用代码').Path
.venv/Scripts/python.exe -m local_mail.environment --run-root <运行环境路径> advance-time --to <带时区时间>
.venv/Scripts/python.exe -m local_mail.environment --run-root <运行环境路径> receive --account <账户名> --message-file <入站邮件JSON路径>
.venv/Scripts/python.exe -m local_mail.environment --run-root <运行环境路径> delivery --submission-id <提交ID> --address <收件地址> --status delivered
```

`receive` 根据环境当前时间接收一封邮件，生成资源 ID 并运行收件自动化；附件传原始字节的 base64。`advance-time` 按到期先后执行 pending 任务，再将时钟设置到目标时间；不允许倒退。`delivery` 仅为尚未确定结果的收件人记录最终证据，退信时可另传 `--reason`。环境端的配置变化应写入实际状态，再由正常工具读取。

`events` 保存按 sequence 排序的操作、操作者、时间和前后状态；`sent_events` 保存发送瞬间的邮件快照，`delivery_events` 保存投递证据。删除 Sent 中的邮件不删除已经发生的发送记录。

## 维护

运行 `.venv/Scripts/python.exe tools/mail/generate_metadata.py` 可同步接口入口、schema 和 `prompt/tools/mail.md`。此命令只注册 Python 函数签名，不打开运行环境，也不执行邮件操作。

本轮验证范围为 Python 语法、公开接口注册、schema 与签名一致性及静态代码核对，按用户要求未运行测试集。
