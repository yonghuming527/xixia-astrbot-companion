# 安全说明

## 绝不得提交

- `cmd_config.json` 和 AstrBot 实际插件配置
- QQ 号、`target_umo`、OneBot Token 和控制面板密码
- API Key、Cookie、令牌、浏览器配置文件
- `data_v4.db`、记忆库、聊天记录和日记
- 音色素材、训练数据、模型权重和下载的视频

`.gitignore` 只是最后一道保护，提交前仍应手工检查：

```powershell
git diff --cached
git grep -n -i -E "api[_-]?key|authorization|cookie|password|token"
```

## 最小权限

- 三个插件都应使用同一个、精确的私聊 `target_umo`。
- 发布动态仅允许明确命令或明确的发布请求。
- 视频功能只读，不增加点赞、评论、关注、收藏或支付接口。
- Cookie 应属于专用账号，并存在仓库之外。

## 音色和内容授权

只使用自有、已授权或许可条款允许的音频、视频和图像素材。不得用音色克隆进行欺诈、冒充或骚扰。

## 发现泄露时

1. 撤销泄露的 API Key 和会话。
2. 在对应平台重新登录并刷新 Cookie。
3. 从 Git 历史中清理敏感文件，不要只删除最新版本。
4. 检查最近的 API 用量和账号操作记录。
