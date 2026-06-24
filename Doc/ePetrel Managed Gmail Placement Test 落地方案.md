# ePetrel Managed Gmail Placement Test 落地方案

## 目标
每次测试生成唯一 `emailtestrequestid`，客户端使用指定发件箱发送到 ePetrel 托管 Gmail。检测服务确认邮件落入 Inbox 或 Spam 后，将结果回写 BFF。

## Request ID
BFF 创建请求时生成唯一 `emailtestrequestid`，并缓存：
- request_id
- user_id
- sender_email
- target_gmail
- status: pending/sent/completed/failed/expired
- placement: inbox/spam/unknown
- created_at / expires_at

## 客户端发送邮件时携带
- Subject: `... [emailtestrequestid]`
- Header: `X-ePetrel-EmailTestRequestId`
- Header: `X-ePetrel-Test-Sender`
- Body: `emailtestrequestid: xxx`

## Gmail 检测服务
建议使用 Gmail API，而不是普通 IMAP，原因是 Gmail API 能直接读取 `labelIds`。

检测逻辑：
1. 定时扫描托管 Gmail 最近邮件。
2. 根据 header、subject、body 匹配 `emailtestrequestid`。
3. 读取 Gmail `labelIds`：
   - 包含 `SPAM` => placement = `spam`
   - 包含 `INBOX` 且不含 `SPAM` => placement = `inbox`
   - 否则 => placement = `unknown`
4. 回写 BFF。

## BFF 回写接口
`POST /v1/email-test/results`

Body:
{
  "emailtestrequestid": "xxx",
  "placement": "inbox",
  "gmail_message_id": "xxx",
  "detected_at": "ISO_TIME"
}

Header:
`Authorization: Bearer INTERNAL_TOKEN`

## 客户端轮询
客户端调用：
`GET /v1/email-test/requests/{emailtestrequestid}`

返回：
{
  "status": "completed",
  "emailtestrequestid": "xxx",
  "placement": "inbox"
}