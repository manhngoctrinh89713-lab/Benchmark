# Chat 工具

Chat 工作台提供 57 个 MCP 接口，以微信式个人联系人、私聊和群聊为功能底本。状态位于运行环境的 `services/chat/state.json`，文件与其他工具共用 `workspace`。身份、好友关系、群成员关系、消息接收范围和个人本地记录分别保存。

## 功能范围

| 能力 | 接口 |
| --- | --- |
| 自己的身份与资料 | `get_profile`、`update_profile` |
| 联系人与好友关系 | `search_contacts`、`get_contact`、`update_contact`、`delete_contact`、`set_contact_blocked`、`send_friend_request`、`list_friend_requests`、`respond_friend_request` |
| 会话查询与个人设置 | `list_chats`、`get_chat`、`list_chat_members`、`update_chat_settings` |
| 群生命周期及邀请 | `create_chat`、`update_chat_members`、`list_group_invitations`、`respond_group_invitation`、`leave_chat`、`dissolve_group` |
| 群角色、资料、公告和置顶 | `transfer_group_owner`、`set_group_administrator`、`update_group`、`set_group_nickname`、`get_group_announcement`、`set_group_announcement`、`list_pinned_messages`、`set_message_pinned` |
| 消息查询 | `list_messages`、`read_message`、`get_message_context` |
| 文本、引用和提醒 | `send_message`，支持同会话引用、@成员和按权限@全体 |
| 文件、媒体和卡片 | `send_file`、`send_media`、`send_card`、`list_media`、`download_media`、`get_send_status` |
| 转发及合并记录 | `forward_message`、`forward_messages`、`read_merged_messages` |
| 本地整理与撤回 | `delete_message`、`delete_messages`、`clear_chat_history`、`recall_message`、`mark_read` |
| 会话草稿 | `get_draft`、`save_draft`、`clear_draft`、`send_draft` |
| 独立收藏 | `favorite_message`、`list_favorites`、`get_favorite`、`update_favorite`、`delete_favorite`、`forward_favorite`、`download_favorite_attachment` |

Agent 调用时加 `chat__` 前缀。每个接口的完整参数保存在对应目录的 `schema.json`，工具说明同步至 `prompt/tools/chat.md`。

## 身份与联系人

用户 ID 表示稳定身份。公开昵称、当前用户对联系人的备注、用户在各群中的群昵称分别保存；修改任一名称不改变用户身份或其他名称。

`contacts` 是环境的用户资料目录，`relations` 保存各用户自己的好友关系、拉黑状态、备注和标签。查询只返回当前用户有权查看的资料及自己的关系信息。共同群中的非好友可以按已知身份查询公开资料；联系电话仅向自己和自己的好友展示。资料中的组织名称是普通描述信息，不产生群管理权限。

好友申请先进入 pending，只有收件人可以接受或拒绝；接受后双方建立好友关系。删除好友是单方面关系变化，保留本地历史和共同群身份。私聊发送要求自己的好友关系有效且未拉黑；对方已删除或拉黑时，产生仅自己可见的 failed 消息，错误信息不区分对方的私人设置。共同群消息不受私聊拉黑影响。

本轮提供自己的昵称和联系电话修改，不提供账号注册、身份冒用或全网用户发现。环境中的用户由评测端登记，好友申请按明确用户 ID 定位。

## 会话及群管理

个人会话置顶、免打扰、隐藏和人工未读标记只影响当前用户。隐藏会话保留记录和成员身份，收到后续消息时重新出现在列表中。`mark_read` 清除本地消息未读和人工未读，不生成对方可见的已读回执。阅读与搜索均不自动标已读。

私聊两人，重复创建同一对用户的私聊会复用会话；创建群聊至少三人，之后可以因成员退出而只剩少量成员。创建者为群主，省略群名称时根据成员昵称生成。

| 操作 | 权限 |
| --- | --- |
| 邀请自己的未拉黑好友、修改自己的群昵称、退出群 | 当前普通成员 |
| 审批邀请、移除普通成员、修改群名及邀请确认、管理公告和置顶消息、@全体 | 群主或管理员 |
| 设置或撤销管理员、移除管理员、转让群主、解散群 | 群主 |

群主不能被移除，退出前先转让或解散；管理员不能移除其他管理员。转让后原群主成为普通成员。解散后全体停止群内发言和管理，已有本地历史保留。

普通成员在开启邀请确认的群中邀请好友，会创建待审批记录；批准之前不算加入。群主和管理员邀请可直接加入。邀请者离群时，其未完成申请过期；解散群时全部未完成申请过期。审批和直接加入都使用当前成员状态。

