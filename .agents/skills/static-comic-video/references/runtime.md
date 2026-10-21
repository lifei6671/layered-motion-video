# SC-P0 运行约定

工作目录是本 Skill 根 `.agents/skills/static-comic-video/`。依赖、虚拟环境和 Remotion 项目均在这里；不修改 VoiceStudio 的 Python 环境、配置或模型。仓库根的另一条分层动画路线保持独立。

## 安装与检查（PowerShell）

先进行服务能力发现；此脚本仅使用 Python 标准库，不需要先安装 WhisperX 或模型。优先使用本机服务进行其能满足的处理，确认具体缺口后才安装所需本地能力；评估依据见 [VoiceStudio](voicestudio.md)。

```powershell
uv run --no-project --offline --python 3.12.13 scripts/probe_voicestudio.py --url http://127.0.0.1:13900 --output reports/voicestudio.json
```

以下是本轮已验证的隔离本地运行路径，供服务无法提供完整原文强制对齐证据时补齐能力使用。不是每次制作视频都重新安装。

```powershell
Set-Location D:\wx_lifeilin\github.com\lifei6671\layered-motion-video\.agents\skills\static-comic-video
uv sync --locked
Push-Location renderer/static-comic
npm ci --no-audit --no-fund
node node_modules/@remotion/cli/remotion-cli.js versions
node node_modules/@remotion/cli/remotion-cli.js browser ensure
Pop-Location
```

`browser ensure` 是明确的依赖准备命令，可能下载浏览器；本机版本及可执行文件 SHA256 见 [doctor 记录](../reports/doctor.json)。`doctor` 不调用 ensure、不使用 `npx`，缺依赖时失败。换机器应重新检查并记录浏览器和 FFmpeg 实际版本，不沿用旧 PASS。

```powershell
.\.venv\Scripts\python.exe -m static_comic doctor --browser renderer/static-comic/node_modules/.remotion/chrome-headless-shell/win64/chrome-headless-shell-win64/chrome-headless-shell.exe --output reports/doctor.json
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
uv sync --locked --check
```

不提供 `--models-lock` 时模型项为 `NOT_RUN`，总体退出码 1 是预期结果。`doctor` 的总体状态仅覆盖运行检查；许可、可用图片渠道、阶段放行以及人工验收另见 [SC-P0 记录](../reports/SC-P0.md)。

## 模型准备与复用

本机已有 VoiceStudio 的识别模型，不重复下载：

- ASR：`Systran/faster-whisper-large-v3`，revision `edaa852ec7e145841d8ffdb056a99866b5f0a478`，CTranslate2 权重；位置见下方 `$asr`。本阶段显式用 CPU / int8 检查，不代表 GPU 不可用，也不改变 VoiceStudio 的设备设置。
- VoiceStudio 的 tiny 是 `csukuangfj/sherpa-onnx-whisper-tiny`，ONNX encoder/decoder 格式，不是 WhisperX 所需的 CTranslate2 格式；本期不引入第二个识别后端。用户已有的 large-v3 优先于初始探针所用 small 缓存。
- 中文对齐：`jonatasgrosman/wav2vec2-large-xlsr-53-chinese-zh-cn`，revision `99ccb2737be22b8bb50dcfcc39ad4d567fb90cfd`。这是 WhisperX 3.8.6 的默认中文对齐模型；识别模型不能替代它。
- VAD：WhisperX 3.8.6 自带 `assets/pytorch_model.bin`；锁定时连同包内 assets 文件一起计算摘要，不改写权重。

只有缺少中文对齐权重时，显式执行准备步骤（约 1.28 GB 权重，联网下载；不获取任何生产图片）：

```powershell
.\.venv\Scripts\python.exe -c "from huggingface_hub import snapshot_download; print(snapshot_download('jonatasgrosman/wav2vec2-large-xlsr-53-chinese-zh-cn',revision='99ccb2737be22b8bb50dcfcc39ad4d567fb90cfd',allow_patterns=['config.json','preprocessor_config.json','pytorch_model.bin','special_tokens_map.json','vocab.json']))"
```

下载成功后先记录文件哈希，再加载验证；不能因为 snapshot 目录存在就认为模型完整：

