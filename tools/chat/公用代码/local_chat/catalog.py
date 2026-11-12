"""User-facing chat operations; environment controls are host-only."""
from mcp.types import ToolAnnotations

TOOLS = {
    "get_profile": "读取当前操作者的身份及个人资料；用户 ID 稳定，昵称变化不改变身份。",
    "update_profile": "修改自己的昵称或联系电话，未传字段保留；不修改他人资料或账号标识。expected_version 使用个人资料版本。",
    "search_contacts": "按可见资料及自己的备注、标签搜索联系人；默认只列好友。friends_only=false 包含已知用户及当前共同群成员；支持 tag、blocked 和 offset 分页，limit 为 1..100。返回 items/total/next_offset。",
    "get_contact": "读取已知用户的可见资料及自己与该用户的好友、拉黑关系、备注和标签。个人备注、公开昵称、群昵称分别保存；不返回对方的私人备注或拉黑名单。",
    "update_contact": "修改自己的好友备注或标签，tags 替换为所传完整列表，空列表清空；不改变对方身份。expected_version 使用 relationship.version。",
    "delete_contact": "单方面删除好友关系，保留既有本地聊天记录和共同群成员身份；expected_version 使用关系版本。再次私聊须重新建立好友关系。",
    "set_contact_blocked": "设置或解除自己的联系人拉黑状态；影响双方私聊投递，不影响共同群中的消息。expected_version 使用关系版本。",
    "send_friend_request": "向已知用户 ID 发起好友申请并附验证信息；同方向重复 pending 申请返回原申请。实际接受由目标用户决定，发起申请不建立好友关系。",
    "list_friend_requests": "分页查询自己的好友申请；direction 为 incoming/outgoing，status 为 pending/accepted/rejected，null 查询全部。",
    "respond_friend_request": "接受或拒绝发给自己的 pending 好友申请；接受后双方建立好友关系。已拉黑的联系人须先解除拉黑。",
    "list_chats": "列出自己可访问的私聊和群聊，包含仍保留本地历史的已退出群。支持名称/ID、类型、未读、置顶、免打扰和 active_only；默认不含隐藏会话。page 从 0 开始，limit 为 1..100；sort_by 为 last_active/name，置顶会话优先。返回列表。读取不标已读。",
    "get_chat": "读取会话详情、当前身份、成员状态及本地未读数；已退群仅返回退出时保存的群资料和自己保留的历史摘要。读取不标已读。",
    "list_chat_members": "分页查询会话成员，分别显示稳定用户 ID、昵称、自己的备注、群昵称和群角色；role 可为 owner/administrator/member。已退群返回退出时成员快照，并标明非当前名单。",
    "update_chat_settings": "设置自己的会话置顶、免打扰、隐藏或人工未读标记；未传字段保留。隐藏仅移出会话列表，不清空记录或退群；收到新消息后重新出现。",
    "create_chat": "创建 direct 私聊或 group 群聊，自动包含自己。选择未拉黑好友；私聊两人并复用已有会话，新建群至少三人，自己成为群主。省略群名称时根据成员昵称生成。",
    "update_chat_members": "邀请或移除群成员，action 为 add/remove。普通成员邀请自己的好友；开启邀请确认时生成 pending 申请，群主/管理员可直接邀请。移除需群主/管理员，管理员不能移除其他管理员；群主不可被移除，自己退出使用 leave_chat。新成员仅接收加入后的消息。返回会话详情和待审批 ID。",
    "list_group_invitations": "查询群邀请审批记录；群主/管理员可见全群，普通成员仅可见自己发起的邀请。status 为 pending/approved/rejected/expired，null 为全部。",
    "respond_group_invitation": "群主或管理员批准/拒绝 pending 邀请；批准时邀请者仍须在群，批准后才实际加入。批准前不授予消息访问。",
    "leave_chat": "退出当前群聊并停止接收后续消息，保留已有本地历史。群主须先转让群主或解散群；私聊用隐藏会话处理。",
    "transfer_group_owner": "群主将所有权转给另一名当前成员；原群主成为普通成员，新群主不再同时占管理员角色。expected_version 使用群版本。",
    "set_group_administrator": "群主设置或撤销另一名当前成员的管理员身份；管理员不能改变群主身份。expected_version 使用群版本。",
    "dissolve_group": "群主解散群聊，全部成员停止后续发言、接收和群管理，保留各自已有本地历史；待审批邀请记为 expired。",
    "update_group": "群主/管理员修改群名称或 invite_requires_approval，未传字段保留；这是群内公共设置，变更产生正常群通知。expected_version 使用群版本。",
    "set_group_nickname": "修改自己在当前群中的群昵称，空字符串恢复使用个人昵称；不改变公开资料或他人的个人备注。",
    "get_group_announcement": "读取群公告及版本；新成员可读取当前公告。已退出群只能读取退出时保存的公告快照。",
    "set_group_announcement": "群主/管理员发布或修改群公告，content=null 删除公告；保留递增版本并产生群通知。expected_version 使用公告版本，初次发布为 0。",
    "list_pinned_messages": "读取群中自己有权查看的置顶消息；置顶不使新成员获得此前未接收消息的历史访问权。",
    "set_message_pinned": "群主/管理员置顶或取消置顶一条自己可见的群消息；变更产生群通知。expected_version 使用群版本。",
    "list_messages": "组合查询自己的本地消息；支持会话、正文、发送人、时间、类型、附件、文件名、@对象和未读。所有筛选条件同时成立，默认时间倒序，offset 分页、limit 为 1..100。kind 为 text/file/image/audio/video/link/contact/location/merged/system。时间需带时区，since 包含、before 不包含。读取不标已读。",
    "read_message": "按全局消息 ID 读取自己本地可见的消息，包括撤回提示；不标已读。合并记录返回摘要，内容使用 read_merged_messages 展开。",
    "get_message_context": "读取自己可见的指定消息及同会话前后文；before/after 为 0..50，前后文按时间正序，读取不标已读。",
    "send_message": "发送文本，可引用同会话消息、@当前群成员；mention_all=true 需群主/管理员。@仅提醒，整条消息仍发送给全群。quote_message_id 引用普通时间线消息，不创建讨论线程。重复调用会重复发送。",
    "send_file": "发送独立文件消息，file_path 来自 workspace，单文件最多 25 MiB；发送时保存字节快照，之后源文件变化不影响已发送内容。",
    "send_media": "将 workspace 中的图片、语音或视频作为相应消息发送；kind 为 image/audio/video，文件类型须匹配，最多 25 MiB。不执行拍摄、录音、转码或语音识别。语音消息不能转发，可下载或收藏。",
    "send_card": "发送 link/contact/location 卡片。link 使用 http(s) URL、标题和描述；contact 使用可见用户的 user_id，分享公开名片；location 使用静态纬度和经度、标题及描述。各类型只使用对应字段，不上传本地路径或自动下载链接目标。",
    "get_send_status": "查询自己发出消息的 sent/failed 状态及可见错误，表示服务接收结果；不提供对方阅读回执，read_status 保持 unknown。",
    "list_media": "分页查询本地可见消息中的文件和媒体元数据，包含合并记录内的附件；query 匹配文件名。分别显示服务器是否可下载 available 和是否已有本地缓存 saved_locally。",
    "download_media": "按会话、消息及附件 ID 保存原始字节到 workspace，不覆盖已有文件；也支持合并记录中的附件。未过期的远端内容或自己的既有缓存可下载。不会推进时间；下载会建立本地缓存。",
    "forward_message": "把自己可见且支持转发的消息复制到另一个会话，生成新消息并保存内容快照；不继承原消息的引用或@。语音和系统通知不可转发，已撤回或本地删除内容不可转发。",
    "forward_messages": "选择同一会话的最多 100 条消息，按原时间顺序逐条或合并转发到最多 20 个目标；merged=true 生成聊天记录消息。目标逐项返回状态，某目标失败不回滚其他成功发送。源内容无效时在发送前报错；附件合计最多 50 MiB，合并嵌套最多 3 层。",
    "read_merged_messages": "分页展开合并转发记录；内容是转发时保存的副本，不重新访问源会话。item_path 为从 0 开始的条目索引路径，可展开嵌套合并记录，最多 3 层。",
    "delete_message": "仅从自己的本地历史删除一条消息或撤回提示；保留对方记录、收藏、独立转发副本和评测端发送记录。返回本地逐项删除结果。",
    "delete_messages": "批量删除自己本地的最多 500 条消息；逐项返回成功或失败，不撤回或删除对方副本。",
    "clear_chat_history": "清空自己在指定会话中当前保留的本地记录，保留群成员身份、其他用户的记录、收藏和工作区已下载文件。后续新消息仍会正常接收。",
    "recall_message": "在环境 recall_window_seconds 内撤回自己已成功发送的消息，需要仍可操作该会话。会话中保留撤回提示，引用区域显示原消息已撤回；独立转发、合并记录、收藏和已保存文件不随之删除。",
    "mark_read": "清除自己对当前本地可见消息的未读状态及人工未读标记，不向他人暴露阅读回执；读取查询本身不标已读。",
    "get_draft": "读取当前用户在指定会话保存的文本草稿；每个用户每个会话一份草稿，未保存时返回 null。",
    "save_draft": "保存或替换自己的会话文本草稿，可带引用和@成员；不产生发送。修改和发送时检查当前会话条件，expected_version 使用草稿版本，首次创建为 0。",
    "clear_draft": "清空自己的会话草稿；expected_version 可检查草稿是否变化，不影响已发送消息。",
    "send_draft": "按草稿文本、引用和@提交发送，重新检查会话、成员和联系人关系；发送成功后清除草稿，投递失败保留草稿。",
    "favorite_message": "把自己可见消息保存为独立收藏，支持文本、媒体、卡片和合并记录，保留原内容副本；可设置标题和标签。原消息后续撤回或删除不改变收藏。系统通知不可收藏。",
    "list_favorites": "按标题、文本和标签分页搜索自己的收藏；不暴露其他用户的收藏。",
    "get_favorite": "读取自己的收藏及内容元数据；合并记录分页展开，item_path 为嵌套条目索引路径。",
    "update_favorite": "修改自己收藏的标题或标签，未传字段保留，空标签列表清空；不改写保存的原消息内容。",
    "delete_favorite": "删除自己的收藏及其内容副本，不影响原消息、独立转发或工作区文件。",
    "forward_favorite": "将自己的收藏副本发送到目标会话，生成新消息；不依赖原消息仍可访问。语音收藏不可转发。",
    "download_favorite_attachment": "从自己的收藏副本下载附件，包括合并记录内附件，save_path 位于 workspace；不覆盖已有文件，不受原消息过期、撤回或删除影响。",
}

READ_ONLY = {"get_profile", "search_contacts", "get_contact", "list_friend_requests", "list_chats", "get_chat",
             "list_chat_members", "list_group_invitations", "get_group_announcement", "list_pinned_messages",
             "list_messages", "read_message", "get_message_context", "get_send_status", "list_media",
             "read_merged_messages", "get_draft", "list_favorites", "get_favorite"}


def register_tool(mcp, store, name):
    readonly = name in READ_ONLY
    mcp.tool(name=name, description=TOOLS[name], annotations=ToolAnnotations(
        readOnlyHint=readonly, destructiveHint=not readonly, idempotentHint=readonly, openWorldHint=False,
    ))(getattr(store, name))


def register_tools(mcp, store):
    for name in TOOLS:
        register_tool(mcp, store, name)
