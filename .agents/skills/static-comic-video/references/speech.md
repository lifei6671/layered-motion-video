# SC-P3 中文语音与纠错

本阶段为换图生成语音证据，不生成字幕、TTS、配乐或最终封装。输入仍是 P1 项目；图片策略可保持待审，`align` 不晋级图片。生产 `compile` 仍先执行图片门禁，再重放 SC-P3 证据。

初始分镜允许尚未规划的非末尾 `transition_out: null`。P3 仅在内部时钟校验副本中将其视为零帧硬切；返回候选及原始分镜仍保留 null，不生成转场授权。已填写转场照常完整验证。生产编译仍要求完成 P4 语义规划及用户确认。

## 运行

工作目录是 Skill 根目录，使用既有隔离环境与 `reports/models.lock.json`。不安装到 VoiceStudio，不修改其模型/设备设置，不自动切换后端或下载权重。

```powershell
.venv/Scripts/python.exe -m static_comic align --project <episode> --voice-url http://127.0.0.1:13900 --models-lock reports/models.lock.json
.venv/Scripts/python.exe -m static_comic validate --project <episode>
.venv/Scripts/python.exe -m static_comic compile --project <episode>
```

`align` 返回 0 表示技术证据可用于编译，3 表示 `REVIEW_REQUIRED`，2 表示运行/输入错误。真实运行的输出见 `work/alignment/review.json`。技术项目必须显式加 `--technical-fixture`，且报告、编译图片与时间均维持技术标记；它们不能转作生产批准。

生产编译现在必须有有效 SC-P3 报告；P1/P2 原有纯技术时间夹具仍可独立运行。原 `input/storyboard.json` 不被改写，应用后的候选进入同一 `compile_timing`，最终源镜头数据写入 `timeline.lock.json`。语义锚点、转场类型和 placement 保留分镜中的规划；它们与声学边界不一致时保留调整原因，交 SC-P4 复核。

## 实际执行与证据

1. FFmpeg 选择源文件的 `0:a:0`，完整解码成 48 kHz / stereo / s16 母带，再从母带生成 16 kHz / mono / s16 模型输入。没有裁静音、改变速度、拼接或 `-shortest`。以 WAV 的 PCM frame count 计时，立体声不乘二，T 由真实母带采样数决定。
2. 核对服务当前为 `whisperx` / `Systran/faster-whisper-large-v3`，核验锁定本地 ASR 文件。调用 `/transcribe` 的 `mode=reference`、`refine=false`；此模式在当前服务中只用已安装模型、不请求词级 forced alignment。保留调用前后引擎状态及原始响应；后端变更阻断放行。服务未暴露已加载权重的逐文件摘要，因此文件校验不是远程加载字节的证明，服务结果只作粗识别。
3. NFKC、标点过滤、数字/百分比/常用单位读法形成候选匹配串，逐个读法码点保存原文区间。`28%` 的多个读音字符共同引用原文的一个区间。使用整段有序匹配，关闭 SequenceMatcher 的 autojunk；每个非相等片段都生成异常，匹配率不是通过阈值。
4. 完整相等、连续映射的粗分段提供候选窗口；人工窗口可以替换相交窗口。窗口不超过 30 秒。被替换窗口的剩余部分不会按平均字速补齐，缺证据仍待审。重复句保留原文和 ASR 全局顺序，缺少一次重复会留下内容异常。
5. 锁定 WhisperX 3.8.6，在隔离进程中以现有中文 wav2vec2 权重执行 `return_char_alignments=True`。加载设置 `model_cache_only=True`，不下载模型。归一化窗口不含空格和标点，已经是一个句子：worker 中临时提供 NLTK 无训练 tokenizer，仅用于单窗口分句，避免 WhisperX 隐式下载英语 Punkt 数据；不修改第三方安装文件。
6. 原始字符必须属于模型字典，有有限、正向、单调且在窗口内的 start/end/score，才可成为声学候选。低于 0.2 的分数只触发筛查，绝不解释为准确率；wildcard、缺失、无 score 的插值时间和粗分段回退分别标记。未确认时间阻断编译；内部不确定字符也需相邻边界的明确确认，且不能有内容差异。完全声学回退时，可在文本匹配、窗口可信及人工确认条件下使用粗区间，并在 `speech_intervals` 保留 `coarse_segment` / `manual_window` 来源；不伪造缺失字符时间。ASR 窗口越过实际音频尾部、逆序或重叠也输出定位异常，不钳位后冒充可信时间。

WhisperX 3.8.6 自身把字符秒数舍入到 0.001 秒。适配器用其原始十进制表示一次换算到 48 kHz 采样，再加实际窗口原点；整数采样是时钟单位，不表示声学精度达到一个采样。窗口按 16 kHz 的实际网格裁取，`input_16k` 与 `origin_samples` 共同记录，避免偏移加两次。

输出包括 `work/audio/{master_48k.wav,align_16k.wav,audio.json}`、`work/alignment/{asr_segments.json,aligned.json,review.json,worker.log}`。模型输入、读法计划、原始模型输出保存在 `work/alignment/evidence/<SHA256>.json`；重新运行保留旧证据，派生报告可更新。

## 人工纠错

首次无覆盖运行会生成 `work/alignment/overrides.template.json`。复制到 `input/overrides.json` 后编辑；已有覆盖不会被 `align` 改写。Schema 沿用 P1 的三种 entry：

- `reading`：`script_range` 和实际 `reading`，用于金额、单位、缩写或识别表述差异。数字超过四位默认候选按数字逐位读；不同读法要明确覆盖。英文缩写不强行用中文模型 wildcard 冒充对齐，需确认实际读法。
- `window`：原文区间和全局 48 kHz `samples: [start,end]`，重对齐范围不跨镜头，不拆一个读法 token。
- `boundary`：相邻两侧 `from_shot_id`、`to_shot_id` 和全局 `sample`，保留人工确认来源。第一镜头固定从音频原点 0 开始。

每条必须有原因及真实 `human` 收据（操作者、带时区时间、用户交互证据），并绑定原文/源音频/分镜字节摘要。覆盖重复、交叉、越界、窗口逆序、过期摘要会失败。修改覆盖后重新执行 `align`；随后 `compile` 从不可变原始证据确定性重放，不接受手改 `aligned.json` 的 PASS 或时间。原文、声音、分镜、覆盖或 PCM 改动都会使旧结果失效。

真实漏读/加读/截断始终保留内容异常。边界覆盖只修正时间，不删除内容异常。应修正源配音，或让用户明确修改原文与分镜，再重跑；不把 ASR 错误自动改成已确认读法。测试中的合成收据明确标为技术夹具，不能复制到实际项目。

## 验收边界

`PASS` 是技术编译候选，不是人类已逐边界试听。`human_boundary_audit` 保持 `NOT_RUN`，本阶段不代写真实用户批准。对照原音逐个检查候选边界、确认配音全文以及最终样片试听仍需真实用户，生产审批闭环属于后续阶段。

测试命令：`.venv/Scripts/python.exe -m unittest discover -s tests -v`；真实集成探针记录见 [SC-P3](../reports/SC-P3.md)。`scripts/create_speech_fixture.ps1` 仅用系统内置声音创建离线测试输入，`scripts/verify_speech_probe.py` 专门构造漏读/截断反例并调用真实服务，不是业务功能。探针目录已存在时拒绝重建；不覆盖已有证据。
