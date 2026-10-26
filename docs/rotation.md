# 密钥轮换

六种凭据分别用于 Core 管理、Phone 上报、Sensor 上报、MCP 完整权限、MCP 只读权限和 OAuth 授权页面。不要复用，不要上传实际值。

## 手机 Token

1. 生成新随机值：`python -c "import secrets; print(secrets.token_urlsafe(32))"`。
2. 更新服务端 `VEGLIA_PHONE_TOKEN`。如需短暂过渡，将旧值放入 `VEGLIA_PHONE_TOKEN_PREVIOUS`，将到期的 Unix 秒时间戳放入 `VEGLIA_PHONE_TOKEN_PREVIOUS_UNTIL`。
3. 重启 Core；手机停止服务，更新 Token，再启动。无需重装 App。
4. 验证手机心跳和上报；到期后旧值自动被拒绝，再删除旧值配置并重启。

过渡到期必须是有限时间。旧值不填到期时间或到期时间格式错误时不会被接受。泄露凭据应尽快停用，勿长时间保留过渡。

## 从旧版共享 Token 迁移

旧版 `VEGLIA_TOKEN` 是所有核心接口的管理密钥。迁移时必须换成新的 Core 管理密钥，并将手机和电脑上报分别改用 Phone/Sensor Token。

暂时没改好设备时，可以把旧共享密钥同时设为 Phone 和 Sensor 的 `PREVIOUS` 值，给定短暂期限。这样它只保留旧设备继续上报所需的权限，不能读取设备状态、请求截图或拉起应用。

迁移会重启服务，内存中的近期活动记录会清空；备份配置并在合适时间切换。不能同时保证永久接受旧泄露密钥和将它撤销。

## Agent 与 OAuth

MCP Token 使用相同的 `_PREVIOUS` / `_PREVIOUS_UNTIL` 过渡机制，轮换它不需要动手机。已持有 Token 的客户端必须在期限内更新。

OAuth 客户端正常使用刷新令牌即可。退出连接可调用 `/revoke`；刷新令牌被再次使用时，该令牌族会失效，需要重新授权。

如需强制撤销所有 OAuth 连接：停止 MCP，备份后移走 `server/data/auth.sqlite3`，再启动；所有客户端需重新连接注册。只更换 OAuth 授权密码不会自动撤销已授权的令牌。授权数据库和配置备份都属于私密文件。
