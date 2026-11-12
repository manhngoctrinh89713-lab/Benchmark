"""Public mail operations. Host environment controls are deliberately separate."""
from mcp.types import ToolAnnotations

TOOLS = {
    "list_accounts": "列出当前操作者可访问的账户、主地址、别名和实际权限。共享邮箱也是独立账户。",
    "get_account": "查询账户身份、当前操作者及 read/write/send_as/send_on_behalf/manage 权限。发送身份只能选主地址或别名。",
    "list_mailboxes": "列出文件夹 ID、路径、层级、系统标识、版本及邮件/未读数量；Drafts 的数量包含独立草稿。",
    "search_emails": "搜索邮件摘要和附件元数据。query 搜索主题与正文；各普通筛选条件同时成立，filters 内按 match=all/any 组合。条件对象为 field/op/value；eq 为相等或列表成员，contains 为子串，in 为候选值列表，exists 接收布尔值；lt/lte/gt/gte 仅支持 size 和 timestamp。mailbox 可传文件夹 ID 或完整路径；未指定时含 Trash。地址精确匹配且忽略大小写；since 包含、before 不包含。sort_by 为 timestamp/subject/size/from。size 为 UTF-8 正文与附件字节总量。offset 分页，limit 为 1..100；时间为带时区 ISO8601。",
    "read_email": "读取单封邮件正文、身份、收件人、附件元数据、会话和版本。读取不改变已读状态；收件人副本不显示密送名单。",
    "list_threads": "分页查询当前账户的邮件会话；query 匹配会话中任一邮件的主题或正文，按最后邮件时间倒序。",
    "read_thread": "按 thread_id 分页读取会话邮件及可见参与人，按时间正序；每封邮件仍保持独立内容和状态。",
    "update_threads": "对指定会话当前包含的邮件执行移动、已读、星标或分类更改；返回调用时的成员快照和逐封执行结果，稍后加入会话的邮件不受影响。最多 100 个会话、500 封邮件。",
    "list_attachments": "列出邮件附件 ID、文件名、类型、字节数及哈希，不返回附件字节。",
    "download_attachment": "按账户、邮件和附件 ID 下载原始附件字节。save_path 位于 workspace 内，相对路径从 workspace 解析；不覆盖已有文件。",
    "export_email": "将邮件导出为标准 MIME .eml 文件，含正文、附件和可见邮件头。save_path 位于 workspace 内；不覆盖已有文件。",
    "send_email": "提交新邮件并保存至 Sent；支持 To/Cc/Bcc、HTML、Reply-To、附件和代理发送。收件人可为明确邮箱地址、contact:<联系人ID>、group:<群组ID>；联系人和个人组立即解析，组织组在提交时展开。附件从 workspace 读取并保存字节快照。in_reply_to 使用父邮件 message_id。send_mode 为 send_as 或 send_on_behalf，后者同时显示实际 Sender。返回提交 ID 和已有状态；外部收件人无送达证据时保持 unknown。重复调用会重复发送。",
    "get_send_status": "查询提交记录及已有投递证据。accepted 表示已接受，delivered/bounced/partial 表示已记录的结果；unknown 表示该收件人尚无证据。隐藏群组成员不通过状态查询公开。",
    "create_draft": "创建可未完成的草稿；可暂缺收件人、主题或正文。地址引用立即解析，附件立即保存字节快照。send_mode 为 send_as/send_on_behalf；创建草稿仅需 write，实际发送另行检查发送权限。",
    "list_drafts": "分页列出账户草稿摘要、收件人、附件元数据和版本。草稿单独管理，不混入 search_emails 的已存储邮件。",
    "get_draft": "读取草稿完整内容、收件人、发送身份、附件元数据和版本。",
    "update_draft": "修改草稿中 changes 指定的字段，未指定字段保留；空收件人列表可清空地址。附件通过 update_draft_attachments 管理。expected_version 可用于并发检查。",
    "update_draft_attachments": "为草稿添加 workspace 文件或按 remove_ids 移除附件；同次移除并添加可替换附件，新附件获得新 ID。单个附件最多 25 MiB，总计最多 20 个、50 MiB；保存字节快照。",
    "delete_draft": "删除指定草稿及其附件快照；expected_version 可检查草稿是否已被修改。",
    "send_draft": "按草稿保存的内容与地址提交发送，检查当前发送权限；成功后消耗草稿。组织组在提交时展开，外部投递需另有证据。",
    "reply_email": "针对选定 email_id 生成回复，默认保存草稿；as_draft=false 立即发送。优先使用 Reply-To；回复已发送副本时使用原 To；reply_all 同时考虑原 To/Cc，排除自身并去重，密送不参与。可选择引用原文、附件和发送身份。",
    "forward_email": "转发选定邮件，默认保存草稿；as_draft=false 立即发送。可内联转发或以 .eml 附件转发；include_attachments 控制是否保留原附件。地址、正文和保留的附件形成新快照。",
    "update_emails": "批量移动邮件或设置已读、星标及分类；最多 500 个唯一 email_id。每封独立执行，返回逐项结果，失败项不回滚成功项。mailbox 使用 ID 或完整路径，移到 Archive 即归档，移到 Trash 即删除；移动保持邮件 ID。分类参数为分类 ID。",
    "copy_emails": "将指定邮件复制到同一账户的目标文件夹；逐项返回新 copy_id。副本获得新资源 ID，保留原 Message-ID、内容、附件和会话，原邮件保留。最多 500 封。",
    "delete_emails": "批量删除邮件，默认移入 Trash 并记录原位置；permanent=true 永久删除。逐项执行并返回结果，最多 500 封。",
    "restore_emails": "批量恢复 Trash 中邮件；默认返回原文件夹，原文件夹不存在时放入 INBOX，也可指定其他目标文件夹。保留邮件 ID，逐项返回结果。",
    "empty_mailbox": "清空指定文件夹当前邮件，默认移入 Trash；permanent=true 永久删除。不删除文件夹或子文件夹，不处理独立草稿。最多 500 封，逐项返回结果。清空 Trash 时须使用 permanent=true。",
    "create_mailbox": "创建单个自定义文件夹；parent_id 可指定父文件夹 ID，未指定时建在根目录。name 为不含斜杠的单个名称。",
    "update_mailbox": "重命名或移动自定义文件夹，保持文件夹和邮件 ID；子树路径随之更新。parent_id 指定新父文件夹，move_to_root=true 移到根目录。系统文件夹不可改名或移动。",
    "delete_mailbox": "删除自定义文件夹及子文件夹；默认将子树内邮件移入 Trash，恢复时进入 INBOX；permanent=true 同时永久删除这些邮件。系统文件夹不可删除。",
    "list_categories": "列出账户分类的 ID、名称、颜色和版本。",
    "write_category": "创建或修改账户分类；传 category_id 修改，不传则创建。分类名称在账户内唯一，color 为显示颜色文本。",
    "delete_category": "删除分类并移除账户邮件上的该分类标记，保留邮件内容与位置。",
    "search_contacts": "按姓名、地址、组织或备注子串搜索可见通讯录，空 query 列出全部；scope 为 all/personal/organization。个人联系人可管理，组织目录只读；分页 limit 为 1..100。",
    "get_contact": "读取可见联系人及其全部地址、默认地址、所属范围和版本。",
    "write_contact": "创建或修改自己的个人联系人；传 contact_id 修改。emails 为明确邮箱地址，default_email 必须属于 emails，省略时用第一项。组织目录只读。",
    "delete_contact": "删除自己的个人联系人。已经解析到草稿或定时邮件的明确地址保持不变。",
    "list_groups": "分页列出可见的个人联系人组和组织邮件群组摘要；组织群组包含邮件地址，成员另查。query 匹配名称或地址。",
    "get_group": "读取可见群组；include_members=true 时按成员可见权限返回成员列表。组织群组只读；个人组由本人管理。",
    "write_contact_group": "创建或修改个人联系人组；members 为明确邮箱地址，不嵌套其他组。传 group_id 修改，不传则创建。个人组用于编写时展开地址。",
    "delete_contact_group": "删除自己的个人联系人组；已编写邮件中展开的地址保持不变。",
    "resolve_recipients": "解析明确邮箱地址、contact:<联系人ID>、group:<群组ID> 并去重；多地址联系人使用默认地址。个人组立即展开，组织组保留群组地址并按权限显示成员；外部地址的目录状态为 unknown。",
    "list_delegates": "查询邮箱委托及各操作者的授权，需要该邮箱 manage 权限。",
    "set_delegate": "为已登记操作者设置邮箱委托，覆盖此人的既有授权；permissions 可含 read/write/send_as/send_on_behalf，各权限独立。仅邮箱所有者可管理，不提供租户级授权。expected_version 使用账户版本。",
    "remove_delegate": "移除指定操作者的邮箱委托，需 manage；不改变邮箱所有者权限。expected_version 使用账户版本。",
    "list_rules": "按 priority 升序、同优先级按 ID 列出收件规则。规则仅由新入站邮件触发，查询不会运行规则。",
    "write_rule": "创建或替换有限收件规则；conditions 全部成立且 exceptions 无一成立时匹配。条件采用 field/op/value，与邮件搜索一致，不检查 Bcc。actions 按顺序执行：move+mailbox、mark_read/star+value、add_category+category_id、trash、forward+recipients。priority 越小越先执行，stop_processing 停止后续规则。单条规则动作整体成功或回滚并留失败记录。仅新入站触发；自动转发/回复不再触发自动发送。传 rule_id 修改。",
    "delete_rule": "删除指定收件规则；不撤销该规则已经完成的操作。",
    "get_auto_reply": "读取自动回复启用状态、内部/外部正文、外部受众、有效时间和版本。",
    "set_auto_reply": "设置自动回复；内部按邮箱主地址同域判断，外部受众 external_audience 为 none/contacts/all。start_at/end_at 为带时区 ISO8601，有效范围左闭右开；省略则该端不限。每次设置重置回复历史，有效配置内每个地址最多回复一次，自动邮件及 Trash/Junk 不回复。启用需要 write 和 send_as。",
    "schedule_email": "将完整草稿排队定时发送并消耗草稿；send_at 为未来的带时区 ISO8601 时间。排队固定正文、附件、显式地址、联系人及个人组解析结果；组织组到实际提交时展开。到期使用排队操作者当前授权，失败保留 failed 状态。查询不推进时间。",
    "list_scheduled_emails": "分页查询定时邮件及冻结内容；status 可为 pending/submitted/failed/cancelled，省略时查询全部。",
    "update_scheduled_email": "修改 pending 定时邮件的发送时间，或用 replacement_draft_id 替换冻结内容并消耗该草稿。仅原排队操作者可修改；新时间须在当前环境时间之后。",
    "cancel_scheduled_email": "取消 pending 定时邮件；需账户 write 权限。取消后保留记录，不产生发送，也不自动恢复原草稿。",
}

READ_ONLY = {
    "list_accounts", "get_account", "list_mailboxes", "search_emails", "read_email",
    "list_threads", "read_thread", "list_attachments", "get_send_status", "list_drafts",
    "get_draft", "list_categories", "search_contacts", "get_contact", "list_groups", "get_group",
    "resolve_recipients", "list_delegates", "list_rules", "get_auto_reply", "list_scheduled_emails",
}


def register_tool(mcp, store, name):
    readonly = name in READ_ONLY
    mcp.tool(name=name, description=TOOLS[name], annotations=ToolAnnotations(
        readOnlyHint=readonly, destructiveHint=not readonly, idempotentHint=readonly, openWorldHint=False,
    ))(getattr(store, name))


def register_tools(mcp, store):
    for name in TOOLS:
        register_tool(mcp, store, name)
