# SC-P3 执行与验收记录

日期：2026-10-21。范围为实施清单 SC-P3-01～06，所有实现位于本 Skill；没有进入 SC-P3A/SC-P4/SC-P5，没有提交或推送。原有根目录、cover-studio、P0/P1/P2 交付保留。开始 HEAD 为 `3c0b583102984e01c7f27fc72b07da9a1998be21`，既有工作区修改通过 [baseline](sc-p3/baseline.json) 区分。

## 任务对应

| 任务 | 实现 | 验证 |
|---|---|---|
| SC-P3-01 母带和模型输入 | `speech_audio.py`，同源 48k stereo PCM → 16k mono PCM | 实际 PCM 计数、头尾静音验证；脉冲/内部静音回归 |
| SC-P3-02 锁定后端和有序匹配 | VoiceStudio `/transcribe` reference + `speech_text.py` | 实际 large-v3 响应；后端回退、段重叠/越界测试 |
| SC-P3-03 多对多映射 | 数字/百分比/单位规范化及读法覆盖 | 28%、120 元、2 kg、API、重复句、非 BMP 和原文码点映射 |
| SC-P3-04 可信窗口/采样时钟 | 离线 WhisperX 3.8.6 worker，原始 chars 和一次全局偏移 | 实际中文模型对齐；缺失、wildcard、插值、零时长、低分、粗回退区分 |
| SC-P3-05 人工覆盖 | 既有 overrides Schema、摘要/冲突/人类收据检查 | 过期/重叠/越界拒绝；读法修正；首镜头/完整回退人工确认；重复重放 |
| SC-P3-06 异常/编译接入 | `evaluate` + `apply_alignment` → 原有 `compile_timing` | 正常技术项目可编译；漏读/截断拒绝；生产不能绕过或使用技术证据 |

## 服务与模型

先读取并保存实时 [health](sc-p3/health.json)、[OpenAPI](sc-p3/openapi.json) 和 [ASR 状态](sc-p3/engines-asr.json)。VoiceStudio 0.5.6 当前为 WhisperX / faster-whisper-large-v3。health 声明 CUDA，但真实加载后的 `actual_execution_device=cpu`、精度 `int8`，因此本轮粗识别记作 **CPU 实际执行**，不以健康接口声明冒充 GPU 验证。原始每次响应及前后执行证据在项目 `work/alignment/evidence/`。

服务 API 没有确认原文/可信窗口输入，也没有原始 chars 完整性契约，因此只用于粗识别。细对齐复用 P0 已下载并按哈希锁定的中文 wav2vec2，使用 Skill 隔离环境的 CPU / WhisperX 3.8.6。未重新下载 ASR 或中文对齐权重，未修改 VoiceStudio 的环境、设置、服务代码或模型选择。服务未返回加载权重的 SHA256，不把本地文件核验说成服务内存中的模型字节证明。

开发中尝试准备 NLTK 英语 Punkt 数据时，下载器报网络地址限制，没有成功下载。最终实现无需它：归一化窗口已经是单句，隔离 worker 临时使用 NLTK 无训练 tokenizer，并断言完整单句范围；不会触发 WhisperX 的隐式资源下载，也不修改安装包文件。

## 实际音频验证

输入是 Windows 内置 Microsoft Huihui Desktop 生成的 **18.42 秒测试中文配音**，不是用户正式配音，不包含任何真实人工批准。生成脚本见 `scripts/create_speech_fixture.ps1`。原文为：

> 预算是120元，重量是2kg。增长了28%，这是API接口。请再检查。请再检查。

实际测试读法将 API 读作“应用程序”，因此初次运行准确留下内容差异。测试专用覆盖将该原文区间映射到实际读法；覆盖收据写明 `TECHNICAL FIXTURE ONLY`，整个项目及编译产物继续标记 technical_fixture，不能进入生产。

音频计数详见 [audio-validation.json](sc-p3/audio-validation.json)：源为 22050 Hz / mono / 406173 帧；母带为 48000 Hz / stereo / **884187 PCM 帧**；模型输入为 16000 Hz / mono / **294729 帧**。没有因 stereo 乘二。源与母带时长差不足一个 48k 采样；头部约 0.755 秒、尾部约 1.605 秒静音保持一致。另有实际 FFmpeg 脉冲测试核对内部静音与内容未被剪裁。

正常候选边界为 `0 / 316512 / 639264`（48k samples），后两处约 **6.594 / 13.318 秒**。正常项目通过同一 P1 编译器得到 **553 帧**，逻辑镜头长度为 `198 / 202 / 153`。这不是逐字精确率，也不是用户已经听过的边界。

真实负例在测试副本上构造，不改正常源音频：`missing` 删除中段包含第二句的区间，`truncated` 截短结尾。它们保留正常原文，必须生成 `REVIEW_REQUIRED` 并拒绝编译。初次截断测试发现服务给出超出实际尾部的段时间；实现现保留定位异常，不钳位放行。合法人工窗口只能解决时间问题，不能清除漏读/加读/截断内容差异。

## 验证命令与证据

- PASS：60 项 Python、37 项 Node、Skill 结构检查；最终真实 align/compile 共 6 项预期结果通过。正常项目无写入编译重放两次完全相同，两个反例继续被拒绝，见 [重放验证](sc-p3/replay-validation.json)。
- `.venv/Scripts/python.exe -m unittest discover -s tests -v`：[60 项 Python 日志](sc-p3/python-tests.txt)。
- 渲染器目录 `npm test`：[37 项 Node / contracts / TypeScript 日志](sc-p3/node-tests.txt)。未修改 P2 视觉执行层。
- `.venv/Scripts/python.exe -X utf8 .../skill-creator/scripts/quick_validate.py .`：[Skill 结构检查](sc-p3/skill-validation.txt)。Windows 默认 GBK 读取失败后显式启用 UTF-8，通过检查。
- 实际服务与模型运行命令、退出码和耗时：[integration.json](sc-p3/integration.json)。正常 align/compile 预期 0；漏读/截断 align 预期 3，compile 预期 2。早期失败记录单独保留，不作为最终 PASS。
- [正常 aligned](sc-p3/normal/work/alignment/aligned.json)、[漏读报告](sc-p3/missing/work/alignment/review.json)、[截断报告](sc-p3/truncated/work/alignment/review.json)。
- [独立 checkpoint](sc-p3/checkpoint-review.md)：指出 1 个 P1，已增加修复与回归；最终审查另见 `sc-p3/review.md`。

最终范围核对同时发现 `.idea` 和 `cover-studio` 有其他工作流的变动。本任务未编辑这些文件，也没有回退它们；最终 review-target 将其作为 concurrent exclusions 单独记录。

## 人工验收与限制

工程测试验证真实音频经过真实服务/模型、采样时钟、证据来源和拒绝机制。**人工逐候选边界试听：NOT_RUN**；**用户正式配音验收：NOT_RUN**。工程 PASS 不代替这两项，`human_boundary_audit` 不会被 Agent 改为批准。

数字/读法生成仅是匹配候选；无法确认的缩写、复杂数值和识别表述差异需要用户确认。超过 30 秒或不完整匹配的窗口需要拆分/确认，不自动猜测平均字速。WhisperX 原始字符秒数自带毫秒舍入，整数采样只保证唯一时钟，不虚构采样级声学精度。后续正式项目仍需图片渠道/逐图批准，以及 SC-P4/P5 的语义与有声预览审批。
