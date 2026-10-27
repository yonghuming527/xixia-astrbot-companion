# 部署教程（Windows + AstrBot + NapCatQQ）

## 1. 架构

```text
QQ 私聊
  ↕
NapCatQQ / OneBot
  ↕
AstrBot
  ├─ LLM Provider
  ├─ 视觉 Provider
  ├─ STT Provider
  └─ 汐夏自制插件
```

插件只保存运行状态，不包含模型、QQ 密码或云端 API Key。

## 2. 准备组件

1. 从 [AstrBot 官方仓库](https://github.com/AstrBotDevs/AstrBot) 选择官方文档支持的安装方式。Windows 桌面环境可使用 AstrBot Launcher 或脚本安装。
2. 从 [NapCatQQ Releases](https://github.com/NapNeko/NapCatQQ/releases) 安装与当前 QQ 兼容的版本。
3. 在 NapCat 中启用 OneBot WebSocket，再在 AstrBot 中添加对应的 QQ/OneBot 平台配置。
4. 在 AstrBot 中至少配置一个文本 LLM Provider。视频插件还需要视觉 Provider 和 STT Provider。

WebSocket 地址、Token 和端口由使用者自己设定，不要照抄他人配置。

## 3. 安装插件

找到 AstrBot 实际使用的 Python，安装视频插件依赖：

```powershell
<ASTRBOT_PYTHON> -m pip install -r requirements.txt
```

将需要的目录原样复制到：

```text
<ASTRBOT_INSTANCE>/data/plugins/
```

例如：

```text
data/plugins/astrbot_plugin_xixia_proactive/
data/plugins/astrbot_plugin_xixia_qzone/
data/plugins/astrbot_plugin_xixia_video_reader/
```

重启 AstrBot。控制面板应显示三个插件，且无 ImportError。

## 4. 获取 `target_umo`

`target_umo` 是最重要的权限边界。仓库默认为空，未填时插件不会向任何会话执行受限操作。

1. 用允许控制机器人的 QQ 给机器人发一条测试私聊。
2. 在 AstrBot 日志或事件调试信息中查找 `unified_msg_origin`。
3. 它通常类似：

```text
qq_<BOT_QQ>:FriendMessage:<USER_QQ>
```

4. 把同一个值填入三个插件的 `target_umo`。

不要把真实 UMO 提交到 Git。

## 5. 配置主动消息与成长状态

参考 `config/astrbot_plugin_xixia_proactive.example.json`。推荐起步值：

- 无交互 90 分钟后才可能主动发送。
- 每日随机上限 3–5 条。
- 23:30–08:30 不主动打扰。
- 关系状态每 12 轮反思一次。
- `dry_run=true` 可先只记录不发送。

审核命令：

```text
查看关系状态
查看成长日记
```

## 6. 配置 QQ 动态

参考 `config/astrbot_plugin_xixia_qzone.example.json`。

支持：

```text
/动态 今晚的风很轻。
发动态：今晚的风很轻。
发一个你自己想发的动态
```

询问“你会发动态吗”、否定或取消不会触发发布。发布能否成功取决于 NapCat 版本是否支持 `send_qzone_msg`。

## 7. 配置只读视频理解

参考 `config/astrbot_plugin_xixia_video_reader.example.json`。

### 必要依赖

- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [FFmpeg](https://ffmpeg.org/download.html)
- 可接收本地图片的视觉 Provider
- 可转写 WAV 的 STT Provider
- Windows Edge（抖音页面读取）

`yt_dlp_module_path` 可留空，此时使用已安装的 `yt-dlp`。`ffmpeg_path` 可填绝对路径，或在 PATH 配置正确时保持 `ffmpeg`。

### Cookie

优先使用专用机器人账号。可在你自己授权的浏览器上导出 Netscape Cookie 文件：

```powershell
<ASTRBOT_PYTHON> -m yt_dlp --cookies-from-browser edge --cookies douyin-cookies.txt "https://www.douyin.com/"
```

将文件放在 AstrBot 的 `data/plugin_data/astrbot_plugin_xixia_video_reader/` 中，再把绝对路径填入 `cookie_file`。

Cookie 等同于登录凭证：不得上传、分享、写入 README 或记忆库。若疑似泄露，立即退出所有会话并刷新凭证。

### 触发方式

- 直接发送支持的哔哩哔哩/抖音链接。
- 明确说“帮我看、找一个、推荐一个、逛逛”并指定平台。
- `我要听歌 <歌名>` 只搜索对应歌曲素材，不计入每日 5 条浏览量。

## 8. 人格、Token 与长期记忆

`config/persona.example.md` 是脱敏范例，可粘贴到 AstrBot 的默认人格。不要把权限控制只写在人格里；真正的写操作仍必须由插件代码检查 `target_umo`。

`config/astrbot-token-saving.example.json` 是建议值片段，只合并对应字段，不要整个覆盖 `cmd_config.json`。

可选的长期记忆方案可使用任意 AstrBot 记忆插件。建议向量模型使用 `BAAI/bge-m3`，每次最多注入 3 条相关记忆。记忆插件不在本仓库中。

## 9. 可选语音链路

日常语音可使用 AstrBot 支持的 TTS Provider。本地克隆可参考 [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)。RVC 只用于后级音色转换，不应与普通 TTS 配置混为同一个 Provider。

未获得说话人授权时，不得上传、训练或发布其音色模型。

## 10. 验证

先停留在 `dry_run=true`，确认日志中的主动消息判断正确，再关闭观察模式。

```powershell
<ASTRBOT_PYTHON> -m unittest discover -s tests -v
Get-ChildItem plugins -Recurse -Filter *.py | ForEach-Object { & <ASTRBOT_PYTHON> -m py_compile $_.FullName }
```

手工验证清单：

1. 非指定 QQ 不能发动态。
2. “你会发动态吗？”不会触发发布。
3. 普通讨论“B 站推荐算法”不会自动浏览。
4. 当日第 6 条不同视频会被拒绝。
5. 23:30–08:30 不主动发送。
6. `查看关系状态` 和 `查看成长日记` 可读取本地状态。

## 11. 常见问题

### 插件不加载

确认目录名与 `metadata.yaml` 中的 `name` 一致，并使用 AstrBot 自己的 Python 安装依赖。

### 视频没有声音或画面

检查 `ffmpeg_path`、视觉 Provider ID 和 STT Provider ID；确保对应 Provider 能处理本地文件。

### 抖音登录失效

在机器人专用 Edge 中重新登录，重新导出 Cookie，替换本地文件。不要把 Cookie 发到聊天里。

### QQ 动态发布失败

在 NapCat 中确认当前版本包含 `send_qzone_msg`，并检查 QQ 账号是否可以正常发布空间动态。插件失败后不会自动重试。