公告、置顶、角色、群名、成员加入退出和解散产生正常群通知。群资料及公告支持版本检查；删除公告保留递增版本，避免删除后重新发布使旧版本再次生效。`list_chat_members` 分页展示身份、昵称、备注、群昵称和角色。

## 接收范围与历史访问

每封消息保存发送当时的实际接收用户 ID，而不靠当前成员名单反推历史权限。

- 新成员仅接收实际加入后的消息，不自动取得入群前历史。
- 退出或被移除后停止接收后续消息，保留此前已接收且未本地删除的记录。
- 再次加入不会补齐离群期间的消息；此前仍保留的历史继续可见。
- 已退出群的详情和成员查询使用退出时保存的资料快照，不泄露后续群名、公告或成员变化。
- 当前公告属于群资料，新成员可读取当前公告；置顶消息仍受其原有消息接收范围限制。

分享此前聊天内容通过转发或合并转发完成，产生新的接收范围和内容副本。群管理权限不包含读取他人的本地历史或收藏。

## 消息与内容副本

支持文本、文件、图片、语音、视频、链接卡片、联系人名片、静态位置、合并记录和系统通知。媒体保存文件字节、名称、类型、大小和哈希，不执行拍摄、录音、转码或识别。语音可以下载和收藏，不支持直接转发；普通音频文件可以作为文件消息发送和转发。

引用同会话消息时保存发送者、展示文字及附件名称；引用文件不代表再次发送文件字节。原消息撤回后，普通时间线的引用区域显示原消息已撤回。@只改变提醒对象，整条消息仍向会话全部当前成员发送。

逐条转发创建独立消息，不继承引用或@。合并转发按原消息顺序保存内容快照，可分页展开，嵌套最多三层；展开时不重新读取源会话。语音和系统通知不能作为转发源。多目标转发逐目标返回结果，某个目标失败保留已经成功的发送；源内容无效时在开始发送前报错。

收藏归当前用户所有，保存独立内容快照及收藏时可见的引用展示内容。收藏后可以管理标题和标签、下载附件或再次转发；原消息撤回、删除或失去访问权不改变收藏。收藏中的语音仍不可转发。

文本中的 URL 或本地文件路径仅是文字。链接卡片保存明确 URL 及展示资料，不自动读取链接内容；发送文件必须通过文件或媒体接口。发送记录也不会把文字中提到的工作区文件认作已传输文件。

## 文件可用性、删除与撤回

文件和媒体发送时读取工作区并保存字节快照；此后源文件的修改、移动或删除不改变已发送内容。单文件上限 25 MiB，多选转发所含附件合计上限 50 MiB。下载目标必须在工作区内，且不覆盖已有文件。

文件的远端可用状态与当前用户的本地缓存分开记录。未下载文件可以因期限到达或环境端状态变化而无法获取；已经下载建立的本地缓存仍可再次保存或转发。缓存属于应用本地消息副本，工作区导出文件是另一份文件。清空本地消息后不能再通过原消息访问缓存，已导出的工作区文件保留。收藏及独立转发各有自己的字节副本。

| 操作 | 影响 |
| --- | --- |
| 本地单条或批量删除 | 隐藏自己的对应记录，保留其他用户记录及独立副本 |
| 清空本地历史 | 清空自己在该会话的当前记录，保留成员身份、收藏和工作区文件，继续接收后续消息 |
| 隐藏会话 | 仅移出列表，保留本地历史和成员身份 |
| 撤回 | 在期限内撤回自己已成功发送的消息；会话内保留提示，独立转发、合并记录、收藏和已保存文件保留 |
| 删除收藏 | 删除自己的收藏副本，保留源消息及其他副本 |

撤回需要仍可操作原会话，期限由环境的 `recall_window_seconds` 决定，不依赖工具调用次数。已发送消息不提供原地改写接口。

## 草稿和发送结果

每个用户每个会话一份文本草稿，可保存引用和@成员。草稿修改不产生发送；发送时重新检查会话成员、好友关系、引用可见性和@对象。成功发送后消耗草稿，投递失败保留草稿。草稿及其他可修改资源支持 `expected_version`，版本变化时该次修改报错。

消息状态为 sent 或 failed。sent 表示消息已被服务接受并存入其实际接收用户的环境本地记录，不能据此认定对方已阅读。Agent 的发送状态查询不暴露阅读回执。发送时的接收对象与内容保存在评测端事件中，事后删除本地消息不会删除已经发生的发送记录。

