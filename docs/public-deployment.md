# 公网 MCP 部署

推荐结构：公网 Agent → HTTPS 域名 / Cloudflare Tunnel → 本机认证 MCP 8514 → 核心服务 8513。手机与电脑采集端继续通过局域网连接 8513。

1. 先运行本地配置生成器，确认 MCP 无凭据返回 401，有正确 Token 可完成 MCP 握手。
2. 在 `server/.env` 设置 `VEGLIA_PUBLIC_URL=https://mcp.example.com`（替换为自己的域名，不带路径、末尾斜杠或参数），重启 MCP。
3. Cloudflare Tunnel 的该域名路由指向 `http://127.0.0.1:8514`。路由整个主机名，保留 `/mcp`、`/.well-known/*`、`/authorize`、`/consent`、`/token`、`/register`、`/revoke`。
4. **不要把核心服务 8513 一起暴露到公网，也不要把无鉴权的旧版 MCP 放在此路由后面。** 本机到 cloudflared 的 HTTP 流量只走 loopback；若 cloudflared 位于另一台设备，这一段也应使用 TLS 或安全私网。
5. 从公网验证无凭据/错误凭据为 401、错误 Host/Origin 被拒绝，再连接 Agent。单看 `/health` 为 200 不能证明鉴权正常。

OAuth 使用授权码 + PKCE S256、明确的权限确认、1 小时访问令牌、7 天刷新令牌、刷新轮换和重放撤销。凭据保存在 `server/data/auth.sqlite3` 中；访问/刷新令牌和授权码只存摘要，注册客户端信息仍属于私密数据。授权密码采用随机高熵值，只在你自己的授权页填写。

ChatGPT 使用动态客户端注册（DCR）。默认允许官方 `chatgpt.com` 回调和原生客户端 loopback 回调；其他可信客户端的完整 HTTPS 回调地址填入 `VEGLIA_OAUTH_REDIRECT_URIS`，多个用英文逗号隔开。不要添加通配符。页面显示客户端名称和回调地址，名称由客户端提供，不能据此证明身份。

Codex 支持 OAuth 登录或通过 `bearer_token_env_var` 指定 Bearer Token。其他可配置请求头的 Agent 使用 `Authorization: Bearer ...`，不要把 Token 放在 URL。

如果额外启用 Cloudflare Access，Agent 需要同时满足 Access 和本项目的鉴权。传统 Access 浏览器登录页面不能代替 MCP OAuth；不了解客户端兼容性时，不要在 OAuth 和 MCP 路由前叠加该页面。可配置请求头的自动化程序可额外使用 Access Service Token。

直接从局域网访问新版 HTTP MCP时：显式设置 `VEGLIA_MCP_HOST=0.0.0.0`，在 `VEGLIA_MCP_ALLOWED_HOSTS` 加入局域网 `IP:端口`，客户端同样携带 Token；浏览器客户端还需配置精确 Origin。优先使用 stdio、本机回环或 TLS/VPN。防火墙限制来源。

参考：[MCP 授权规范](https://modelcontextprotocol.io/specification/latest/basic/authorization)、[OpenAI 鉴权文档](https://developers.openai.com/plugins/build/auth)、[Cloudflare Service Token](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/)。
