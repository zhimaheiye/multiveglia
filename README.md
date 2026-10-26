# MultiVeglia

让你授权的 AI 获取自己的 Android 手机活动、手机截图和 Windows 电脑状态。支持多电脑汇总、局域网 MCP，以及带 OAuth / Bearer Token 鉴权的远程 MCP。

本项目基于 [Evelyn & River 的 Veglia](https://github.com/sebastianevan200-stack/veglia)，保留原作者署名，沿用 **CC BY-NC-SA 4.0**。修改说明见 [CHANGELOG.md](CHANGELOG.md)。

仅用于你本人或明确同意的设备。截图和窗口标题可能包含隐私；授权给 Agent 的数据会传给该 Agent 及其服务提供商。Cloudflare 等反向代理也可能终止 TLS。自托管并不意味着数据不会经过第三方。

## 下载与首次运行

从本仓库 Releases 下载 `MultiVeglia-0.7.0-windows-x64.zip` 和 `MultiVeglia-0.7.0.apk`。Windows 包包含 Python 和依赖，解压到你有写入权限的目录即可使用，无需安装 Python。

1. 双击 `Setup.cmd`：在本机生成六枚互不相同的随机凭据，已有配置不会被覆盖。
2. 打开 `server/data/setup-credentials.txt` 查看手机 Token 和 Agent 凭据。**这个文件、`server/.env` 和整个 `server/data` 都是私密文件，不能上传。**
3. 双击 `Start.cmd` 启动核心服务、MCP 和电脑采集端。窗口保持开启，Ctrl+C 停止。
4. Android 11 或更新版本安装 APK，填入 `http://电脑局域网IP:8513` 和 **Phone Token**，启用无障碍服务，然后启动。Windows 防火墙只允许你信任的专用网络访问 8513。
5. 切换手机应用，再让 Agent 调用 `get_phone_activity` 验证。应用为空或心跳过期不等于 MCP 故障。

手机和电脑需要网络互通。默认局域网 HTTP 不提供传输加密；不可信网络上应使用 HTTPS 或 VPN。MCP 默认只监听本机。

## 连接 Agent

**本机 stdio**：命令为 Windows 包内 `python/python.exe`，参数为 `run.py stdio` 的绝对路径（例如 `["C:/Apps/MultiVeglia/run.py", "stdio"]）。stdio 的访问权限由本机进程和文件权限控制。

**HTTP MCP**：地址 `http://127.0.0.1:8514/mcp`，请求头 `Authorization: Bearer <MCP Token>`。推荐日常查询使用只读 Token；完整 Token 额外允许截图和拉起手机应用。核心服务 Token 和手机 Token 不能用来访问 MCP。

**ChatGPT / Codex 远程 MCP**：按 [公网部署说明](docs/public-deployment.md) 设置 HTTPS 域名后，选择 OAuth 连接。系统会打开你自己的授权页，输入本机生成的 OAuth 授权密码，并确认权限。这里只支持单个设备所有者，不能作为多个不相关用户共享的托管服务。

| 工具 | 权限 |
|---|---|
| `get_veglia_status`、`get_phone_activity`、`get_devices_activity`、`get_device_activity`、`get_desktop_activity`、`get_context` | `veglia:read` |
| `get_phone_screen` | `veglia:capture` |
| `summon_phone_ai` | `veglia:summon` |

未授权、错误或过期凭据均拒绝访问。只读 Token 不能调用截图和拉起应用，即使客户端尝试调用也会被服务器拒绝。

## 多电脑与轮换

其他电脑的采集端设置 `VEGLIA_HUB_URL` 为核心服务的局域网地址，设置独立的 `VEGLIA_DEVICE_ID`，并填入 Sensor Token，然后运行 `run.py sensor`。

手机 Token 可在现有 App 界面中修改，不需要重新安装。完整步骤见 [密钥轮换](docs/rotation.md)。APK 签名密钥与连接 Token 是不同的东西：前者用于安装升级，不能当作连接密码。

## 从源码运行与构建

Python 3.13+：`python -m pip install -r server/requirements.txt`，然后 `python setup.py`、`python run.py all`。电脑采集端仅支持 Windows；核心服务与 MCP 可在其他系统上运行，分别启动 `core` 和 `mcp`。

Android 构建使用 JDK 17、Android SDK Platform 34 和 Build Tools 34：

```text
python android/build.py --java-home PATH --build-tools PATH --android-jar PATH --keystore PRIVATE_KEY_PATH
```

通过环境变量 `VEGLIA_KEYSTORE_PASSWORD` 提供签名密码，默认别名为 `multiveglia`。脚本不生成或携带签名私钥，不会使用调试签名代替正式签名。

新签名不能直接覆盖另一个签名的旧 APK；第一次迁移可能需要卸载重装并重新启用无障碍服务。日常 Token 轮换无需升级 APK。

## 验证与限制

`python -m unittest discover -s server -p test_security_integration.py -v` 使用隔离的临时服务测试鉴权和 OAuth，不会操作真实手机。另有设备注册、上下文融合和代理绕过回归测试。真实手机截图、厂商后台限制以及云端 OAuth 连接需在部署后验证，自动化测试不替代这些验证。

凭据和 OAuth 数据保存在本机文件中；运行用户具有读取权限。不要与不可信的 Windows 用户共享目录，也不要将整个安装目录压缩后发送给别人。发布包应从干净源码构建。
