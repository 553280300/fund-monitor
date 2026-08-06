# 通知渠道

支持桌面通知、邮件、Telegram 和通用 Webhook。渠道名称、类型和非敏感参数保存在本地数据库；邮件授权码、Telegram Bot Token 与 Webhook secret 保存在 Windows 系统凭据库。

Telegram 需要 `chat_id`；Webhook 需要完整 HTTP(S) URL；邮件需要 SMTP 主机、端口、用户名、发件人与收件地址。每个渠道的配置错误只影响该渠道，不会停止监控或其他渠道投递。
