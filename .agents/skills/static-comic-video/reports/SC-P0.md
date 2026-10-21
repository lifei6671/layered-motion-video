# SC-P0 环境、版本与运行基线

执行日期：2026-10-21（Asia/Shanghai）。本次交付范围：SC-P0 和项目级 Skill 入口。SC-P1～SC-P7 尚未实现，未制作视频。运行与模型基线 `PASS`；不代表首版引擎完成。

## 工作区与文件边界

起始 HEAD：`3c0b583102984e01c7f27fc72b07da9a1998be21`。
原有修改：`.gitignore`、`README.md`；原有未跟踪文件：`DESIGN.md` 和 `docs/` 下三个方案文件。原始文件哈希记录在 [baseline.json](baseline.json)。本轮实现只新增 `.agents/skills/static-comic-video/`，不提交、不推送。

用户明确要求以 Skill 形式交付，因此方案中计划的仓库根 `renderer/static-comic/` 调整为 Skill 内的同名路径。Python 模块为 Skill 内 `static_comic/`，模型准备/服务发现工具为 `scripts/`；不与另一条分层动画方案混用。

## 任务记录

| 任务 | 状态 | 实际结果/证据 |
|---|---|---|
| SC-P0-01 | PASS | 仓库基线、原有文件哈希、用户提供作用域规则已确认；Skill/Python/渲染器边界已建立 |
| SC-P0-02 | PASS | [doctor.json](doctor.json)：Python、Node、Remotion CLI、React SSR、Chrome 启动、FFmpeg/ffprobe、WhisperX import 及完整模型加载探针通过 |
| SC-P0-03 | PASS | `uv.lock`、渲染目录 `package-lock.json`；[models.lock.json](models.lock.json) 记录 ASR/中文对齐/VAD revision、设备和逐文件 SHA256；浏览器/FFmpeg 可执行文件摘要在 doctor 报告 |
| SC-P0-04 | PASS | 用户确认“个人使用，或总人数不超过 3 人的公司”；按官方当前许可页面记录适用范围，不替未来使用者作判断、不购买许可 |
| SC-P0-05 | PASS | [运行约定](../references/runtime.md)；真实本地命令可执行；Windows 中文/空格路径、特殊符号参数、缺可执行文件、超时、退出码测试通过；不使用 npx 自动取包 |
| SC-P0-06 | PASS（能力盘点） | [图片能力与许可记录](license-and-capabilities.json)；已区分本地生图未接入、第三方渠道未选择、人工提示词可交付；未生成或下载生产图片 |

本轮追加用户约定：**先检查并优先复用本地 VoiceStudio 服务，服务不满足具体要求时才准备本地模型；先查已有权重，避免重复下载**。[服务评估](../references/voicestudio.md) 和 [实时只读报告](voicestudio.json) 已落盘。接口健康/ready 不代表实际语音转录或严格对齐通过。

## 实测版本与结果

| 项目 | 本次基线 |
|---|---|
| Python / Node / npm | 3.12.13 / 24.19.0 / 11.17.0 |
| Remotion | 4.0.515；所有 `@remotion/*` 一致 |
| React / ReactDOM | 19.2.8 |
| Chrome Headless Shell | Skill 自有依赖目录，149.0.7790.0 |
| FFmpeg / ffprobe | N-126374-g089a48eb36-20260831 |
| WhisperX / PyTorch | 3.8.6 / 2.8.0+cpu；本地探针显式 CPU / int8，无 CUDA 回退或 GPU 性能结论 |
| ASR | 复用 VoiceStudio 的 faster-whisper-large-v3；离线加载 + 1 秒静音 ASR/VAD 返回空 segments |
| 对齐 | wav2vec2-large-xlsr-53-chinese-zh-cn；离线加载、合成输入 forward 输出 `[1,49,3503]` 且全为有限数值 |
| VoiceStudio 服务 | 0.5.6；13900 可达、`ready: true`、当前 whisperx / large-v3、配置 CUDA；实际服务转录 `NOT_RUN` |

关键执行命令（工作目录均为 Skill 根，渲染器命令在其目录）：

```powershell
uv sync --locked
uv sync --locked --check
npm install --no-audit --no-fund
node node_modules/@remotion/cli/remotion-cli.js versions
node node_modules/@remotion/cli/remotion-cli.js browser ensure
.\.venv\Scripts\python.exe -m static_comic doctor --models-lock reports/models.lock.json --browser renderer/static-comic/node_modules/.remotion/chrome-headless-shell/win64/chrome-headless-shell-win64/chrome-headless-shell.exe --output reports/doctor.json
.\.venv\Scripts\python.exe scripts/probe_voicestudio.py --url http://127.0.0.1:13900 --output reports/voicestudio.json
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -X utf8 C:/Users/lifei/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```

安装时首次使用 `npm install --no-audit --no-fund` 生成锁文件；复现入口为 `npm ci`，两者不混同为重复安装验收。模型准备与锁定的完整参数见 runtime.md；doctor.json 保存逐探针的参数数组、工作目录、退出码、stdout、stderr 和锁文件摘要。

验证结果：10 项 unittest `PASS`；Skill frontmatter 校验 `PASS`；uv 环境与锁匹配 `PASS`；最终 doctor 全部运行项 `PASS`。独立复核的最终结论另见 delivery-review.md（复核结束后生成）。

## 失败、修正与限制

- 初始探针发现 Windows 子进程默认编码不一致，已固定 `PYTHONIOENCODING=utf-8` 并通过中文路径回归。Remotion 自有 Browser API 与 Puppeteer 不同，运行探针已使用公开启动/关闭接口；不再假定 `newPage()` 等签名。
- 中文对齐权重首次下载出现 `IncompleteRead`，一次续传重试后完成；最终核验完整文件哈希，并实际加载。没有用不完整缓存冒充模型成功。
- 历史初始失败报告保留为 `doctor-initial.json`，最终状态以 `doctor.json` 为准。
- TorchCodec 缺 DLL，Pyannote 的内置文件解码不可用。明确的内存数组路径已经运行；SC-P3 必须使用 FFmpeg 解码后输入数组。警告保留在原始报告，不把此组件列为可用。
- 本地生图服务未接入、第三方图库尚未选择，不阻止 SC-P1/SC-P2 的技术夹具开发；真实生产依旧要求用户选择来源和逐图批准。
- ASR 静音探针和对齐 forward 不是中文准确性或时间边界验收。尚无真实配音、分镜、人工审图、语义审核、有声预览、完整试听和正式画质结果；全部 `NOT_RUN`。

下一阶段进入条件已满足：SC-P1 输入/来源契约、整数时钟和图片快照。先使用技术夹具；生产级图片门禁不得绕过。当前没有初始化或暗中推进真实视频制作。
