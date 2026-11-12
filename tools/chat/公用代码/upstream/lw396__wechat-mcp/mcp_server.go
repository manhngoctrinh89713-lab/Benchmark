package main

import (
	"context"
	"encoding/base64"

	"github.com/lw396/wechat-mcp/config"
	"github.com/modelcontextprotocol/go-sdk/mcp"
	"github.com/sirupsen/logrus"
)

func InitMCPServer(appServer *AppServer) *mcp.Server {
	server := mcp.NewServer(
		&mcp.Implementation{
			Name:    config.AppName,
			Version: config.AppVersion,
		},
		&mcp.ServerOptions{
			InitializedHandler: func(ctx context.Context, req *mcp.InitializedRequest) {
				if req != nil {
					appServer.trackSession(req.Session)
				}
			},
		},
	)

	registerTools(server, appServer)

	logrus.Info("MCP Server initialized with official SDK")

	return server
}

func registerTools(server *mcp.Server, appServer *AppServer) {
	mcp.AddTool(server, &mcp.Tool{
		Name:        "check_login_status",
		Description: "检查当前微信登录状态",
	},
		func(_ context.Context, req *mcp.CallToolRequest, _ any) (*mcp.CallToolResult, any, error) {
			result := appServer.handleCheckLoginStatus()
			return convertToMCPResult(result), nil, nil
		},
	)

	mcp.AddTool(server,
		&mcp.Tool{
			Name:        "get_self_wxid",
			Description: "获取当前登录账号的 wxid",
		},
		func(_ context.Context, req *mcp.CallToolRequest, _ any) (*mcp.CallToolResult, any, error) {
			result := appServer.handleGetSelfWxid()
			return convertToMCPResult(result), nil, nil
		},
	)

	mcp.AddTool(server,
		&mcp.Tool{
			Name:        "send_text_message",
			Description: "使用微信发送文本、卡片、网络图片或文件消息",
		},
		func(_ context.Context, req *mcp.CallToolRequest, args SendFlexMessageArgs) (*mcp.CallToolResult, any, error) {
			result := appServer.handleSendFlexMessage(args)
			return convertToMCPResult(result), nil, nil
		},
	)

	mcp.AddTool(server,
		&mcp.Tool{
			Name:        "get_self_info",
			Description: "获取当前登录账号微信的详细信息",
		},
		func(_ context.Context, req *mcp.CallToolRequest, _ any) (*mcp.CallToolResult, any, error) {
			result := appServer.handleGetSelfInfo()
			return convertToMCPResult(result), nil, nil
		},
	)

	mcp.AddTool(server,
		&mcp.Tool{
			Name:        "get_message_types",
			Description: "获取微信客户端的消息类型字典",
		},
		func(_ context.Context, req *mcp.CallToolRequest, _ any) (*mcp.CallToolResult, any, error) {
			result := appServer.handleGetMsgTypes()
			return convertToMCPResult(result), nil, nil
		},
	)

	mcp.AddTool(server,
		&mcp.Tool{
			Name:        "get_chat_rooms",
			Description: "获取当前微信账号的群聊列表",
		},
		func(_ context.Context, req *mcp.CallToolRequest, _ any) (*mcp.CallToolResult, any, error) {
			result := appServer.handleGetChatRooms()
			return convertToMCPResult(result), nil, nil
		},
	)

	mcp.AddTool(server,
		&mcp.Tool{
			Name:        "get_chat_room_members",
			Description: "查询微信群聊成员列表",
		},
		func(_ context.Context, req *mcp.CallToolRequest, args RoomIDArgs) (*mcp.CallToolResult, any, error) {
			result := appServer.handleGetChatRoomMembers(args)
			return convertToMCPResult(result), nil, nil
		},
	)

	mcp.AddTool(server,
		&mcp.Tool{
			Name:        "get_chat_room_alias",
			Description: "查询群聊中某位成员的群昵称",
		},
		func(_ context.Context, req *mcp.CallToolRequest, args ChatRoomAliasArgs) (*mcp.CallToolResult, any, error) {
			result := appServer.handleGetAliasInChatRoom(args)
			return convertToMCPResult(result), nil, nil
		},
	)

	mcp.AddTool(server,
		&mcp.Tool{
			Name:        "invite_chat_room_members",
			Description: "通过邀请链接方式添加群聊成员",
		},
		func(_ context.Context, req *mcp.CallToolRequest, args ChatRoomMembersArgs) (*mcp.CallToolResult, any, error) {
			result := appServer.handleInviteChatRoomMembers(args)
			return convertToMCPResult(result), nil, nil
		},
	)

	mcp.AddTool(server,
		&mcp.Tool{
			Name:        "add_chat_room_members",
			Description: "将联系人直接拉入指定群聊",
		},
		func(_ context.Context, req *mcp.CallToolRequest, args ChatRoomMembersArgs) (*mcp.CallToolResult, any, error) {
			result := appServer.handleAddChatRoomMembers(args)
			return convertToMCPResult(result), nil, nil
		},
	)

	mcp.AddTool(server,
		&mcp.Tool{
			Name:        "remove_chat_room_members",
			Description: "将指定成员移出群聊",
		},
		func(_ context.Context, req *mcp.CallToolRequest, args ChatRoomMembersArgs) (*mcp.CallToolResult, any, error) {
			result := appServer.handleRemoveChatRoomMembers(args)
			return convertToMCPResult(result), nil, nil
		},
	)

	mcp.AddTool(server,
		&mcp.Tool{
			Name:        "revoke_message",
			Description: "撤回指定微信消息",
		},
		func(_ context.Context, req *mcp.CallToolRequest, args MsgIDArgs) (*mcp.CallToolResult, any, error) {
			result := appServer.handleRevokeMessage(args)
			return convertToMCPResult(result), nil, nil
		},
	)

	mcp.AddTool(server,
		&mcp.Tool{
			Name:        "forward_message",
			Description: "将历史消息转发给指定联系人或群聊",
		},
		func(_ context.Context, req *mcp.CallToolRequest, args ForwardMessageArgs) (*mcp.CallToolResult, any, error) {
			result := appServer.handleForwardMessage(args)
			return convertToMCPResult(result), nil, nil
		},
	)

	mcp.AddTool(server,
		&mcp.Tool{
			Name:        "send_pat_message",
			Description: "在群聊中拍一拍指定成员",
		},
		func(_ context.Context, req *mcp.CallToolRequest, args PatMessageArgs) (*mcp.CallToolResult, any, error) {
			result := appServer.handleSendPatMessage(args)
			return convertToMCPResult(result), nil, nil
		},
	)

	mcp.AddTool(server,
		&mcp.Tool{
			Name:        "get_audio_message",
			Description: "下载微信语音消息为 MP3",
		},
		func(_ context.Context, req *mcp.CallToolRequest, args AudioMessageArgs) (*mcp.CallToolResult, any, error) {
			result := appServer.handleGetAudioMsg(args)
			return convertToMCPResult(result), nil, nil
		},
	)

	mcp.AddTool(server,
		&mcp.Tool{
			Name:        "download_image",
			Description: "下载并解密微信图片消息",
		},
		func(_ context.Context, req *mcp.CallToolRequest, args DownloadImageArgs) (*mcp.CallToolResult, any, error) {
			result := appServer.handleDownloadImage(args)
			return convertToMCPResult(result), nil, nil
		},
	)

	mcp.AddTool(server,
		&mcp.Tool{
			Name:        "download_attachment",
			Description: "下载微信消息附件",
		},
		func(_ context.Context, req *mcp.CallToolRequest, args DownloadAttachArgs) (*mcp.CallToolResult, any, error) {
			result := appServer.handleDownloadAttach(args)
			return convertToMCPResult(result), nil, nil
		},
	)

	mcp.AddTool(server,
		&mcp.Tool{
			Name:        "get_contacts",
			Description: "获取微信完整通讯录",
		},
		func(_ context.Context, req *mcp.CallToolRequest, _ any) (*mcp.CallToolResult, any, error) {
			result := appServer.handleGetContacts()
			return convertToMCPResult(result), nil, nil
		},
	)

	mcp.AddTool(server,
		&mcp.Tool{
			Name:        "get_friends",
			Description: "获取微信好友列表",
		},
		func(_ context.Context, req *mcp.CallToolRequest, _ any) (*mcp.CallToolResult, any, error) {
			result := appServer.handleGetFriends()
			return convertToMCPResult(result), nil, nil
		},
	)

	mcp.AddTool(server,
		&mcp.Tool{
			Name:        "get_info_by_wxid",
			Description: "根据 wxid 获取微信联系人信息",
		},
		func(_ context.Context, req *mcp.CallToolRequest, args InfoByWxidArgs) (*mcp.CallToolResult, any, error) {
			result := appServer.handleGetInfoByWxid(args)
			return convertToMCPResult(result), nil, nil
		},
	)

	mcp.AddTool(server,
		&mcp.Tool{
			Name:        "refresh_moments",
			Description: "刷新朋友圈数据",
		},
		func(_ context.Context, req *mcp.CallToolRequest, args RefreshPyqArgs) (*mcp.CallToolResult, any, error) {
			result := appServer.handleRefreshPyq(args)
			return convertToMCPResult(result), nil, nil
		},
	)

	mcp.AddTool(server,
		&mcp.Tool{
			Name:        "accept_new_friend",
			Description: "根据好友申请参数通过好友请求",
		},
		func(_ context.Context, req *mcp.CallToolRequest, args AcceptNewFriendArgs) (*mcp.CallToolResult, any, error) {
			result := appServer.handleAcceptNewFriend(args)
			return convertToMCPResult(result), nil, nil
		},
	)

	mcp.AddTool(server,
		&mcp.Tool{
			Name:        "receive_transfer",
			Description: "接受好友发起的转账",
		},
		func(_ context.Context, req *mcp.CallToolRequest, args ReceiveTransferArgs) (*mcp.CallToolResult, any, error) {
			result := appServer.handleReceiveTransfer(args)
			return convertToMCPResult(result), nil, nil
		},
	)
}

func convertToMCPResult(result *MCPToolResult) *mcp.CallToolResult {
	var contents []mcp.Content
	for _, c := range result.Content {
		switch c.Type {
		case "text":
			text := c.Text
			if c.Data != "" {
				text += "\n附加数据: " + c.Data
			}
			contents = append(contents, &mcp.TextContent{Text: text})
		case "image":
			imageData, err := base64.StdEncoding.DecodeString(c.Data)
			if err != nil {
				logrus.WithError(err).Error("Failed to decode base64 image data")
				contents = append(contents, &mcp.TextContent{
					Text: "图片数据解码失败: " + err.Error(),
				})
			} else {
				contents = append(contents, &mcp.ImageContent{
					Data:     imageData,
					MIMEType: c.MimeType,
				})
			}
		}
	}

	return &mcp.CallToolResult{
		Content: contents,
		IsError: result.IsError,
	}
}