```powershell
$asr = 'C:\Users\lifei\AppData\Local\OmniVoice\hf_cache\models--Systran--faster-whisper-large-v3\snapshots\edaa852ec7e145841d8ffdb056a99866b5f0a478'
$alignment = 'C:\Users\lifei\.cache\huggingface\hub\models--jonatasgrosman--wav2vec2-large-xlsr-53-chinese-zh-cn\snapshots\99ccb2737be22b8bb50dcfcc39ad4d567fb90cfd'
.\.venv\Scripts\python.exe scripts/lock_models.py --asr $asr --asr-revision edaa852ec7e145841d8ffdb056a99866b5f0a478 --alignment $alignment --alignment-revision 99ccb2737be22b8bb50dcfcc39ad4d567fb90cfd --device cpu --compute-type int8 --output reports/models.lock.json
.\.venv\Scripts\python.exe -m static_comic doctor --models-lock reports/models.lock.json --browser renderer/static-comic/node_modules/.remotion/chrome-headless-shell/win64/chrome-headless-shell-win64/chrome-headless-shell.exe --output reports/doctor.json
```

`lock_models.py` 记录调用者指定的 revision 与实际字节，不向远端查询或证明 revision 来源；revision 应来自下载记录/已有 snapshot 名。`probe_models.py` 核验整个文件集合和 SHA256，设置为本地加载，运行 ASR/VAD 静音探针和中文对齐模型合成张量 forward。成功不能代表真实中文识别、语义边界或完整试听通过。

## 当前运行限制

- Python 3.12.13；Node 24.19.0；npm 11.17.0；Remotion 所有包固定 4.0.515；React / ReactDOM 19.2.8；WhisperX 3.8.6。Python 全部依赖见 `uv.lock`，Node 全部依赖见渲染目录 `package-lock.json`。
- 本次隔离环境安装 PyTorch 2.8.0+cpu。CUDA 未在该环境验证，不把 VoiceStudio 的 CUDA 状态套用到此环境。
- Pyannote 导入时报告 TorchCodec 缺 DLL，内置文件解码不可用；WhisperX 的 FFmpeg/内存数组路径已完成 ASR/VAD 静音探针。SC-P3 必须使用明确解码后的音频数组，并验证真实中文音频；不得把该警告隐藏为完整解码能力通过。
- `doctor` 用原生 node 加本地 JS 入口和参数数组运行 CLI，避免 Windows `.cmd`、shell 拼接和隐式安装。中文与空格路径、含 shell 特殊符号的参数和非零退出码都有回归测试。
- SC-P2 已增加视频 Composition、Studio 入口和无声技术渲染，见 [视觉执行协议](rendering.md)。SC-P3 增加 VoiceStudio 粗识别、锁定中文模型对齐、母带和人工覆盖，见 [语音协议](speech.md)。SC-P5 已接入完整有声预览、明确批准及正式封装，见 [交付流程](delivery.md)；SC-P6 已提供[缓存与恢复](cache.md)，真实样片与性能基线属于 SC-P7。

参考：[Remotion openBrowser](https://www.remotion.dev/docs/renderer/open-browser)、[WhisperX 官方项目](https://github.com/m-bain/whisperX)、[中文对齐模型](https://huggingface.co/jonatasgrosman/wav2vec2-large-xlsr-53-chinese-zh-cn)。

## Windows 进程边界

Python 内部继续用 resolve_path 校验单期相对路径、越界链接和输出重解析点。在启动 Node/Remotion、Studio 和媒体验证工具时，共用 process_args/process_path 将已授权的 `\\?\D:\...` 本地磁盘路径转为标准原生路径，覆盖 cwd、入口、bundle、props、public、浏览器及输出。参数数组和 shell=False 保持不变；UNC/设备命名空间不被转换为本地文件。FFmpeg 的 a:0、0:v:0 等非路径参数保持原样。适配器只改表示法，不能代替路径授权。

真实标准/扩展路径探针：`.venv/Scripts/python.exe scripts/verify_windows_paths.py --output <new-directory>`，每种条件产生独立90帧技术短片，检查 Composition、预览、1080p视觉及完整音频封装；production_accepted 始终 false。
