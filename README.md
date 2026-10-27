# 汐夏 AstrBot Companion

一组面向 QQ 私聊伴侣机器人的 AstrBot 插件与部署模板。项目重点是可审核记忆、受限主动消息、明确授权的 QQ 动态，以及只读视频理解。

本项目是非官方社区项目，与 AstrBot、NapCatQQ、QQ、哔哩哔哩和抖音官方无隶属关系。

> 本仓库不包含 QQ 号、API Key、Cookie、聊天记忆、音色素材或模型文件。

## 包含的插件

| 插件 | 功能 | 默认安全边界 |
| --- | --- | --- |
| `astrbot_plugin_xixia_proactive` | 随机主动消息、关系状态、未完事项和成长日记 | 未填 `target_umo` 时不向任何会话发送 |
| `astrbot_plugin_xixia_qzone` | 明确命令或明确自然语言请求后发布 QQ 空间文字动态 | 仅指定私聊 UMO 可发布 |
| `astrbot_plugin_xixia_video_reader` | 理解哔哩哔哩/抖音视频，支持按歌名准备素材 | 两平台合计每日最多 5 条，不执行点赞、评论等写操作 |

## 快速开始

1. 部署 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 和 [NapCatQQ](https://github.com/NapNeko/NapCatQQ)。
2. 安装本仓库的依赖。
3. 将 `plugins/` 下需要的插件目录复制到 AstrBot 实例的 `data/plugins/`。
4. 先发一条测试消息，从 AstrBot 日志取得自己的 `target_umo`。
5. 通过 AstrBot 控制面板配置插件和 Provider ID，然后重启。

完整步骤、配置示例和验证命令见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

## 目录

```text
plugins/     三个自制 AstrBot 插件
config/      脱敏的配置与人格模板
docs/        部署、安全与排错文档
tests/       不联网的核心逻辑测试
```

## 重要限制

- QQ 空间发布依赖 NapCat 对 `send_qzone_msg` Action 的支持。
- 抖音理解依赖本机 Edge 和用户自己的合法登录状态。
- 视频功能依赖 FFmpeg、`yt-dlp`、视觉 Provider 和 STT Provider。
- 长期记忆、TTS、GPT-SoVITS 和 RVC 是可选的外部集成，未捆绑在此仓库。
- 请遵守 QQ、哔哩哔哩和抖音的服务条款及当地法律。

## 开发测试

使用 AstrBot 自带的 Python 环境：

```powershell
<ASTRBOT_PYTHON> -m pip install -r requirements.txt
<ASTRBOT_PYTHON> -m unittest discover -s tests -v
Get-ChildItem plugins -Recurse -Filter *.py | ForEach-Object { & <ASTRBOT_PYTHON> -m py_compile $_.FullName }
```

## License

[MIT](LICENSE)
