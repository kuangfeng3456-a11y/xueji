# 学迹鸿蒙客户端

这是学迹的 HarmonyOS / OpenHarmony Stage 模型工程，使用 ArkTS 调用仓库里已有的 FastAPI，不另起一套后端。

可以完成：

- 登录、注册（学生 / 教师 / 教务）
- 今日学习路径：计划任务、完成打卡、拍题练习、口语教练、复盘
- 在设置页修改 API 基址
- 相机拍照、相册选图，上传到 `POST /api/cloud/ocr/extract`，再保存错题
- 本机听写、上传录音走 `POST /api/coach/sessions/{id}/voice`，朗读优先走 `POST /api/cloud/sis/synthesize`
- 多轮教练会话，追问会带上同一会话的历史

## 用 DevEco Studio 打开

1. 安装 DevEco Studio 5.0.0 或更新版本，并准备 HarmonyOS NEXT SDK，API 12（`5.0.0(12)`）。
2. 打开本目录 `clients/harmonyos`，不要打开仓库根目录。
3. 等待工程同步。首次打开会下载 hvigor 与 ohpm 依赖，并可能生成 `local.properties`、`.hvigor/`、`oh_modules/`。这些文件已忽略，不要提交。
4. 连接真机或模拟器。调试签名在 DevEco 的 File > Project Structure > Signing Configs 里自动生成，不要把证书、p12 或 profile 提交到仓库。
5. 运行 entry 模块。

如果同步后提示 SDK 版本不一致，把 `build-profile.json5` 里的 `compatibleSdkVersion` / `targetSdkVersion` 改成你本机已安装的 API 版本，再同步一次。

## 连上学习服务

1. 在电脑上按仓库根目录说明启动 FastAPI（默认 `http://127.0.0.1:8000`）。
2. 模拟器访问本机服务时，地址通常不是 `127.0.0.1`。在客户端「设置」里改成电脑的局域网地址，例如 `http://192.168.1.20:8000`。
3. 工程已允许明文 HTTP（`network_config.json`），只为连接开发环境。正式发布应改为 HTTPS。
4. 手机与电脑需要在同一网络，且服务监听 `0.0.0.0`。

## 语音与拍照的真实行为

| 能力 | 云端已配置 | 未配置或调用失败 |
| --- | --- | --- |
| 拍题识别 | 华为云 OCR 填入题干 | 页面说明未开通，保留手动填写 |
| 语音提问 | 上传 wav 到一句话识别，再进入教练会话 | 不编造文本；可改用本机听写或文字 |
| 朗读 | 播放云端合成的音频 | 改用设备 TextToSpeech；设备也不支持时只显示文字 |

服务端是否接通，由环境变量中的华为云凭证决定。客户端不会假装识别成功。

本机听写和本机朗读依赖设备上的 Core Speech Kit。模拟器可能没有语音引擎，这时使用文字，或在真机上再试。

## 本环境的限制

编写这份源码的环境没有 DevEco Studio 和 HarmonyOS SDK，因此这里不能真正编译 HAP，也没有在模拟器里跑通。交付的是目录、`module.json5`、页面与接口调用都按 Stage 模型组织的源码，目标是 DevEco 打开后能同步并构建。若当前 SDK 的相机、选图或语音接口签名与 API 12 示例有差异，按 IDE 提示改对应调用即可，接口路径不用改。