## 状态结构与兼容

本轮状态模型为 `model_version=3`。原 v2 环境可载入：保留用户、会话和消息 ID，补齐版本、关系、接收范围和成员记录。原 `contacts` 中的其他用户迁移为原操作者的好友，并建立对应初始反向好友关系，以兼容原来的私聊操作。新建 v3 环境直接配置真实关系。

| 位置 | 主要字段 |
| --- | --- |
| 顶层 | `model_version=3`、`now`、`current_user_id`、`recall_window_seconds` |
| `contacts[]` | 用户资料：`id/name`，可选 `wechat_id/phone/organization/version` |
| `relations[]` | `owner_id/user_id/is_friend/blocked/remark/tags/version`，每个方向独立 |
| `chats[]` | `id/type/name/member_ids`；群还需 `owner_id`，可选 `admin_ids/invite_requires_approval` |
| `chats[].membership[]` | `user_id/joined_at/left_at`，保留加入退出时序；初始成员时间可为 null |
| `messages[]` | `id/chat_id/sender_id/text/timestamp`；可选 `kind/recipient_ids/attachments/quote_message_id` 等 |
| `attachments[]` | `id/name/content_base64/size/sha256/content_type`；可选 `available/expires_at/downloaded_by` |
| 用户本地状态 | 会话的 `user_settings`；消息的 `hidden_by/read_by`；附件的 `downloaded_by` |
| 独立资源 | `friend_requests/invitations/drafts/favorites`，由相应接口管理 |

初始消息未填写 recipient_ids 时，默认已被当前配置的会话成员接收。这用于描述初始已有历史，不会为运行中新增成员补发旧消息。需要描述初始已退出成员时，应明确配置 membership、消息 recipient_ids 及其退出时的群资料快照。旧的 history_visibility 字段不参与 v3 的访问判断。

`search_contacts` 现在返回 `items/total/next_offset` 分页对象；`update_chat_members` 返回 `chat` 和 `pending_invitation_ids`；单条删除也使用统一逐项结果。原 14 个接口名称保留，消息和成员历史语义按本轮规则统一。

## 评测端入口

`local_chat.environment` 提供以下主机函数，不注册为 Agent MCP 工具：

| 函数 | 作用 |
| --- | --- |
| `advance_time(store, to)` | 显式推进环境时间，不允许倒退；查询和普通操作不自动推进时间 |
| `set_actor(store, user_id)` | 切换实际操作者；后续正常接口按此人的关系和群角色执行 |
| `receive_message(store, chat_id, sender_id, content)` | 按正常成员和好友关系投递入站消息，附件提供 base64 字节 |
| `set_media_available(store, message_id, attachment_id, available)` | 改变指定消息副本中附件的远端可获取状态，保留实际缓存和独立副本 |

从仓库根目录可使用对应 CLI：

```powershell
$env:PYTHONPATH = (Resolve-Path 'tools/chat/公用代码').Path
.venv/Scripts/python.exe -m local_chat.environment --run-root <运行环境路径> advance-time --to <带时区时间>
.venv/Scripts/python.exe -m local_chat.environment --run-root <运行环境路径> set-actor --user-id <用户ID>
.venv/Scripts/python.exe -m local_chat.environment --run-root <运行环境路径> receive --chat-id <会话ID> --sender-id <用户ID> --message-file <消息JSON路径>
.venv/Scripts/python.exe -m local_chat.environment --run-root <运行环境路径> set-media --message-id <消息ID> --attachment-id <附件ID> --available false
```

入站事件的 sender_id 是环境中实际发送者，入口临时按此人执行正常投递语义，完成后恢复操作者。群成员、角色、公告、联系人关系等人为变更可切换操作者后调用相同业务接口，结果写入实际环境，再由 Agent 查询。

`events` 按 sequence 记录操作者、时间、对象和前后状态；`delivery_events` 始终保存发送时的内容与实际接收对象；`member_events` 记录实际加入，不把批准前申请或入群前历史记为已经接收。事件序号区分同一环境时刻的先后顺序。

## 维护与验证

运行 `.venv/Scripts/python.exe tools/chat/generate_metadata.py` 可同步接口入口、schema、安装包工具列表和 `prompt/tools/chat.md`。此过程只读取函数签名，不打开环境，也不执行聊天动作。

本轮按用户要求未运行测试集或模型评测。验证范围为 Python 语法、公开接口注册、schema 结构及签名一致性、内部方法引用、安装包工具覆盖和静态行为核对。
