# SC-P6 缓存真实性、失败恢复与回归

范围仅为 SC-P6；实现、测试、协议和证据全部保留在本 Skill。未提交、推送或修改其他项目的工作；并发发生的 cover-studio 改动不属于本次交付。未新增依赖、模型下载、字幕、TTS、音乐或分段渲染。

## 实现

- `static_comic/cache.py`：内容/版本键、完整清单与实际文件 SHA256 检查、临时生成、逐文件原子发布及可捕获失败回滚、阶段命中原因和交付尝试状态。
- `project.py`：来源/许可/候选/逐图批准仍实时核验；逐图预处理、时间线、暂存分别缓存。改一张图仅重建相关预处理，视觉仍按整片缓存。
- `speech_audio.py`、`speech.py`：48k/16k 同源 PCM、粗 ASR 与锁定对齐窗口分别缓存；模型字节仍验证。后端变化/畸形 worker 结果不提交缓存，旧对齐结果不会被失败进程覆盖。
- `delivery.py`：Remotion 构建、540p/1080p 视觉和各自封装分别缓存。构建键包含实际导入的 schema、tsconfig、渲染代码、配置、锁文件、工具与图片。当前审批绑定包含源输入；画面缓存键只绑定执行内容与运行规格。
- 旧有效成片保留与当前成功分开：失败报告列出旧输入/文件摘要，status 不把旧文件存在解释成本次成功；重试仍须过当前门禁。

完整字段、运行命令和恢复边界见 [缓存协议](../references/cache.md)。发布保证为逐文件 `os.replace` 与可捕获异常回滚；不宣称跨文件断电事务或并发写入互斥，同一期串行执行。

## 验证

| 检查 | 结果与证据 |
|---|---|
| Python 全量回归 | PASS：140 项，438.513 秒；[完整日志](sc-p6/python-tests.txt) |
| 最终受影响回归 | PASS：42 项，235.496 秒，构建键补齐后复跑 P5/P6；[日志](sc-p6/targeted-tests.txt) |
| Node / 契约生成一致性 / TypeScript | PASS：69 项；[日志](sc-p6/node-tests.txt) |
| Skill frontmatter | PASS：官方 quick_validate.py，以 Python `-X utf8` 执行 |
| 真实 Remotion / FFmpeg 技术探针 | PASS：[结果](sc-p6/real-probe/result.json)、[完整媒体校验](sc-p6/real-probe/validation.json)、[输出](sc-p6/real-probe/technical-final.mp4) |
| 独立代码审查 | 见 [检查点记录](sc-p6/checkpoint-reviews.json)；最终覆盖与 freshness 另见 sc-p6/independent-review.json、final-freshness.json |

全量回归完成后，仅补齐构建缓存键和规范化根路径，并增加 schema 变更回归；最后复跑受影响的 P5/P6。全量 140 项与最终相关回归有重叠，不相加为测试总数。

真实探针使用 11.981 秒双声道合成音频及 3 张几何图，所有批准均为 SYNTHETIC TEST ONLY。S=575088、T=360、覆盖尾差 912 samples；全片解码与封装前视频帧摘要一致，AAC 全文/首尾内容检查通过。冷运行 78.547 秒、相同输入重跑 17.469 秒；audio、授权记录、3 张图、timeline、staging、build、两种 visual 与 mux 共 12 项最新记录均为 HIT。该耗时包含哈希和完整媒体验证，不是 SC-P7 性能基线或 SLA。

故障探针在实际 mux 临时 `audible.mp4` 写入部分字节后抛错，记录了具体 FFmpeg 参数；旧成片及批准 SHA256 均不变，status=FAILED/current_success=false。原命令重试后 OUTPUT_VERIFIED。删除正式视觉轨后明确 REBUILT/published_visual_missing_or_corrupt，并重新验证、封装。最终 MP4 SHA256：`6d03e67d6771d05429c4c53f66b39d384b8774c17a6580f5ce9f7ff2b55a7f07`。

## 缓存与门禁矩阵

| 条件 | 验证位置 / 行为 |
|---|---|
| 相同输入 | P6 delivery identical_rerun + 真实探针：摘要/批准不变，阶段 HIT |
| 一张原图变化 | P6 PreparationTests：仅 1 次相关预处理；P1/P3A 正式文件变化与审批测试阻止未审原图 |
| mixed 单镜头渠道变化 | P3A unconfirmed_mixed_mapping、source_change_and_rejection：需要新渠道/供图确认，原转场不能放行 |
| 来源/许可变化，像素不变 | P3A candidate_and_license_bytes、reimport_identical_bytes 与 P5 license_change：实时核验与重新审图 |
| 手动文件出现/覆盖/缺失 | P3A waiting/formal_file_change 与 P6 missing_image：文件存在不能批准，缺失阻止生成且保留旧成片 |
| 运镜/转场类型/位置/时长/边界变化 | P6 execution_change：整片视觉重建，旧批准失效；P4/P1 窗口与位置预算回归 |
| 只改转场解释 | P6 explanation_only：视觉 HIT，预览摘要变更、原批准拒绝；P4/P5 语义计划仍失效 |
| 只改配音、视觉时间线不变 | P6 voice_same_timeline：只重做音频/封装，视觉 HIT，必须重新有声批准 |
| 配音改变 T | P6 voice_duration：360→361 帧，视觉重建；生产 P3 对齐绑定回归 |
| 视觉/清单丢失、损坏、错误 key | P6 CacheTests、missing_or_corrupt_published_visual + 真实探针：不能误 HIT，完整重建 |
| 渲染/封装失败、缺图、暂存损坏 | P6 fault injection、publish rollback 与真实 mux 探针：明确失败、保留旧媒体/批准；重试验证成功 |
| 对齐、路径、批准回归 | 全量 P1/P3/P3A/P4/P5；P6 backend_changed 和 worker failure：失败不缓存、恢复可重试 |
| 构建实际依赖变化 | P6 imported_schema_change：bundle 与整片视觉失效 |

P6 delivery 矩阵中的 renderer doubles 用于验证调度/键与状态，不作为画质证据；真实渲染、音视频全解码由 P5 与本期真实探针单独覆盖。P6 对齐恢复测试模拟服务/worker，未宣称本期重新执行真实中文 ASR。

## 审查修复与未执行项

独立检查点发现并修复了两项 P1：损坏 manifest 缺字段/错误结构不能重建；VoiceStudio 后端不一致结果永久缓存。新增回归后独立复核 21 项通过。主 Agent 进一步补齐 schema/tsconfig 构建依赖，并修正真实探针的故障拦截范围；首次不充分的探针证据已删除，不计入最终 PASS。

技术 PASS 不等于生产批准。语义/试听收据仅 TEST_ONLY，正式画质与真实用户验收 NOT_RUN，production_accepted=false。SC-P7 的真实原画、60～90 秒样片、实际观看试听及 1/3 分钟性能基线尚未执行。
