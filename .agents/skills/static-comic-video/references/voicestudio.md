# VoiceStudio 优先的复用策略

用户在本轮明确指定：优先使用本机 `http://127.0.0.1:13900` 服务；服务不符合要求时，再补齐本地模型能力。优先检查服务，再检查已有权重，最后才下载确实缺失的模型。不要修改 VoiceStudio 的全局模型、设备或网络设置。

## 2026-10-21 实际发现

只读探针见 [voicestudio.json](../reports/voicestudio.json)。服务版本 0.5.6，`/health` 正常；`/dictation/readiness?purpose=transcribe` 返回 `ready: true`；`/engines/asr` 当前为 `whisperx` 和 `Systran/faster-whisper-large-v3`，配置为 RTX 4070 SUPER / CUDA。服务执行证据当时为 `not_loaded`，不是推理已通过。

提供 `/transcribe`、`/v1/audio/transcriptions`。前者 `mode=reference` 可用已安装的当前后端进行粗识别；`mode=accurate` 请求词级时间。后者提供 `verbose_json` 和词/段时间参数。P0 时真实音频上传为 `NOT_RUN`；SC-P3 已通过 `/transcribe` 执行真实音频集成测试，实际响应和调用前后设备证据见 [SC-P3 记录](../reports/SC-P3.md)。

## 与 SC-P3 要求的具体差距

1. OpenAPI 的两个转录请求都没有“已确认原文/读法区间/可信音频窗口”的强制对齐输入。`prompt` 是识别提示，不是必须逐字对齐的原文。
2. 本机 `backend/services/asr_backend.py:555` 按语言懒加载 wav2vec2。`forced_align` 的调用使用 `return_char_alignments=False`（约 613 行），不能直接给出需求要求的原始字符对齐证据。
3. 同一函数在模型缺失或对齐失败时保留原来的段时间；上层成功转录不能证明时间来自声学对齐。不能把此结果直接标为“精确成功”。
4. 名为 `WhisperX (faster-whisper + wav2vec2 forced alignment)` 的条目是后端能力标签。其 `is_available` 检查依赖及 CTranslate2/cuDNN，不逐个验证中文对齐权重已下载。

因此当前服务作为**优先的粗识别候选**；它不能单独满足本项目“按已确认原文强制对齐，并保留缺失、插值、失败来源证据”的完整契约。SC-P3 已实际调用并检查服务返回结果，保存原始响应与实际 engine；候选交给同一原文匹配/时间编译流程。服务不能提供的对齐明细由本地锁定 WhisperX 补齐。不能只因健康检查通过就跳过对齐验证，也不自动修改 VoiceStudio 来扩充接口。

## 本机模型

- 已复用 VoiceStudio 的 large-v3 CTranslate2 模型，并在隔离环境完成离线加载和静音 ASR/VAD 探针。
- tiny 为 sherpa-onnx 格式，不能直接作为 WhisperX 的 CTranslate2 权重。
- 在检查到的 VoiceStudio 模型缓存中没有中文 wav2vec2 对齐权重。本轮另行下载并锁定中文对齐模型，已完成离线 forward；路径与哈希见 [models.lock.json](../reports/models.lock.json)。
- 下载发生在本轮服务优先约定提出之前；今后不重复下载，按上面的服务→已有权重→缺失下载顺序执行。

这些事实来自本轮实时 HTTP、已安装源码和文件检查；迁移机器或升级 VoiceStudio 后重新检查接口与实际返回证据，不把该版本的差距当成永久限制。
